"""Release validation reuses native selection for complete datasets."""

import hashlib
from pathlib import Path
import shutil

import pytest

from scripts.create_frozen_manifest import config_task_paths, source_tasks


def test_freeze_supports_complete_non_ten_task_groups_and_detects_tampering(
    tmp_path: Path,
) -> None:
    tasks = []
    for n in range(13):
        path = tmp_path / str(n)
        path.mkdir()
        (path / "instruction.md").write_text(f"task {n}")
        tasks.append(
            {
                "task_id": f"arbitrary/task-{n}",
                "path": str(path),
                "files": [
                    {
                        "path": "instruction.md",
                        "sha256": hashlib.sha256(
                            (path / "instruction.md").read_bytes()
                        ).hexdigest(),
                    }
                ],
            }
        )
    source = {"benchmarks": {"arbitrary-split": {"expected_count": 13, "tasks": tasks}}}
    assert len(source_tasks(source)) == 13
    (tmp_path / "5/instruction.md").write_text("corrupt")
    with pytest.raises(ValueError, match="Source task manifest mismatch"):
        source_tasks(source)


def test_freeze_rejects_incomplete_group_and_cross_group_id_collision(
    tmp_path: Path,
) -> None:
    task = {"task_id": "same-id", "path": str(tmp_path), "files": []}
    with pytest.raises(ValueError, match="Incomplete frozen source group"):
        source_tasks({"benchmarks": {"a": {"expected_count": 2, "tasks": [task]}}})
    with pytest.raises(ValueError, match="globally unique"):
        source_tasks({"benchmarks": {"a": {"tasks": [task]}, "b": {"tasks": [task]}}})


def test_release_native_dataset_resolution_includes_every_task(tmp_path: Path) -> None:
    template = Path(__file__).resolve().parents[3] / "examples/tasks/hello-world"
    for n in range(3):
        shutil.copytree(template, tmp_path / f"fixture-{n}")
    base = {"agents": [{"name": "nop"}], "datasets": [{"path": str(tmp_path)}]}
    assert sorted(config_task_paths(base)) == sorted(tmp_path.iterdir())
    base["datasets"][0]["task_names"] = ["fixture-1"]
    assert config_task_paths(base) == [tmp_path / "fixture-1"]
    assert config_task_paths(
        {"agents": [{"name": "nop"}], "tasks": [{"path": str(tmp_path / "fixture-2")}]}
    ) == [tmp_path / "fixture-2"]
