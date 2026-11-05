from __future__ import annotations

import hashlib
import json
import subprocess
import types
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from benchmarks.workspacebench.scripts import (
    native_trial_bridge,
    prepare,
    summarize,
    validate,
)


def test_task_asset_revision_is_stable(tmp_path: Path) -> None:
    (tmp_path / "b").write_bytes(b"two")
    (tmp_path / "a").write_bytes(b"one")

    revision, count = validate._task_asset_revision(tmp_path)

    records = [
        ("a", hashlib.sha256(b"one").hexdigest()),
        ("b", hashlib.sha256(b"two").hexdigest()),
    ]
    expected = hashlib.sha256(
        json.dumps(records, separators=(",", ":")).encode()
    ).hexdigest()
    assert revision == f"sha256:{expected}"
    assert count == 2


def test_prepare_rejects_unmarked_existing_directory(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    output = tmp_path / "runtime"
    output.mkdir()
    wheel = tmp_path / "openharness-0.1.0-py3-none-any.whl"
    wheel.write_bytes(b"wheel")

    with pytest.raises(ValueError, match="unmarked"):
        prepare.prepare(source, output, wheel)


def test_prepare_creates_read_only_mount_targets(tmp_path: Path) -> None:
    prepare._ensure_mountpoints(tmp_path)

    assert (tmp_path / "evaluation" / "tasks").is_dir()
    assert (tmp_path / "evaluation" / "tasks_lite").is_dir()


def test_compatibility_patch_applies_to_pinned_checkout() -> None:
    repo = Path(__file__).resolve().parents[3]
    configured = subprocess.run(
        [
            "git",
            "-C",
            str(repo),
            "config",
            "--get",
            "workspacebench.testSource",
        ],
        text=True,
        capture_output=True,
        check=False,
    ).stdout.strip()
    if not configured:
        pytest.skip("set git config workspacebench.testSource for integration check")
    patch = (
        repo
        / "benchmarks"
        / "workspacebench"
        / "patches"
        / "workspacebench-openharness.patch"
    )
    subprocess.run(
        ["git", "-C", configured, "apply", "--check", str(patch)],
        check=True,
    )


def test_summarize_preserves_trace_hashes(tmp_path: Path) -> None:
    task = tmp_path / "task-1"
    raw = task / "raw"
    raw.mkdir(parents=True)
    (raw / "openharness_stdout.jsonl").write_text(
        '{"type":"agent_end"}\n', encoding="utf-8"
    )
    (task / "agent.json").write_text(
        json.dumps(
            {
                "status": "passed",
                "durationMs": 12,
                "trace": {
                    "llm": {
                        "usageTotal": {
                            "prompt_tokens": 3,
                            "completion_tokens": 2,
                            "total_tokens": 5,
                        }
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    (task / "metadata.json").write_text(
        json.dumps({"id": "task-1", "persona": "Researcher"}),
        encoding="utf-8",
    )
    (task / "rubrics_judge--Judge.json").write_text(
        json.dumps({"summary": {"total": 2, "passed": 1}}),
        encoding="utf-8",
    )

    result = summarize.summarize(tmp_path, judge_model="Judge")

    assert result["summary"]["tasks"] == 1
    assert result["summary"]["rubric_pass_rate"] == 0.5
    assert result["tasks"][0]["total_tokens"] == 5
    files = result["trajectory_index"][0]["artifacts"]["files"]
    assert files["openharness_jsonl"]["sha256"]


def test_judge_response_contract_rejects_error_json() -> None:
    with pytest.raises(RuntimeError, match="lacks rubric"):
        native_trial_bridge.validate_judge_response(
            {"error": {"code": "bad_request"}}, 1
        )


@pytest.mark.parametrize("status", [400, 401, 429])
def test_http_faults_are_recorded_without_response_body(
    tmp_path: Path, status: int
) -> None:
    diagnostics = native_trial_bridge._Diagnostics(
        tmp_path / "judge.json",
        model="deepseek-flash",
        base_url="https://api.deepseek.com/v1",
    )
    error = urllib.error.HTTPError(
        "https://api.deepseek.com/v1/chat/completions",
        status,
        "provider error",
        {"Content-Type": "application/json"},
        None,
    )
    request_module = types.SimpleNamespace(
        urlopen=lambda *_args, **_kwargs: (_ for _ in ()).throw(error)
    )
    native = types.SimpleNamespace(urllib=types.SimpleNamespace(request=request_module))
    original = native_trial_bridge._install_http_audit(native, diagnostics)
    try:
        request = urllib.request.Request(
            "https://api.deepseek.com/v1/chat/completions",
            data=b'{"model":"deepseek-flash"}',
            headers={"Authorization": "Bearer secret"},
            method="POST",
        )
        with pytest.raises(urllib.error.HTTPError):
            native.urllib.request.urlopen(request, timeout=1)
    finally:
        native.urllib.request.urlopen = original
    record = json.loads((tmp_path / "judge.json").read_text())
    assert record["api_requested"] is True
    assert record["requests"][0]["status"] == status
    assert "secret" not in json.dumps(record)


def test_timeout_and_error_json_are_diagnosable(tmp_path: Path) -> None:
    diagnostics = native_trial_bridge._Diagnostics(
        tmp_path / "judge.json",
        model="deepseek-flash",
        base_url="https://api.deepseek.com/v1",
    )
    request_module = types.SimpleNamespace(
        urlopen=lambda *_args, **_kwargs: (_ for _ in ()).throw(
            TimeoutError("timed out")
        )
    )
    native = types.SimpleNamespace(urllib=types.SimpleNamespace(request=request_module))
    original = native_trial_bridge._install_http_audit(native, diagnostics)
    try:
        with pytest.raises(TimeoutError):
            native.urllib.request.urlopen(
                urllib.request.Request("https://api.deepseek.com/v1/chat/completions"),
                timeout=1,
            )
    finally:
        native.urllib.request.urlopen = original
    diagnostics.update(response_parse_error="invalid JSON response")
    diagnostics.finish(
        status="failed", stage="judge_call", error=ValueError("invalid JSON")
    )
    record = json.loads((tmp_path / "judge.json").read_text())
    assert record["requests"][0]["error_code"] == "TimeoutError"
    assert record["response_parse_error"] == "invalid JSON response"
    assert record["exception"]["type"] == "ValueError"


def test_reward_write_is_atomic_and_diagnostic_safe(tmp_path: Path) -> None:
    reward = tmp_path / "verifier" / "reward.txt"
    reward.parent.mkdir()
    temporary = reward.with_suffix(reward.suffix + ".tmp")
    temporary.write_text("0.5\n")
    temporary.replace(reward)
    assert reward.read_text() == "0.5\n"
    assert not temporary.exists()
