"""Create the release input for ``frozen_harbor.py`` from explicit artifacts.

This only records a fixed evaluation plan. It does not dispatch or retry Jobs.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import subprocess
import sys
import zipfile
from pathlib import Path
from typing import Any, cast


MODULES = {
    "harbor": [
        "harbor",
        "harbor.cli.main",
        "harbor.cli.jobs",
        "harbor.job",
        "harbor.trial.trial",
        "harbor.trial.single_step",
        "harbor.trial.agent_lifecycle",
        "harbor.agents.installed.open_harness",
        "harbor.verifier.verifier",
        "harbor.environments.e2b_resumable",
    ],
    "harbor-remote-docker": [
        "harbor_remote_docker",
        "harbor_remote_docker.environment",
        "harbor_remote_docker.transport",
    ],
}


def source_tasks(source: dict[str, Any]) -> list[dict[str, Any]]:
    """Verify an explicit complete source list, including older 4x10 lists."""
    tasks = []
    for benchmark, group in source["benchmarks"].items():
        selected = group["tasks"]
        if not selected or len(selected) != group.get("expected_count", len(selected)):
            raise ValueError(f"Incomplete frozen source group: {benchmark}")
        for task in selected:
            item = {**task, "benchmark": benchmark}
            if not Path(item["path"]).is_dir():
                raise FileNotFoundError(item["path"])
            for file in cast(list[dict[str, Any]], item["files"]):
                path = Path(item["path"]) / file["path"]
                if sha256(path) != file["sha256"]:
                    raise ValueError(f"Source task manifest mismatch: {path}")
            tasks.append(item)
    if len({task["task_id"] for task in tasks}) != len(tasks):
        raise ValueError("Frozen Task IDs must be globally unique")
    if len({str(Path(task["path"]).resolve()) for task in tasks}) != len(tasks):
        raise ValueError("Frozen task paths must be unique")
    return tasks


def config_task_paths(config: dict[str, Any]) -> list[Path]:
    from harbor.job import Job
    from harbor.models.job.config import JobConfig

    configs = asyncio.run(Job._resolve_task_configs(JobConfig.model_validate(config)))
    if any(c.path is None for c in configs):
        raise ValueError("Freeze remote sources as local native Tasks before execution")
    return [Path(c.path).resolve() for c in configs if c.path is not None]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def wheel_identity(path: Path, package: str) -> dict[str, Any]:
    prefix = package.replace("-", "_")
    with zipfile.ZipFile(path) as archive:
        metadata = next(
            n for n in archive.namelist() if n.endswith(".dist-info/METADATA")
        )
        version = next(
            line.removeprefix("Version: ")
            for line in archive.read(metadata).decode().splitlines()
            if line.startswith("Version: ")
        )
        modules = {}
        for module in MODULES[package]:
            member = module.replace(".", "/")
            if module in ("harbor", "harbor_remote_docker"):
                member += "/__init__.py"
            else:
                member += ".py"
            modules[module] = hashlib.sha256(archive.read(member)).hexdigest()
    return {
        "version": version,
        "wheel_path": str(path.resolve()),
        "wheel_sha256": sha256(path),
        "modules": modules,
        "package_prefix": prefix,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--python", type=Path, required=True)
    parser.add_argument("--harbor-wheel", type=Path, required=True)
    parser.add_argument("--provider-wheel", type=Path, required=True)
    parser.add_argument("--harness-wheel", type=Path, required=True)
    parser.add_argument("--task-manifest", type=Path, required=True)
    parser.add_argument("--config", type=Path, action="append", required=True)
    parser.add_argument("--controller-lock", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--max-concurrent-trials", type=int, default=1)
    args = parser.parse_args()

    source = json.loads(args.task_manifest.read_text())
    tasks = source_tasks(source)
    by_path = {str(Path(task["path"]).resolve()): task for task in tasks}

    configs = {}
    planned = set()
    for path in args.config:
        path = path.resolve()
        config = json.loads(path.read_text())
        chosen = [by_path[str(p)] for p in config_task_paths(config)]
        concurrency = config.get("n_concurrent_trials", 1)
        if not 1 <= concurrency <= args.max_concurrent_trials:
            raise ValueError(f"Config exceeds explicit concurrency cap: {path}")
        benchmarks = {task["benchmark"] for task in chosen}
        if len(benchmarks) != 1:
            raise ValueError(f"Config must target one benchmark: {path}")
        benchmark = benchmarks.pop()
        ids = [task["task_id"] for task in chosen]
        if len(ids) != len(set(ids)):
            raise ValueError(f"Duplicate Task IDs: {path}")
        for task_id in ids:
            key = (benchmark, task_id)
            if key in planned:
                raise ValueError(f"Task planned in more than one Job: {key}")
            planned.add(key)
        agent = config["agents"][0]
        kwargs = agent["kwargs"]
        if Path(kwargs["wheel_path"]).resolve() != args.harness_wheel.resolve():
            raise ValueError(f"Harness wheel path differs: {path}")
        if kwargs["wheel_sha256"] != sha256(args.harness_wheel):
            raise ValueError(f"Harness wheel hash differs: {path}")
        configs[str(path)] = {
            "sha256": sha256(path),
            "benchmark": benchmark,
            "task_ids": ids,
            "n_concurrent_trials": concurrency,
            "benchmark_revision": source["benchmarks"][benchmark]["protocol"],
            "judge_identity": {
                "official": bool(source["benchmarks"][benchmark]["judge_official"]),
                "model": config.get("verifier", {}).get("env", {}).get("JUDGE_MODEL"),
                "revision": source["benchmarks"][benchmark]["protocol"].get(
                    "judge_revision"
                ),
            },
            "model_identity": {
                "model": agent["model_name"],
                "profile": kwargs.get("profile"),
                "thinking": kwargs.get("thinking"),
                "max_tokens": kwargs.get("max_tokens"),
            },
            "environment_identity": {
                "import_path": config["environment"].get("import_path"),
                "config_sha256": sha256(path),
            },
        }
    expected = {(task["benchmark"], task["task_id"]) for task in tasks}
    if planned != expected:
        raise ValueError(
            f"Plan does not cover frozen tasks: missing={expected - planned}"
        )

    commit = subprocess.check_output(
        ["git", "-C", str(args.repo), "rev-parse", "HEAD"], text=True
    ).strip()
    inventory = json.loads(
        subprocess.check_output(
            [
                str(args.python.absolute()),
                "-s",
                "-c",
                "import importlib.metadata as m, json; "
                "print(json.dumps(sorted((d.metadata['Name'].lower(), d.version) "
                "for d in m.distributions())))",
            ],
            text=True,
        )
    )
    manifest = {
        "schema_version": "frozen-harbor-release-v1",
        "repo_path": str(args.repo.resolve()),
        "git_commit": commit,
        "python": str(args.python.absolute()),
        "venv_path": str(args.python.absolute().parent.parent),
        "dependency_inventory": inventory,
        "packages": {
            "harbor": wheel_identity(args.harbor_wheel, "harbor"),
            "harbor-remote-docker": wheel_identity(
                args.provider_wheel, "harbor-remote-docker"
            ),
        },
        "open_harness": {
            "wheel_path": str(args.harness_wheel.resolve()),
            "wheel_sha256": sha256(args.harness_wheel),
            "cli_entry": "open-harness = cli:main",
        },
        "source_task_manifest": {
            "path": str(args.task_manifest.resolve()),
            "sha256": sha256(args.task_manifest),
        },
        "controller_lock": str(args.controller_lock.resolve()),
        "max_concurrent_trials": args.max_concurrent_trials,
        "tasks": tasks,
        "configs": configs,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(manifest, indent=2) + "\n")
    print(
        f"Frozen {len(tasks)} tasks in {len(configs)} native Harbor Jobs: {args.output}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
