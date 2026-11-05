from __future__ import annotations

import json

from benchmarks.terminal_bench_science.scripts import prepare_local


def test_prepare_local_creates_flat_symlink_view(tmp_path, monkeypatch):
    source = tmp_path / "source"
    task_a = source / "tasks" / "domain" / "field" / "task-a"
    task_b = source / "tasks" / "other" / "field" / "task-b"
    task_a.mkdir(parents=True)
    task_b.mkdir(parents=True)
    (task_a / "task.toml").write_text("[task]\nname = 'task-a'\n")
    (task_b / "task.toml").write_text("[task]\nname = 'task-b'\n")
    destination = tmp_path / "staging"
    monkeypatch.setattr(
        prepare_local,
        "inspect",
        lambda _: {
            "source_commit": "a" * 40,
            "task_count": 2,
            "dataset_revision": "sha256:" + "b" * 64,
        },
    )

    result = prepare_local.prepare(source, destination)

    assert result["task_names"] == ["task-a", "task-b"]
    assert (destination / "task-a").is_symlink()
    assert (destination / "task-a" / "task.toml").read_text().startswith("[task]")
    assert json.loads((destination / "rsi-source.json").read_text())["task_count"] == 2


def test_inspect_classifies_compose_and_sidecar_tasks(tmp_path, monkeypatch):
    from benchmarks.terminal_bench_science.scripts.validate import classify_task

    plain = tmp_path / "plain"
    compose = tmp_path / "compose"
    sidecar = tmp_path / "sidecar"
    for task in (plain, compose, sidecar):
        (task / "environment").mkdir(parents=True)
    (compose / "environment" / "docker-compose.yaml").write_text("services: {}\n")
    assert classify_task(plain, {}) == (False, [])
    assert classify_task(compose, {}) == (True, [])
    assert classify_task(
        sidecar, {"artifacts": [{"source": "/x", "service": "broker"}]}
    ) == (False, ["broker"])
