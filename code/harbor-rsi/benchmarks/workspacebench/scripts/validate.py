"""Validate the pinned WorkspaceBench checkout and Lite assets."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = json.loads((ROOT / "manifest.json").read_text(encoding="utf-8"))


def _git(root: Path, *args: str) -> str:
    return subprocess.check_output(
        ["git", "-C", str(root), *args], text=True, encoding="utf-8"
    ).strip()


def _task_asset_revision(task_root: Path) -> tuple[str, int]:
    records: list[tuple[str, str]] = []
    for path in sorted(item for item in task_root.rglob("*") if item.is_file()):
        records.append(
            (
                path.relative_to(task_root).as_posix(),
                hashlib.sha256(path.read_bytes()).hexdigest(),
            )
        )
    payload = json.dumps(records, separators=(",", ":")).encode()
    return "sha256:" + hashlib.sha256(payload).hexdigest(), len(records)


def inspect(source: Path, *, verify_assets: bool = True) -> dict[str, Any]:
    source = source.resolve()
    commit = _git(source, "rev-parse", "HEAD")
    expected_commit = str(MANIFEST["source_commit"])
    if commit != expected_commit:
        raise ValueError(f"expected commit {expected_commit}, found {commit}")

    remote = _git(source, "remote", "get-url", "origin")
    if "OpenDataBox/Workspace-Bench" not in remote:
        raise ValueError(f"unexpected origin: {remote}")

    evaluation = source / "evaluation"
    required_code = [
        evaluation / "scripts" / "build_run_config.py",
        evaluation / "scripts" / "run_isolated_benchmark.py",
        evaluation / "src" / "agent_runner.py",
        evaluation / "src" / "agent_eval.py",
        evaluation / "docker" / "docker-compose.yaml",
    ]
    missing_code = [str(path) for path in required_code if not path.is_file()]
    if missing_code:
        raise ValueError(f"missing upstream files: {missing_code}")

    task_root = evaluation / "tasks_lite"
    metadata_paths = sorted(task_root.glob("*/metadata.json"))
    expected_tasks = int(MANIFEST["task_count"])
    if len(metadata_paths) != expected_tasks:
        raise ValueError(
            f"expected {expected_tasks} Lite tasks, found {len(metadata_paths)}"
        )

    task_ids: set[str] = set()
    personas: dict[str, int] = {}
    rubric_count = 0
    missing_task_assets: list[str] = []
    for path in metadata_paths:
        value = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise ValueError(f"metadata must be an object: {path}")
        task_id = str(value.get("id") or path.parent.name)
        if task_id in task_ids:
            raise ValueError(f"duplicate task id: {task_id}")
        task_ids.add(task_id)
        persona = str(value.get("persona") or "unknown")
        personas[persona] = personas.get(persona, 0) + 1
        rubrics = value.get("rubrics")
        if isinstance(rubrics, list):
            rubric_count += len(rubrics)
        for item in value.get("data_manifest", []):
            if not isinstance(item, dict):
                continue
            stored = item.get("stored_relpath")
            if isinstance(stored, str) and not (path.parent / stored).is_file():
                missing_task_assets.append(f"{task_id}:{stored}")
    if missing_task_assets:
        raise ValueError(
            f"missing {len(missing_task_assets)} task asset(s): "
            + ", ".join(missing_task_assets[:5])
        )

    filesys = evaluation / "filesys"
    marker = (filesys / ".workspace_bench_language").read_text(encoding="utf-8").strip()
    if marker != MANIFEST["workspace_language"]:
        raise ValueError(
            f"expected workspace language {MANIFEST['workspace_language']}, found {marker}"
        )
    workspaces: dict[str, int | None] = {}
    for name in MANIFEST["workspace_directories"]:
        directory = filesys / name
        if not directory.is_dir():
            raise ValueError(f"missing workspace directory: {directory}")
        first_file = next(
            (path for path in directory.rglob("*") if path.is_file()), None
        )
        if first_file is None:
            raise ValueError(f"empty workspace directory: {directory}")
        workspaces[str(name)] = (
            sum(1 for path in directory.rglob("*") if path.is_file())
            if verify_assets
            else None
        )

    task_revision = None
    task_asset_files = None
    if verify_assets:
        task_revision, task_asset_files = _task_asset_revision(task_root)
        if task_revision != MANIFEST["task_asset_revision"]:
            raise ValueError(
                f"expected task asset revision {MANIFEST['task_asset_revision']}, "
                f"found {task_revision}"
            )
        if task_asset_files != MANIFEST["task_asset_files"]:
            raise ValueError(
                f"expected {MANIFEST['task_asset_files']} task asset files, "
                f"found {task_asset_files}"
            )

    return {
        "source_commit": commit,
        "source_repository": remote,
        "task_count": len(task_ids),
        "rubric_count": rubric_count,
        "personas": dict(sorted(personas.items())),
        "workspace_language": marker,
        "workspace_files": workspaces,
        "task_asset_revision": task_revision,
        "task_asset_files": task_asset_files,
        "assets_verified": verify_assets,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument(
        "--fast",
        action="store_true",
        help="Check structure and references without hashing all Lite task assets.",
    )
    args = parser.parse_args()
    print(
        json.dumps(
            inspect(args.source, verify_assets=not args.fast),
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
