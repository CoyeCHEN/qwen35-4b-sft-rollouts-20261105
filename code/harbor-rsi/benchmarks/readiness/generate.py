"""Convert frozen sources with existing adapters, then export immutable TB tasks."""

import argparse
import asyncio
import hashlib
import json
import subprocess
from pathlib import Path

from adapters.clawgym.adapter import ClawGymAdapter
from benchmarks.jobbench.src.jobbench_e2b.adapter import run as convert_jobbench
from benchmarks.readiness.fetch_jobbench import (
    REVISION,
    selected_entries,
    source_path,
    verify,
)
from harbor.models.trial.config import TaskConfig
from harbor.tasks.client import TaskClient

CLAWGYM_SHA256 = "b2fede029e73a769ad294089a735108be4396294590ec00c9527ac60b1da0f72"


async def export_terminal_tasks(manifest: Path, output: Path) -> None:
    entries = json.loads(manifest.read_text())
    if len(entries) != 89 or len({x["name"] for x in entries}) != 89:
        raise ValueError("Frozen Terminal-Bench 2.1 list must contain 89 unique tasks")
    configs = [TaskConfig.model_validate(x) for x in entries]
    if any(not c.ref or not c.ref.startswith("sha256:") for c in configs):
        raise ValueError("Every TB task must be content pinned")
    client = TaskClient()
    # Bound preparation traffic to the public registry; execution still uses
    # native Job concurrency, and the native client owns downloads/cache.
    for start in range(0, len(configs), 8):
        await client.download_tasks(
            [c.get_task_id() for c in configs[start : start + 8]],
            output_dir=output,
            export=True,
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--alfworld-python", required=True)
    parser.add_argument("--alfworld-data", type=Path, required=True)
    parser.add_argument("--clawgym-data", type=Path, required=True)
    parser.add_argument("--jobbench-source", type=Path, required=True)
    parser.add_argument("--jobbench-tree", type=Path, required=True)
    parser.add_argument("--tb-manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists() and any(args.output.iterdir()):
        raise ValueError(
            "Use a new empty output directory; historical datasets are immutable"
        )
    if hashlib.sha256(args.clawgym_data.read_bytes()).hexdigest() != CLAWGYM_SHA256:
        raise ValueError("ClawGym source does not match the official frozen revision")
    downloaded = json.loads((args.jobbench_source / "source-download.json").read_text())
    if downloaded["revision"] != REVISION or any(
        x["status"] == "blocked" for x in downloaded["results"]
    ):
        raise ValueError(
            "JobBench source download is incomplete or uses the wrong revision"
        )
    for entry in selected_entries(args.jobbench_tree):
        verify(source_path(args.jobbench_source, entry["path"]).read_bytes(), entry)
    subprocess.run(
        [
            args.alfworld_python,
            "-c",
            "from importlib.metadata import version; assert version('alfworld') == '0.4.2'",
        ],
        check=True,
    )
    repository = Path(__file__).resolve().parents[2]
    subprocess.run(
        [
            args.alfworld_python,
            str(repository / "benchmarks/alfworld/build_dataset.py"),
            "--alfworld-data",
            str(args.alfworld_data.resolve()),
            "--output",
            str(args.output / "alfworld"),
            "--no-oracle",
        ],
        check=True,
    )
    ClawGymAdapter(args.output / "clawgym", dataset_path=args.clawgym_data).generate()
    convert_jobbench(
        source_root=args.jobbench_source,
        output_root=args.output / "jobbench",
        splits=["main", "easy"],
        base_image=None,
        workdir="/workspace",
        overwrite=False,
    )
    asyncio.run(export_terminal_tasks(args.tb_manifest, args.output / "tb21"))


if __name__ == "__main__":
    main()
