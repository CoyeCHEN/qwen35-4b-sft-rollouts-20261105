"""Harbor handoff and verifier boundary for one native WorkspaceBench case.

The native WorkspaceBench runner and Judge remain authoritative.  This module
only waits for Harbor's CLI marker, invokes the unchanged Judge, and records a
small, redacted diagnostic record so a missing reward can be attributed without
retaining prompts, API keys, or model responses.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import shutil
import sys
import tempfile
import time
import traceback
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


Json = Any
DEFAULT_DIAGNOSTICS = "/logs/verifier/workspacebench-judge.json"
_SECRET_RE = re.compile(r"(?i)(bearer\s+|api[_-]?key\s*[=:]\s*)[^\s,;]+")


def load_module(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load native module: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _redact(value: Any) -> str:
    return _SECRET_RE.sub(r"\1<redacted>", str(value or ""))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
    temporary.replace(path)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def agent_visible_metadata(meta: dict[str, Any]) -> dict[str, Any]:
    excluded = {
        "rubrics",
        "rubric_types",
        "judge_metadata",
        "ground_truth",
        "reference_output",
    }
    return {
        key: value
        for key, value in meta.items()
        if key not in excluded
        and not key.startswith(("rubric_", "judge_", "ground_truth_"))
    }


class _Diagnostics:
    def __init__(
        self, path: Path, *, model: str | None = None, base_url: str | None = None
    ) -> None:
        self.path = path
        parsed = urllib.parse.urlsplit(str(base_url or ""))
        self.data: dict[str, Json] = {
            "schema_version": 1,
            "status": "running",
            "stage": "initialization",
            "started_at": time.time(),
            "model": model,
            "base_url": f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
            if parsed.scheme
            else None,
            "api_key_present": bool(os.environ.get("JUDGE_API_KEY")),
            "api_requested": False,
            "requests": [],
            "response_parse_error": None,
            "reward_written": False,
        }

    def update(self, *, stage: str | None = None, **values: Json) -> None:
        if stage:
            self.data["stage"] = stage
        self.data.update(values)
        write_json(self.path, self.data)

    def finish(
        self, *, status: str, stage: str, error: BaseException | None = None
    ) -> None:
        self.data["status"] = status
        self.data["stage"] = stage
        self.data["finished_at"] = time.time()
        self.data["duration_ms"] = int(
            (self.data["finished_at"] - self.data["started_at"]) * 1000
        )
        if error is not None:
            self.data["exception"] = {
                "type": type(error).__name__,
                "message": _redact(str(error))[:2000],
                "traceback": _redact(traceback.format_exc())[-12000:],
            }
        write_json(self.path, self.data)
        text_path = self.path.with_suffix(".log")
        text_path.write_text(
            json.dumps(self.data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )


def _request_audit(
    diagnostics: _Diagnostics, request: urllib.request.Request, timeout: Any
) -> dict[str, Json]:
    parsed = urllib.parse.urlsplit(request.full_url)
    return {
        "method": request.get_method(),
        "scheme": parsed.scheme,
        "host": parsed.netloc,
        "path": parsed.path,
        "model": diagnostics.data.get("model"),
        "timeout_seconds": timeout,
        "request_bytes": len(request.data or b""),
        "started_at": time.time(),
    }


def _install_http_audit(native: Any, diagnostics: _Diagnostics) -> Any:
    original = native.urllib.request.urlopen

    def audited(request: Any, *args: Any, **kwargs: Any) -> Any:
        req = (
            request
            if isinstance(request, urllib.request.Request)
            else urllib.request.Request(str(request))
        )
        audit = _request_audit(
            diagnostics, req, kwargs.get("timeout", args[0] if args else None)
        )
        diagnostics.data["api_requested"] = True
        diagnostics.data["requests"].append(audit)
        diagnostics.update(stage="http_request_started")
        started = time.monotonic()
        try:
            response = original(request, *args, **kwargs)
            audit.update(
                {
                    "status": int(getattr(response, "status", response.getcode())),
                    "response_bytes": int(
                        response.headers.get("Content-Length", 0) or 0
                    ),
                    "content_type": response.headers.get("Content-Type"),
                }
            )
            return response
        except urllib.error.HTTPError as exc:
            audit.update(
                {
                    "status": int(exc.code),
                    "error_code": f"http_{exc.code}",
                    "error_type": "HTTPError",
                }
            )
            raise
        except Exception as exc:
            audit.update(
                {
                    "error_code": type(exc).__name__,
                    "error_type": type(exc).__name__,
                    "error_message": _redact(str(exc))[:500],
                }
            )
            raise
        finally:
            audit["duration_ms"] = int((time.monotonic() - started) * 1000)
            diagnostics.update(stage="http_request_finished")

    native.urllib.request.urlopen = audited
    return original


def wait_for_harbor(
    *,
    prompt: str,
    work_dir: str,
    sandbox_dir: str,
    timeout_s: float,
    api_provider: dict[str, Any],
    expected_instruction: Path,
    agent_logs: Path,
    parser: Any,
) -> dict[str, Any]:
    if prompt != expected_instruction.read_text():
        raise RuntimeError("Harbor instruction differs from native Workspace prompt")
    started = time.time()
    raw = Path(sandbox_dir) / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    marker = agent_logs / "open-harness.complete.json"
    if marker.exists():
        raise RuntimeError("A prior Harbor completion exists before native preparation")
    (raw / "native-prompt.txt").write_text(prompt)
    write_json(raw / "harbor-ready.json", {"work_dir": work_dir, "started_at": started})
    deadline = time.monotonic() + timeout_s
    while not marker.is_file():
        if time.monotonic() >= deadline:
            raise TimeoutError(
                "Harbor CLI did not complete within the native runner budget"
            )
        time.sleep(0.25)
    completion = json.loads(marker.read_text())
    if not completion.get("identity") or completion.get("exit_code") != 0:
        raise RuntimeError("Harbor CLI completion is missing an identity or failed")
    stdout = agent_logs / "open-harness.stdout.jsonl"
    stderr = agent_logs / "open-harness.stderr.log"
    shutil.copy2(stdout, raw / "openharness_stdout.jsonl")
    shutil.copy2(stderr, raw / "openharness_stderr.log")
    shutil.copy2(stdout, raw / "stdout.txt")
    shutil.copy2(stderr, raw / "stderr.txt")
    shutil.copy2(marker, raw / "harbor-complete.json")
    trace = parser._parse_openharness_jsonl(
        stdout.read_text(),
        prompt=prompt,
        started_at=started,
        base_url=str(api_provider["baseUrl"]),
        model=str(api_provider["model"]),
    )
    return {
        "status": "ok",
        "paths": [],
        "errorMessage": None,
        "trace": {
            "runner": "openharness",
            "agentId": None,
            "rawDir": str(raw),
            "llm": {
                "provider": "deepseek",
                "baseUrl": api_provider["baseUrl"],
                "model": api_provider["model"],
            },
            **trace,
            "stdoutPath": str(raw / "openharness_stdout.jsonl"),
            "stderrPath": str(raw / "openharness_stderr.log"),
        },
        "metrics": {
            "turns": trace.get("turns"),
            "promptTokens": trace["usageTotal"]["prompt_tokens"],
            "completionTokens": trace["usageTotal"]["completion_tokens"],
            "totalTokens": trace["usageTotal"]["total_tokens"],
        },
        "durationMs": int((time.time() - started) * 1000),
    }


def validate_judge_response(response: Any, rubric_count: int) -> None:
    if not isinstance(response, dict) or not isinstance(response.get("rubrics"), list):
        raise RuntimeError("Native Judge response lacks rubric judgments")
    rows = response["rubrics"]
    if len(rows) != rubric_count or any(
        not isinstance(row, dict)
        or type(row.get("index")) is not int
        or type(row.get("passed")) is not bool
        for row in rows
    ):
        raise RuntimeError(
            "Native Judge response has invalid or incomplete rubric judgments"
        )
    if sorted(row["index"] for row in rows) != list(range(rubric_count)):
        raise RuntimeError(
            "Native Judge response has duplicated or missing rubric indexes"
        )


def judge_single_case(
    source: Path,
    case: Path,
    metadata: Path,
    judge_config: Path,
    diagnostics: _Diagnostics,
) -> float:
    diagnostics.update(
        stage="input_validation", case=str(case), metadata_sha256=_sha256(metadata)
    )
    native = load_module("workspace_native_judge", source / "agent_eval.py")
    meta = json.loads(metadata.read_text())
    if not isinstance(meta.get("rubrics"), list) or not meta["rubrics"]:
        raise RuntimeError("Original task metadata has no rubrics")
    output_dir = case / "output"
    if not output_dir.is_dir() or not any(output_dir.iterdir()):
        raise RuntimeError(
            f"Judge input output directory is missing or empty: {output_dir}"
        )
    write_json(case / "metadata.json", meta)
    original_chat = native._chat_completions
    responses: list[dict[str, Any]] = []
    last_content = ""

    def capture(**kwargs: Any) -> Any:
        nonlocal last_content
        diagnostics.update(stage="judge_call", request_model=kwargs.get("model"))
        full, usage, content = original_chat(**kwargs)
        last_content = content or ""
        responses.append(
            {
                "response_present": full is not None,
                "usage": usage,
                "content_length": len(content or ""),
            }
        )
        write_json(case / "native-judge-responses.json", responses)
        if full is None:
            parsed = native._json_first_object(content or "")
            diagnostics.update(
                response_parse_error=(
                    "Judge API response was not parseable JSON"
                    if parsed is None
                    else "Judge API response did not produce a chat completion"
                )
            )
        return full, usage, content

    original_urlopen = _install_http_audit(native, diagnostics)
    try:
        native._chat_completions = capture
        result = native.evaluate_task(str(case), eval_yaml_path=str(judge_config))
    finally:
        native.urllib.request.urlopen = original_urlopen
    write_json(case / "native-judge-result.json", result)
    artifact_path = Path(result.get("rubricsPath", ""))
    if artifact_path.is_file():
        artifact = json.loads(artifact_path.read_text())
        artifact.setdefault("judge", {})["rawResponseHead"] = "<redacted>"
        write_json(artifact_path, artifact)
    if (
        not result.get("success")
        or not responses
        or not responses[-1]["response_present"]
    ):
        raise RuntimeError(
            "Native Workspace Judge did not return a successful API response"
        )
    parsed_response = native._json_first_object(last_content)
    if not isinstance(parsed_response, dict):
        diagnostics.update(
            stage="response_parse",
            response_parse_error="Judge response did not contain a JSON object",
        )
        raise RuntimeError("Native Judge response was not valid JSON")
    try:
        validate_judge_response(parsed_response, len(meta["rubrics"]))
    except RuntimeError as exc:
        diagnostics.update(stage="response_parse", response_parse_error=str(exc))
        raise
    diagnostics.update(stage="response_parse", response_valid=True)
    # The response content is intentionally kept out of diagnostics. Re-read the
    # native artifact only for structural validation and remove its raw response.
    if not artifact_path.is_file():
        raise RuntimeError("Native Workspace Judge did not write a rubric artifact")
    artifact = json.loads(artifact_path.read_text())
    artifact.setdefault("judge", {})["rawResponseHead"] = "<redacted>"
    write_json(artifact_path, artifact)
    summary = (
        artifact.get("summary") if isinstance(artifact.get("summary"), dict) else {}
    )
    if summary.get("total") != len(meta["rubrics"]):
        raise RuntimeError("Native Workspace Judge did not score every original rubric")
    diagnostics.update(
        stage="rubric_scored",
        rubric_total=summary.get("total"),
        rubric_passed=summary.get("passed"),
    )
    return float(summary["passed"]) / float(summary["total"])


def verify_single_case(config_path: Path, metadata: Path, reward_path: Path) -> float:
    import yaml

    config = yaml.safe_load(config_path.read_text())
    model = os.environ.get("JUDGE_MODEL", "")
    base_url = os.environ.get("JUDGE_API_BASE", "")
    diagnostics = _Diagnostics(
        Path(os.environ.get("JUDGE_DIAGNOSTICS_PATH", DEFAULT_DIAGNOSTICS)),
        model=model,
        base_url=base_url,
    )
    try:
        diagnostics.update(
            stage="configuration",
            env_base_url_present=bool(base_url),
            env_model_present=bool(model),
            env_key_present=bool(os.environ.get("JUDGE_API_KEY")),
        )
        if not base_url or not model or not os.environ.get("JUDGE_API_KEY"):
            raise RuntimeError(
                "JUDGE_API_BASE, JUDGE_MODEL, and JUDGE_API_KEY are required"
            )
        root = Path(config["output_dir"])
        exit_path = root / "native-entry-exit.json"
        deadline = time.monotonic() + 300
        while not exit_path.is_file():
            if time.monotonic() >= deadline:
                raise TimeoutError(
                    "Native Workspace runner did not finish output collection"
                )
            time.sleep(0.25)
        exit_record = json.loads(exit_path.read_text())
        diagnostics.update(
            stage="native_artifact_validation",
            native_exit_code=exit_record.get("exit_code"),
        )
        if exit_record.get("exit_code") != 0:
            raise RuntimeError("Native Workspace runner or isolation guard failed")
        metadata_obj = json.loads(metadata.read_text())
        task_id = str(metadata_obj["id"])
        case = (
            root
            / f"{config['agent_name']}--{config['model_name']}--{config['run_name']}"
            / task_id
        )
        agent = json.loads((case / "agent.json").read_text())
        if agent.get("runnerStatus") != "ok":
            raise RuntimeError(
                "Native Workspace runner did not observe normal CLI completion"
            )
        with tempfile.TemporaryDirectory(prefix="workspace-native-judge-") as temporary:
            judge_config = Path(temporary) / "judge.yaml"
            judge_config.write_text(
                yaml.safe_dump(
                    {
                        "baseUrl": base_url,
                        "apiKey": os.environ["JUDGE_API_KEY"],
                        "model": model,
                        "model_name": model,
                    }
                )
            )
            judge_config.chmod(0o600)
            reward = judge_single_case(
                Path(config["native_src"]), case, metadata, judge_config, diagnostics
            )
        reward_path.parent.mkdir(parents=True, exist_ok=True)
        temporary_reward = reward_path.with_suffix(reward_path.suffix + ".tmp")
        temporary_reward.write_text(f"{reward}\n")
        temporary_reward.replace(reward_path)
        diagnostics.update(stage="reward_written", reward_written=True, reward=reward)
        diagnostics.finish(status="passed", stage="reward_written")
        return reward
    except BaseException as exc:
        diagnostics.finish(
            status="failed", stage=str(diagnostics.data.get("stage")), error=exc
        )
        raise


def run_single_case(config_path: Path) -> dict[str, Any]:
    import yaml

    config = yaml.safe_load(config_path.read_text())
    source = Path(config["native_src"])
    sys.path.insert(0, str(source))
    native = load_module("workspace_native_runner", source / "agent_runner.py")
    parser = load_module(
        "workspace_openharness_parser", Path(config["openharness_parser"])
    )
    meta_path = Path(config["metadata_path"])
    meta = json.loads(meta_path.read_text())
    if meta != agent_visible_metadata(meta):
        raise RuntimeError("Evaluation metadata is visible before Agent execution")
    meta["__metadata_path"] = str(meta_path)

    def handoff(**kwargs: Any) -> dict[str, Any]:
        link_name = config.get("agent_logs_link")
        if link_name:
            logs = Path(kwargs["sandbox_dir"]) / "raw" / "harbor-agent"
            logs.mkdir(parents=True, exist_ok=True)
            link = Path(link_name)
            if link.is_symlink():
                link.unlink()
            elif link.exists():
                raise RuntimeError("Agent log indirection path is occupied")
            link.symlink_to(logs, target_is_directory=True)
        return wait_for_harbor(
            **kwargs,
            expected_instruction=Path(config["instruction_path"]),
            agent_logs=Path(config["agent_logs"]),
            parser=parser,
        )

    role_map = {meta["file_system"]: config["standard_work_dir"]}
    runs_root = (
        Path(config["output_dir"])
        / f"{config['agent_name']}--{config['model_name']}--{config['run_name']}"
    )
    result = native._run_one_case(
        idx=0,
        meta=meta,
        runs_root=str(runs_root),
        run_fn=handoff,
        prompt_head="",
        prompt_tail="",
        task_target_output_dir="model_output",
        timeout_sec=config["timeout_sec"],
        api_provider={"model": "deepseek-flash", "baseUrl": "https://api.deepseek.com"},
        eval_while_running=False,
        eval_yaml="",
        work_dir_map=role_map,
        standard_work_dir_map=role_map,
        agent_name=config["agent_name"],
        model_name=config["model_name"],
        isolated_workdir=True,
        task_workdir_cleanup="failed",
        prompt_language="auto",
    )
    write_json(runs_root / str(meta["id"]) / "native-runner-result.json", result)
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-config", type=Path, required=True)
    args = parser.parse_args()
    run_single_case(args.run_config)


if __name__ == "__main__":
    main()
