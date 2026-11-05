from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "adapters" / "clawgym"))
from adapter import ClawGymAdapter, read_records


def _record(*, reward: str, include_rules: bool = False) -> dict:
    record = {
        "prompt": "Create the output file under build/result.txt.",
        "input_files": [
            {"file_path": "data/input.txt", "content": "source\n"},
            {"file_path": "reward/test.py", "content": reward},
        ],
        "hook_code": "python3 reward/test.py /workspace",
    }
    if include_rules:
        record["rules"] = [
            {
                "name": "result",
                "file_path": "build/result.txt",
                "scores": {"1": "correct"},
            }
        ]
    return record


def _write_dataset(tmp_path: Path, records: list[dict]) -> Path:
    path = tmp_path / "benchmark_data.jsonl"
    path.write_text(
        "".join(json.dumps(record) + "\n" for record in records), encoding="utf-8"
    )
    return path


def test_generates_standard_task_and_hides_reward(tmp_path: Path) -> None:
    reward = """
import sys
from pathlib import Path
workspace = Path(sys.argv[1])
score = 1.0 if (workspace / 'build' / 'result.txt').read_text().strip() == 'ok' else 0.0
print(score)
"""
    dataset = _write_dataset(tmp_path, [_record(reward=reward)])
    output = tmp_path / "dataset"
    task = ClawGymAdapter(output, dataset_path=dataset).generate()[0]

    assert (task / "instruction.md").read_text() == _record(reward=reward)[
        "prompt"
    ] + "\n"
    assert (
        task / "environment/agent_workspace/data/input.txt"
    ).read_text() == "source\n"
    assert not (task / "environment/agent_workspace/reward/test.py").exists()
    assert (task / "tests/official_reward.py").read_text() == reward
    config = (task / "task.toml").read_text()
    assert 'schema_version = "1.4"' in config
    assert 'environment_mode = "separate"' in config
    assert '"judge_request.json"' in config
    assert '"judge_response.json"' in config
    assert '"judge_error.json"' in config
    assert 'source = "/workspace"' in config
    assert "score_weight_code = 0.7" in config
    assert "score_weight_rubric = 0.3" in config
    assert 'CLAWGYM_JUDGE_MODEL = "${CLAWGYM_JUDGE_MODEL:-deepseek-flash}"' in config
    record = json.loads((task / "tests/record.json").read_text())
    assert record["hook_code"] == _record(reward=reward)["hook_code"]
    assert record["score_weights"] == {"code": 0.7, "rubric": 0.3}
    assert 'CMD ["sleep", "infinity"]' in (task / "environment/Dockerfile").read_text()
    assert 'CMD ["sleep", "infinity"]' in (task / "tests/Dockerfile").read_text()
    assert json.loads((output / "source_manifest.json").read_text())["task_count"] == 1
    from harbor.models.dataset.manifest import DatasetManifest
    from harbor.models.task.task import Task
    from harbor.publisher.packager import Packager

    manifest = DatasetManifest.from_toml_file(output / "dataset.toml")
    parsed = Task(task)
    digest, _ = Packager.compute_content_hash(task)
    assert manifest.tasks[0].name == parsed.name
    assert manifest.tasks[0].digest == f"sha256:{digest}"


