"""Validate a checked-out Terminal-Bench-Science release before dispatch."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10 development hosts
    import tomli as tomllib
from pathlib import Path
from harbor.publisher.packager import Packager


EXPECTED_COMMIT = "f81afac4f11048e77a15dfc8fb1dbfb897fea0ce"
EXPECTED_TASKS = 70
EXPECTED_DATASET_REVISION = (
    "sha256:0341d617c95a01594ca934019010625e3e2d2636b51f95952b87bd7235818316"
)


def _git_commit(root: Path) -> str:
    return subprocess.check_output(
        ["git", "-C", str(root), "rev-parse", "HEAD"], text=True
    ).strip()


def classify_task(path: Path, config: dict) -> tuple[bool, list[str]]:
    """Return (uses_compose, non-main artifact services) for one task."""
    environment_dir = path / "environment"
    has_compose = any(
        (environment_dir / name).is_file()
        for name in ("docker-compose.yaml", "docker-compose.yml")
    )
    services: set[str] = set()
    entries = list(config.get("artifacts", []))
    verifier = config.get("verifier", {})
    entries.extend(verifier.get("artifacts", []))
    for entry in entries:
        if isinstance(entry, dict) and entry.get("service", "main") != "main":
            services.add(str(entry["service"]))
    return has_compose, sorted(services)


def inspect(root: Path) -> dict[str, object]:
    manifest = root / "tasks" / "dataset.toml"
    task_paths = sorted((root / "tasks").glob("**/task.toml"))
    if not manifest.is_file():
        raise ValueError(f"missing dataset manifest: {manifest}")
    if len(task_paths) != EXPECTED_TASKS:
        raise ValueError(f"expected {EXPECTED_TASKS} tasks, found {len(task_paths)}")
    with manifest.open("rb") as stream:
        dataset = tomllib.load(stream)
    task_manifest = sorted(
        (task["name"], task["digest"]) for task in dataset.get("tasks", [])
    )
    expected = dict(task_manifest)
    if len(expected) != EXPECTED_TASKS or len(task_manifest) != EXPECTED_TASKS:
        raise ValueError("manifest must declare 70 unique tasks")
    revision = (
        "sha256:"
        + hashlib.sha256(
            json.dumps(
                [
                    {"name": name, "content_sha256": digest}
                    for name, digest in task_manifest
                ],
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        ).hexdigest()
    )
    if revision != EXPECTED_DATASET_REVISION:
        raise ValueError(
            f"expected dataset revision {EXPECTED_DATASET_REVISION}, found {revision}"
        )

    gpu_tasks: list[str] = []
    compose_tasks: list[str] = []
    sidecar_tasks: dict[str, list[str]] = {}
    separate_verifiers = 0
    max_resources = {"cpus": 0, "memory_mb": 0, "storage_mb": 0}
    seen = set()
    for path in task_paths:
        with path.open("rb") as stream:
            config = tomllib.load(stream)
        task_name = config.get("task", {}).get("name", path.parent.name)
        if task_name in seen or task_name not in expected:
            raise ValueError(f"duplicate or undeclared task: {task_name}")
        seen.add(task_name)
        digest, _ = Packager.compute_content_hash(path.parent)
        if "sha256:" + digest != expected[task_name]:
            raise ValueError(f"task content differs from manifest: {task_name}")
        environment = config.get("environment", {})
        has_compose, services_for_task = classify_task(path.parent, config)
        if has_compose:
            compose_tasks.append(task_name)
        if services_for_task:
            sidecar_tasks[task_name] = services_for_task

        gpus = int(environment.get("gpus", 0) or 0)
        if gpus:
            gpu_tasks.append(task_name)
        for key in max_resources:
            max_resources[key] = max(
                max_resources[key], int(environment.get(key, 0) or 0)
            )
        if config.get("verifier", {}).get("environment_mode") == "separate":
            separate_verifiers += 1

    commit = _git_commit(root)
    if commit != EXPECTED_COMMIT:
        raise ValueError(f"expected commit {EXPECTED_COMMIT}, found {commit}")
    return {
        "source_commit": commit,
        "task_count": len(task_paths),
        "dataset_revision": revision,
        "gpu_tasks": gpu_tasks,
        "compose_tasks": sorted(compose_tasks),
        "sidecar_tasks": sidecar_tasks,
        "e2b_compatible_tasks": sorted(
            set(seen) - set(compose_tasks) - set(sidecar_tasks)
        ),
        "max_agent_resources": max_resources,
        "separate_verifiers": separate_verifiers,
        "content_hashes_verified": len(seen),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path, help="checkout of v0.1.0")
    args = parser.parse_args()
    print(json.dumps(inspect(args.source.resolve()), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
