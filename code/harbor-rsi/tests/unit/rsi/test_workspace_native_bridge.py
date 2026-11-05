import importlib.util
import json
import threading
import time
from pathlib import Path

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[3]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


bridge = load(
    "workspace_trial_bridge",
    ROOT / "benchmarks/workspacebench/scripts/native_trial_bridge.py",
)
parser = load(
    "workspace_cli_parser",
    ROOT / "benchmarks/workspacebench/overlay/evaluation/src/agents/openharness.py",
)


@pytest.mark.parametrize(
    "response",
    [
        {},
        {"rubrics": [{"index": 0, "passed": False}]},
        {"rubrics": [{"index": 0, "passed": True}, {"index": 0, "passed": False}]},
        {"rubrics": [{"index": 0, "passed": "false"}, {"index": 1, "passed": True}]},
        {"rubrics": [{"index": False, "passed": True}, {"index": 1, "passed": True}]},
    ],
)
def test_incomplete_or_coerced_judge_output_is_not_a_score(response):
    with pytest.raises(RuntimeError):
        bridge.validate_judge_response(response, 2)


def test_complete_zero_score_is_valid():
    bridge.validate_judge_response(
        {"rubrics": [{"index": 1, "passed": False}, {"index": 0, "passed": False}]}, 2
    )


def test_metadata_hides_grading_fields_preserving_task_inputs():
    meta = {"task": "original", "data_manifest": [{"filename": "a.txt"}]}
    private = {
        "rubrics": ["secret"],
        "rubric_types": [],
        "judge_metadata": {},
        "ground_truth_x": 1,
    }
    assert bridge.agent_visible_metadata({**meta, **private}) == meta


def test_native_handoff_preserves_cli_trace_and_zero_exit(tmp_path):
    instruction = tmp_path / "instruction.md"
    instruction.write_text("Exact native prompt")
    logs = tmp_path / "agent"
    logs.mkdir()
    case = tmp_path / "case"
    message = {
        "role": "assistant",
        "timestamp": 1700000000000,
        "content": [{"type": "text", "text": "['model_output/report\u2028.txt']"}],
        "usage": {"input": 7, "output": 3, "cacheRead": 2},
    }
    event = {"type": "agent_end", "messages": [message]}

    def complete():
        deadline = time.monotonic() + 5
        while not (case / "raw/harbor-ready.json").exists():
            if time.monotonic() > deadline:
                return
            time.sleep(0.01)
        (logs / "open-harness.stdout.jsonl").write_text(
            json.dumps(event, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        (logs / "open-harness.stderr.log").write_text("")
        bridge.write_json(
            logs / "open-harness.complete.json",
            {"identity": "this-trial", "exit_code": 0},
        )

    thread = threading.Thread(target=complete)
    thread.start()
    try:
        result = bridge.wait_for_harbor(
            prompt=instruction.read_text(),
            work_dir=str(case / "workdir"),
            sandbox_dir=str(case),
            timeout_s=5,
            api_provider={
                "model": "deepseek-flash",
                "baseUrl": "https://api.deepseek.com",
            },
            expected_instruction=instruction,
            agent_logs=logs,
            parser=parser,
        )
    finally:
        thread.join(timeout=5)
    assert result["status"] == "ok"
    assert result["trace"]["lastText"] == "['model_output/report\u2028.txt']"
    assert result["trace"]["usageTotal"]["prompt_tokens"] == 9
    assert (case / "raw/openharness_stdout.jsonl").read_bytes() == (
        logs / "open-harness.stdout.jsonl"
    ).read_bytes()
    with pytest.raises(RuntimeError, match="prior Harbor completion"):
        bridge.wait_for_harbor(
            prompt=instruction.read_text(),
            work_dir=str(case / "workdir"),
            sandbox_dir=str(case),
            timeout_s=5,
            api_provider={},
            expected_instruction=instruction,
            agent_logs=logs,
            parser=parser,
        )


def test_native_guard_failure_never_emits_reward(tmp_path, monkeypatch):
    monkeypatch.setenv("JUDGE_DIAGNOSTICS_PATH", str(tmp_path / "judge.json"))
    monkeypatch.setenv("JUDGE_API_BASE", "http://judge.invalid/v1")
    monkeypatch.setenv("JUDGE_MODEL", "deterministic-stub")
    monkeypatch.setenv("JUDGE_API_KEY", "test-secret")
    config = tmp_path / "run.yaml"
    config.write_text(yaml.safe_dump({"output_dir": str(tmp_path)}))
    bridge.write_json(tmp_path / "native-entry-exit.json", {"exit_code": 124})
    reward = tmp_path / "reward.txt"
    with pytest.raises(RuntimeError, match="isolation guard failed"):
        bridge.verify_single_case(config, tmp_path / "metadata.json", reward)
    assert not reward.exists()


def test_valid_zero_judge_reward_and_temporary_credentials(tmp_path, monkeypatch):
    monkeypatch.setenv("JUDGE_DIAGNOSTICS_PATH", str(tmp_path / "judge.json"))
    config = {
        "output_dir": str(tmp_path / "native"),
        "agent_name": "OpenHarness",
        "model_name": "DeepSeek-Flash",
        "run_name": "test",
        "native_src": str(tmp_path / "source"),
    }
    path = tmp_path / "run.yaml"
    path.write_text(yaml.safe_dump(config))
    root = Path(config["output_dir"])
    case = root / "OpenHarness--DeepSeek-Flash--test/3"
    bridge.write_json(root / "native-entry-exit.json", {"exit_code": 0})
    bridge.write_json(case / "agent.json", {"runnerStatus": "ok", "status": "failed"})
    metadata = tmp_path / "metadata.json"
    bridge.write_json(metadata, {"id": "3", "rubrics": ["original rubric"]})
    monkeypatch.setenv("JUDGE_API_BASE", "https://api.deepseek.com/v1")
    monkeypatch.setenv("JUDGE_API_KEY", "test-secret")
    monkeypatch.setenv("JUDGE_MODEL", "deepseek-flash")
    temporary_paths = []

    def judge(source, actual_case, actual_meta, judge_config, diagnostics):
        assert actual_case == case
        assert actual_meta == metadata
        assert yaml.safe_load(judge_config.read_text())["apiKey"] == "test-secret"
        temporary_paths.append(judge_config)
        return 0.0

    monkeypatch.setattr(bridge, "judge_single_case", judge)
    reward = tmp_path / "reward.txt"
    assert bridge.verify_single_case(path, metadata, reward) == 0.0
    assert reward.read_text() == "0.0\n"
    assert not temporary_paths[0].exists()
