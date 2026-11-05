"""Readiness is evidence, not a replacement for native Harbor execution."""

import hashlib
import json
from pathlib import Path

import pytest

from adapters.clawgym.adapter import ClawGymAdapter, verifier_requirements
from benchmarks.readiness.audit import dockerfile_images, job_config
from benchmarks.readiness.fetch_jobbench import source_path, verify
from benchmarks.readiness.collect_evidence import verifier_evidence
from harbor.models.job.config import DatasetConfig, JobConfig
from harbor.models.task.task import Task
from harbor.publisher.packager import Packager
from harbor.tasks.client import TaskClient


def test_source_paths_cannot_escape_root(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="Unsafe source path"):
        source_path(tmp_path, "../other/input")
    assert source_path(tmp_path, "dataset/task1/task_folder/input").is_relative_to(
        tmp_path
    )


def test_zero_reward_does_not_prove_pytest_executed(tmp_path: Path) -> None:
    logs = tmp_path / "verifier"
    logs.mkdir()
    (logs / "reward.txt").write_text("0\n")
    (logs / "test-stdout.txt").write_text(
        "failed to download uv\nuvx: command not found\n"
    )
    status, proof = verifier_evidence(tmp_path, "tb21")
    assert status == "dependency_failure" and not proof["pytest_executed"]
    (logs / "ctrf.json").write_text(
        json.dumps({"results": {"summary": {"tests": 4, "failed": 4, "passed": 0}}})
    )
    assert verifier_evidence(tmp_path, "tb21")[0] == "complete"


def test_multistage_images_keep_exact_tags_and_resolve_build_args() -> None:
    assert dockerfile_images(
        "ARG BASE=python:3.12-slim\nFROM --platform=linux/amd64 ${BASE} AS build\n"
        "FROM build AS tools\nFROM ${UNKNOWN}\nFROM scratch\n"
    ) == [
        ("python:3.12-slim", "from"),
        ("build", "internal_stage"),
        ("${UNKNOWN}", "unresolved"),
        ("scratch", "internal_stage"),
    ]


def test_checker_dependencies_are_declared_only_in_separate_verifier(
    tmp_path: Path,
) -> None:
    assert verifier_requirements("import json\nfrom yaml import safe_load\n") == [
        "PyYAML==6.0.3"
    ]
    assert verifier_requirements("import json\n") == []
    source = tmp_path / "data.jsonl"
    source.write_text(
        json.dumps(
            {
                "prompt": "Write config.",
                "hook_code": "python3 reward/test.py /workspace",
                "input_files": [
                    {
                        "file_path": "reward/test.py",
                        "content": "import yaml\nprint(0)\n",
                    }
                ],
            }
        )
        + "\n"
    )
    task = ClawGymAdapter(tmp_path / "tasks", dataset_path=source).generate()[0]
    assert (task / "tests/verifier-requirements.txt").read_text() == "PyYAML==6.0.3\n"
    assert "pip install" in (task / "tests/Dockerfile").read_text()
    assert "PyYAML" not in (task / "environment/Dockerfile").read_text()
    assert (task / "tests/official_reward.py").read_text() == "import yaml\nprint(0)\n"


@pytest.mark.parametrize("lfs", [True, False])
def test_official_source_identity_rejects_corruption(lfs: bool) -> None:
    data = b"official fixture\n"
    entry = {
        "path": "dataset/profession/task1/task_folder/input",
        "size": len(data),
        "oid": hashlib.sha1(f"blob {len(data)}\0".encode() + data).hexdigest(),
    }
    if lfs:
        entry["lfs"] = {"oid": hashlib.sha256(data).hexdigest()}
    verify(data, entry)
    with pytest.raises(ValueError, match="identity mismatch"):
        verify(data.upper(), entry)
    with pytest.raises(ValueError, match="size mismatch"):
        verify(data[:-1], entry)


async def test_full_clawgym_conversion_is_deterministic_and_native_selectable(
    tmp_path: Path,
) -> None:
    records = [
        {
            "prompt": f"Write result {n}.",
            "input_files": [
                {"file_path": "input.txt", "content": str(n)},
                {"file_path": "reward/test.py", "content": "print(0)\n"},
            ],
            "hook_code": "python3 reward/test.py /workspace",
            "rules": []
            if n % 2
            else [{"file_path": "result.txt", "scores": {"1": "correct"}}],
        }
        for n in range(200)
    ]
    source = tmp_path / "benchmark_data.jsonl"
    source.write_text("".join(json.dumps(r) + "\n" for r in records))
    first = ClawGymAdapter(tmp_path / "first", dataset_path=source).generate()
    second = ClawGymAdapter(tmp_path / "second", dataset_path=source).generate()
    assert len(first) == len(second) == 200
    assert len({Task(p).name for p in first}) == 200
    assert [Packager.compute_content_hash(p)[0] for p in first] == [
        Packager.compute_content_hash(p)[0] for p in second
    ]
    dataset = DatasetConfig(path=tmp_path / "first")
    configs = await dataset.get_task_configs()
    parsed = await TaskClient().download_tasks([c.get_task_id() for c in configs])
    assert len(parsed.results) == 200
    selected = await DatasetConfig(
        path=tmp_path / "first", task_names=[first[137].name]
    ).get_task_configs()
    assert len(selected) == 1 and selected[0].path == first[137]


@pytest.mark.parametrize(
    "benchmark", ["alfworld", "clawgym", "tb21", "jobbench-main", "jobbench-easy"]
)
def test_full_configs_use_native_dataset_and_no_automatic_paid_agent(
    benchmark: str, tmp_path: Path
) -> None:
    config = JobConfig.model_validate(job_config(benchmark, tmp_path))
    assert len(config.datasets) == 1
    assert not config.tasks
    assert config.datasets[0].n_tasks is None
    assert config.agents[0].name == "nop"
    assert config.n_concurrent_trials == 1
    assert config.retry.max_retries == 0
    assert config.environment.delete
    assert config.environment.kwargs.get("metadata_backend") is None


def test_nonzero_hook_keeps_raw_reward_and_incomplete_evidence(tmp_path: Path) -> None:
    import subprocess
    import sys

    source = tmp_path / "data.jsonl"
    source.write_text(
        json.dumps(
            {
                "prompt": "Write result.",
                "hook_code": "python3 reward/test.py /workspace",
                "input_files": [
                    {
                        "file_path": "reward/test.py",
                        "content": "print(0.5)\nraise SystemExit(1)\n",
                    }
                ],
            }
        )
        + "\n"
    )
    task = ClawGymAdapter(tmp_path / "tasks", dataset_path=source).generate()[0]
    logs = tmp_path / "logs"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    result = subprocess.run(
        [sys.executable, str(task / "tests/evaluate.py"), str(workspace)],
        env={
            "PATH": str(Path(sys.executable).parent),
            "HARBOR_VERIFIER_LOG_DIR": str(logs),
            "CLAWGYM_REWARD_SCRIPT": str(task / "tests/official_reward.py"),
            "CLAWGYM_RECORD_PATH": str(task / "tests/record.json"),
        },
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0
    assert json.loads((logs / "reward.json").read_text()) == {"reward": 0.5}
    report = json.loads((logs / "official_result.json").read_text())
    assert report["official_returncode"] == 1
    assert report["score_completeness"] == "incomplete"