def test_official_fixture_score_and_zero_are_distinct(tmp_path: Path) -> None:
    reward = """
import sys
from pathlib import Path
workspace = Path(sys.argv[1])
print(1.0 if (workspace / 'answer.txt').read_text().strip() == 'ok' else 0.0)
"""
    dataset = _write_dataset(tmp_path, [_record(reward=reward)])
    task = ClawGymAdapter(tmp_path / "dataset", dataset_path=dataset).generate()[0]
    verifier_root = tmp_path / "verifier"
    (verifier_root / "logs/verifier").mkdir(parents=True)
    (verifier_root / "workspace").mkdir()
    (verifier_root / "workspace/answer.txt").write_text("ok")
    for name in ("evaluate.py", "official_reward.py"):
        (verifier_root / name).write_bytes((task / "tests" / name).read_bytes())
    env = {
        "PATH": str(Path(sys.executable).parent),
        "HARBOR_VERIFIER_LOG_DIR": str(verifier_root / "logs/verifier"),
        "CLAWGYM_REWARD_SCRIPT": str(verifier_root / "official_reward.py"),
    }
    result = subprocess.run(
        [
            sys.executable,
            str(verifier_root / "evaluate.py"),
            str(verifier_root / "workspace"),
        ],
        cwd=verifier_root,
        env=env,
        check=False,
    )
    assert result.returncode == 0
    assert json.loads((verifier_root / "logs/verifier/reward.json").read_text()) == {
        "reward": 1.0
    }
    (verifier_root / "workspace/answer.txt").write_text("wrong")
    result = subprocess.run(
        [
            sys.executable,
            str(verifier_root / "evaluate.py"),
            str(verifier_root / "workspace"),
        ],
        cwd=verifier_root,
        env=env,
        check=False,
    )
    assert result.returncode == 0
    assert json.loads((verifier_root / "logs/verifier/reward.json").read_text()) == {
        "reward": 0.0
    }


def test_upstream_multiline_metric_parser_averages_top_level_only(
    tmp_path: Path,
) -> None:
    from runpy import run_path

    module = run_path(
        str(
            Path(__file__).resolve().parents[3]
            / "adapters/clawgym/task-template/tests/evaluate.py"
        )
    )
    parse = module["_parse"]
    score, metrics = parse(
        'prefix\n{\n "a": 1.0,\n "nested": {"ignored": 0.0}\n}\n', ""
    )
    assert score == 1.0
    assert metrics == {"a": 1.0, "nested": {"ignored": 0.0}}


def test_hybrid_without_judge_preserves_official_code_score_and_marks_incomplete(
    tmp_path: Path,
) -> None:
    reward = "import sys\nfrom pathlib import Path\nprint(1.0 if (Path(sys.argv[1]) / 'answer.txt').exists() else 0.0)\n"
    dataset = _write_dataset(tmp_path, [_record(reward=reward, include_rules=True)])
    task = ClawGymAdapter(tmp_path / "dataset", dataset_path=dataset).generate()[0]
    verifier_root = tmp_path / "hybrid-verifier"
    (verifier_root / "logs/verifier").mkdir(parents=True)
    (verifier_root / "workspace").mkdir()
    (verifier_root / "workspace/answer.txt").write_text("ok")
    for name in (
        "evaluate.py",
        "official_reward.py",
        "rubric_verifier.py",
        "record.json",
    ):
        (verifier_root / name).write_bytes((task / "tests" / name).read_bytes())
    env = {
        "PATH": str(Path(sys.executable).parent),
        "HARBOR_VERIFIER_LOG_DIR": str(verifier_root / "logs/verifier"),
        "CLAWGYM_REWARD_SCRIPT": str(verifier_root / "official_reward.py"),
    }
    result = subprocess.run(
        [
            sys.executable,
            str(verifier_root / "evaluate.py"),
            str(verifier_root / "workspace"),
        ],
        cwd=verifier_root,
        env=env,
        check=False,
    )
    assert result.returncode == 0
    payload = json.loads(
        (verifier_root / "logs/verifier/official_result.json").read_text()
    )
    assert payload["reward"] == 1.0
    assert payload["code_reward"] == 1.0
    assert payload["rubric_reward"]["reason"] == "judge not configured"
    assert payload["effective_score_mode"] == "code"
    assert payload["score_completeness"] == "incomplete"
    assert json.loads((verifier_root / "logs/verifier/reward.json").read_text()) == {
        "reward": 1.0
    }


def test_rejects_unsafe_input_and_unknown_task(tmp_path: Path) -> None:
    dataset = _write_dataset(tmp_path, [_record(reward="print(0)")])
    raw = json.loads(dataset.read_text().splitlines()[0])
    raw["input_files"][0]["file_path"] = "../secret"
    dataset.write_text(json.dumps(raw) + "\n")
    with pytest.raises(ValueError, match="unsafe"):
        read_records(dataset)
