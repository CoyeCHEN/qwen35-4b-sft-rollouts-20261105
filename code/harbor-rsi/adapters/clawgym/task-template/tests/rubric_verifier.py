"""ClawGym rubric verifier, preserving the pinned judge protocol.

This runs only in Harbor's separate verifier environment. It never exposes
rubric data or the judge credentials to the agent environment.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path, PurePosixPath
from typing import Any


def _safe_path(value: str) -> str:
    path = PurePosixPath(str(value).replace("\\", "/"))
    if path.is_absolute() or ".." in path.parts or not path.as_posix().strip():
        raise ValueError(f"unsafe rubric target path: {value!r}")
    return path.as_posix()


def _json_objects(text: str) -> list[Any]:
    decoder = json.JSONDecoder()
    values: list[Any] = []
    index = 0
    while index < len(text):
        while index < len(text) and text[index].isspace():
            index += 1
        if index >= len(text):
            break
        try:
            value, end = decoder.raw_decode(text, index)
        except json.JSONDecodeError:
            index += 1
            continue
        values.append(value)
        index = end
    return values


def _numeric(value: Any) -> float | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError:
            return None
    return None


def _max_score(rule: dict[str, Any]) -> float:
    scores = rule.get("scores")
    values = [_numeric(key) for key in scores] if isinstance(scores, dict) else []
    values = [value for value in values if value is not None]
    return max(values) if values else 1.0


def _score_keys(rule: dict[str, Any], index: int) -> list[str]:
    keys = [f"criterion_{index}", str(index)]
    if rule.get("name"):
        keys.append(str(rule["name"]))
    if rule.get("file_path"):
        keys.append(str(rule["file_path"]))
    return keys


def _score_sort_key(value: Any) -> tuple[bool, float | str]:
    number = _numeric(value)
    return (number is None, number if number is not None else str(value))


def _normalize_scores(
    parsed: dict[str, Any], rules: list[dict[str, Any]]
) -> tuple[float | None, dict[str, Any]]:
    raw = parsed.get("scores") if isinstance(parsed.get("scores"), dict) else parsed
    if not isinstance(raw, dict) or not rules:
        return None, {
            "raw_scores": raw if isinstance(raw, dict) else None,
            "missing": [f"criterion_{i}" for i in range(1, len(rules) + 1)],
        }
    total = 0.0
    maximum = 0.0
    matched: dict[str, float] = {}
    missing: list[str] = []
    for index, rule in enumerate(rules, 1):
        limit = _max_score(rule)
        maximum += limit
        value = next(
            (_numeric(raw[key]) for key in _score_keys(rule, index) if key in raw), None
        )
        if value is None:
            missing.append(f"criterion_{index}")
            value = 0.0
        value = max(0.0, min(value, limit))
        matched[f"criterion_{index}"] = value
        total += value
    return (total / maximum if maximum else None), {
        "raw_scores": raw,
        "matched_scores": matched,
        "missing": missing,
    }


def _target_files(workspace: Path, record: dict[str, Any]) -> dict[str, Any]:
    initial = {
        item["file_path"]: item["sha256"] for item in record.get("input_manifest", [])
    }
    result: dict[str, Any] = {}
    for rule in record.get("rules", []):
        raw_path = str(rule.get("file_path") or "")
        path = _safe_path(raw_path)
        target = workspace / path
        if not target.exists():
            result[path] = {"exists": False, "content": ""}
            continue
        if not target.is_file():
            result[path] = {
                "exists": False,
                "content": "",
                "error": "not a regular file",
            }
            continue
        digest = hashlib.sha256(target.read_bytes()).hexdigest()
        if initial.get(path) == digest:
            result[path] = {
                "exists": False,
                "content": "",
                "excluded": True,
                "reason": "unchanged preloaded input file",
            }
            continue
        try:
            result[path] = {
                "exists": True,
                "content": target.read_text(encoding="utf-8")[:4000],
            }
        except UnicodeDecodeError:
            result[path] = {"exists": True, "content": "", "error": "not utf-8 text"}
    return result


def _prompt(record: dict[str, Any], targets: dict[str, Any]) -> str:
    blocks = []
    for path, info in targets.items():
        if info.get("excluded"):
            blocks.append(
                f"### Excluded Preloaded File: {path}\nReason: {info['reason']}\n"
            )
        elif not info.get("exists"):
            blocks.append(f"### Missing File: {path}\n")
        else:
            blocks.append(f"### File: {path}\n{info.get('content', '')}")
    rules = []
    for index, rule in enumerate(record.get("rules", []), 1):
        rules.append(
            f"{index}. id=criterion_{index} name={rule.get('name', f'criterion_{index}')} file={rule.get('file_path', '')}"
        )
        for key in sorted((rule.get("scores") or {}), key=_score_sort_key):
            rules.append(f"   - {key}: {(rule.get('scores') or {})[key]}")
    return (
        "You are grading an OpenClaw agent result.\n\n"
        "You must not call, request, or simulate any tools. Do not browse, list directories, open files, inspect the workspace, or ask for more context. Grade only from the task, final output files, and rubrics included in this prompt.\n\n"
        "Before giving the final judgement, you should provide a detailed analysis explaining how the final outputs satisfy or fail each rubric criterion.\n\n"
        "Your final judgement must end with exactly one standalone JSON object and nothing else after it. The final JSON object must contain exactly two keys: `scores` and `notes`.\n\n"
        "- `scores` must map every rubric id (`criterion_1`, `criterion_2`, ...) to one numeric score chosen from that rubric's allowed score anchors.\n"
        "- `notes` must be a concise string summarizing the main reasons for the assigned scores.\n\n"
        "Do not include any overall score in the final JSON. Do not compute or report the final aggregated score. Score aggregation will be handled separately by post-processing.\n\n"
        "Grade the final outputs and transcript-derived evidence only."
        f"## User Task\n{record.get('prompt', '')}\n\n"
        "## Final Output Files\n"
        f"{chr(10).join(blocks)}\n\n## Rubric\n{chr(10).join(rules)}\n"
    )


def main() -> int:
    workspace = Path(
        os.environ.get("CLAWGYM_WORKSPACE")
        or (sys.argv[1] if len(sys.argv) > 1 else "/workspace")
    )
    log_dir = Path(os.environ.get("HARBOR_VERIFIER_LOG_DIR", "/logs/verifier"))
    log_dir.mkdir(parents=True, exist_ok=True)
    record_path = Path(os.environ.get("CLAWGYM_RECORD_PATH", "/tests/record.json"))
    if not record_path.exists():
        record_path = Path(__file__).with_name("record.json")
    record = json.loads(record_path.read_text(encoding="utf-8"))
    rules = record.get("rules") or []
    base_url = os.environ.get("CLAWGYM_JUDGE_BASE_URL")
    api_key = os.environ.get("CLAWGYM_JUDGE_API_KEY")
    if not base_url or not api_key:
        payload = {
            "available": False,
            "score": None,
            "reason": "judge not configured",
            "rules": rules,
        }
        (log_dir / "rubric.json").write_text(
            json.dumps(payload, indent=2) + "\n", encoding="utf-8"
        )
        return 2
    targets = _target_files(workspace, record)
    request_payload = {
        "model": os.environ.get("CLAWGYM_JUDGE_MODEL", "deepseek-flash"),
        "messages": [
            {
                "role": "system",
                "content": "You are a strict grader. Do not call tools or request external files. Use only the prompt contents. You may provide concise analysis, but your response must end with the requested JSON scores object.",
            },
            {"role": "user", "content": _prompt(record, targets)},
        ],
        "temperature": 0.6,
        "max_tokens": 8192,
    }
    request = urllib.request.Request(
        base_url.rstrip("/") + "/chat/completions",
        data=json.dumps(request_payload).encode(),
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
    )
    # Keep the exact request/response contract for parity audits. The request
    # contains no credential; the API key remains only in the Authorization
    # header and is never written to verifier artifacts.
    (log_dir / "judge_request.json").write_text(
        json.dumps(request_payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    try:
        with urllib.request.urlopen(
            request, timeout=float(os.environ.get("CLAWGYM_JUDGE_TIMEOUT_SEC", "180"))
        ) as response:
            body = json.loads(response.read().decode())
        (log_dir / "judge_response.json").write_text(
            json.dumps(body, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        text = body["choices"][0]["message"]["content"]
        stripped = text.strip()
        if stripped.startswith("{"):
            try:
                parsed = json.loads(stripped)
            except json.JSONDecodeError:
                parsed = next(
                    (v for v in reversed(_json_objects(text)) if isinstance(v, dict)),
                    {},
                )
        else:
            parsed = next(
                (v for v in reversed(_json_objects(text)) if isinstance(v, dict)), {}
            )
        score, normalization = _normalize_scores(parsed, rules)
        payload = {
            "available": True,
            "score": score,
            "parsed": parsed,
            "normalization": normalization,
            "target_files": targets,
        }
    except Exception as exc:
        payload = {
            "available": True,
            "score": None,
            "error": f"{type(exc).__name__}: {exc}",
            "target_files": targets,
        }
        (log_dir / "judge_error.json").write_text(
            json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    (log_dir / "rubric.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    if not isinstance(payload.get("score"), (int, float)):
        return 1
    (log_dir / "rubric.txt").write_text(f"{payload['score']}\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
