from __future__ import annotations

import json
import math
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any


def _iter_json_objects(text: str) -> list[Any]:
    """Match ClawGym's upstream stream parser, including multi-line JSON."""
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


def _mean_numeric(mapping: dict[str, Any]) -> float | None:
    values = [
        float(value)
        for value in mapping.values()
        if isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
    ]
    return sum(values) / len(values) if values else None


def _parse(stdout: str, stderr: str) -> tuple[float | None, dict[str, Any] | None]:
    for text in (stdout, stderr):
        for value in _iter_json_objects(text):
            if isinstance(value, dict):
                score = _mean_numeric(value)
                if score is not None:
                    return score, value
    scalar = re.compile(r"^[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?$")
    for text in (stdout, stderr):
        for line in reversed(text.splitlines()):
            if scalar.match(line.strip()):
                return float(line.strip()), {"score": float(line.strip())}
    return None, None


def main() -> int:
    workspace = Path(
        os.environ.get("CLAWGYM_WORKSPACE")
        or (sys.argv[1] if len(sys.argv) > 1 else "/workspace")
    )
    reward_command = [
        sys.executable,
        os.environ.get("CLAWGYM_REWARD_SCRIPT", "/tests/official_reward.py"),
        str(workspace),
    ]
    reward_timeout = float(os.environ.get("CLAWGYM_REWARD_TIMEOUT_SEC", "120"))
    try:
        completed = subprocess.run(
            reward_command,
            cwd=workspace,
            capture_output=True,
            text=True,
            timeout=reward_timeout,
            check=False,
        )
        reward_stdout = completed.stdout
        reward_stderr = completed.stderr
        reward_returncode = completed.returncode
        reward_timed_out = False
    except subprocess.TimeoutExpired as exc:
        reward_stdout = exc.stdout if isinstance(exc.stdout, str) else ""
        reward_stderr = exc.stderr if isinstance(exc.stderr, str) else ""
        reward_returncode = None
        reward_timed_out = True
    score, metrics = _parse(reward_stdout, reward_stderr)
    record_path = Path(os.environ.get("CLAWGYM_RECORD_PATH", "/tests/record.json"))
    if not record_path.exists():
        record_path = Path(__file__).with_name("record.json")
    record = (
        json.loads(record_path.read_text(encoding="utf-8"))
        if record_path.exists()
        else {}
    )
    rules = record.get("rules") or []
    score_weights = record.get("score_weights") or {}
    code_weight = float(score_weights.get("code", 0.7))
    rubric_weight = float(score_weights.get("rubric", 0.3))
    if code_weight < 0 or rubric_weight < 0 or code_weight + rubric_weight <= 0:
        raise ValueError("invalid ClawGym score weights")
    rubric_score: float | None = None
    rubric_payload: dict[str, Any] | None = None
    log_dir = Path(os.environ.get("HARBOR_VERIFIER_LOG_DIR", "/logs/verifier"))
    log_dir.mkdir(parents=True, exist_ok=True)

    def write_evidence(payload: dict[str, Any]) -> None:
        (log_dir / "official_result.json").write_text(
            json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

    if rules:
        rubric_script = Path("/tests/rubric_verifier.py")
        if not rubric_script.exists():
            rubric_script = Path(__file__).with_name("rubric_verifier.py")
        rubric = subprocess.run(
            [sys.executable, str(rubric_script), str(workspace)],
            cwd=workspace,
            capture_output=True,
            text=True,
            check=False,
        )
        rubric_path = (
            Path(os.environ.get("HARBOR_VERIFIER_LOG_DIR", "/logs/verifier"))
            / "rubric.json"
        )
        if rubric_path.exists():
            rubric_payload = json.loads(rubric_path.read_text(encoding="utf-8"))
            value = rubric_payload.get("score")
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                rubric_score = float(value)
        # Preserve the official hybrid policy: use an available component when
        # the other component is unavailable, while recording incompleteness in
        # verifier evidence for an external Score Completeness gate.
        if rubric_score is None:
            payload = {
                "reward": score,
                "code_reward": score,
                "rubric_reward": rubric_payload,
                "official_returncode": reward_returncode,
                "rubric_returncode": rubric.returncode,
                "score_weights": {"code": code_weight, "rubric": rubric_weight},
                "effective_score_mode": "code" if score is not None else None,
                "score_completeness": "incomplete",
                "timed_out": reward_timed_out,
                "stdout": reward_stdout,
                "stderr": reward_stderr,
            }
            write_evidence(payload)
            if score is None:
                return 2
            (log_dir / "reward.json").write_text(
                json.dumps({"reward": score}) + "\n", encoding="utf-8"
            )
            (log_dir / "reward.txt").write_text(f"{score}\n", encoding="utf-8")
            return 0
    final_score = score
    effective_score_mode = (
        "code" if score is not None else "rubric" if rubric_score is not None else None
    )
    if rules and score is None:
        final_score = rubric_score
        effective_score_mode = "rubric"
    elif rules and score is not None and rubric_score is not None:
        total_weight = code_weight + rubric_weight
        final_score = (
            float(score) * code_weight + rubric_score * rubric_weight
        ) / total_weight
        effective_score_mode = "hybrid"
    requested_code = bool(str(record.get("hook_code") or "").strip())
    requested_rubric = bool(rules)
    code_complete = not requested_code or (
        score is not None and not reward_timed_out and reward_returncode == 0
    )
    rubric_complete = not requested_rubric or rubric_score is not None
    score_completeness = (
        "complete" if code_complete and rubric_complete else "incomplete"
    )
    payload = {
        "reward": final_score,
        "metrics": metrics,
        "code_reward": score,
        "rubric_reward": rubric_payload,
        "score_weights": {"code": code_weight, "rubric": rubric_weight},
        "score_mode": "hybrid"
        if rules and score is not None
        else "rubric"
        if rules
        else "code",
        "effective_score_mode": effective_score_mode,
        # This is an adapter-level evidence gate. It does not change the
        # official reward selected above, including valid numeric output from
        # a non-zero reward hook.
        "score_completeness": score_completeness,
        "official_returncode": reward_returncode,
        "timed_out": reward_timed_out,
        "stdout": reward_stdout,
        "stderr": reward_stderr,
    }
    write_evidence(payload)
    if final_score is None or not math.isfinite(final_score):
        return 1
    # Harbor parses reward.json as a numeric-only score map. Keep benchmark
    # evidence in a separate verifier artifact.
    (log_dir / "reward.json").write_text(
        json.dumps({"reward": final_score}) + "\n", encoding="utf-8"
    )
    (log_dir / "reward.txt").write_text(f"{final_score}\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
