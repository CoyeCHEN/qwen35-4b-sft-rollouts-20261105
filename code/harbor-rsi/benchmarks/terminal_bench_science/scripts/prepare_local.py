"""Prepare a flat local Harbor dataset view of Terminal-Bench-Science.

The upstream release nests tasks three levels below ``tasks/``. Harbor's
local dataset loader intentionally scans direct children, so this helper
creates a disposable directory of symlinks without copying or modifying the
benchmark checkout.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

try:
    from .validate import inspect
except ImportError:  # Direct execution: python scripts/prepare_local.py ...
    from validate import inspect


def prepare(source: Path, destination: Path) -> dict[str, object]:
    source = source.resolve()
    destination = destination.resolve()
    metadata = inspect(source)
    task_paths = sorted((source / "tasks").glob("**/task.toml"))
    if (
        destination == source
        or destination.is_relative_to(source)
        or source.is_relative_to(destination)
    ):
        raise ValueError("staging destination must be outside the source checkout")
    names: set[str] = set()
    for task_file in task_paths:
        task_dir = task_file.parent
        task_name = task_dir.name
        if task_name in names:
            raise ValueError(f"duplicate task directory name: {task_name}")
        names.add(task_name)

    result = {
        **metadata,
        "source": str(source),
        "staging_path": str(destination),
        "task_names": sorted(names),
    }
    if destination.exists():
        marker = destination / "rsi-source.json"
        if not marker.is_file() or json.loads(marker.read_text()) != result:
            raise ValueError(
                f"refusing to replace existing staging directory: {destination}"
            )
        if {p.name for p in destination.iterdir()} != names | {"rsi-source.json"}:
            raise ValueError("staging directory contains unexpected entries")
        for task_file in task_paths:
            link = destination / task_file.parent.name
            if not link.is_symlink() or link.resolve() != task_file.parent:
                raise ValueError(f"invalid staged task: {link}")
        return result
    destination.mkdir(parents=True)
    for task_file in task_paths:
        (destination / task_file.parent.name).symlink_to(
            task_file.parent, target_is_directory=True
        )
    (destination / "rsi-source.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n"
    )
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(os.environ.get("SCIENCE_STAGING_DIR", "/tmp/rsi-science-dataset")),
    )
    args = parser.parse_args()
    print(json.dumps(prepare(args.source, args.output), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
