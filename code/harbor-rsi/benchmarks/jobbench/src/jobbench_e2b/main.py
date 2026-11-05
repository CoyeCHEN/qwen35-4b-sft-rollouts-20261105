#!/usr/bin/env python3
"""CLI for the JobBench → Harbor (E2B) adapter.

Examples::

    # Generate both splits from the upstream source tree.
    python -m jobbench_e2b.adapter \\
        --source-root /path/to/hf-job-bench \\
        --split main --split easy \\
        --base-image python:3.12-slim \\
        --overwrite

    # One task, for a smoke test.
    python -m jobbench_e2b.adapter \\
        --source-root /path/to/hf-job-bench \\
        --split easy \\
        --task-ids biostatisticians/task1 \\
        --base-image python:3.12-slim \\
        --overwrite

    # Baked-image mode: emit environment/Dockerfile and leave docker_image out.
    python -m jobbench_e2b.adapter \\
        --source-root /path/to/hf-job-bench \\
        --split easy --baked-image \\
        --overwrite
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from jobbench_e2b.adapter import DEFAULT_WORKDIR, REPO_ROOT, SPLITS, run


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate Harbor tasks from a JobBench source tree.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--source-root",
        type=Path,
        required=True,
        help="JobBench source root, containing dataset/ (and/or dataset_easy/).",
    )
    parser.add_argument(
        "--split",
        action="append",
        choices=sorted(SPLITS),
        dest="splits",
        help="Split to generate; repeat for more than one. Default: main.",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=REPO_ROOT / "datasets",
        help="Where to write generated tasks (default: <repo>/datasets).",
    )
    parser.add_argument(
        "--base-image",
        default=None,
        help=(
            "Runtime-upload mode: start from this image and let Harbor upload "
            "environment/ into the workdir. The image MUST already contain "
            "/logs, /tests, /solution and the workdir — E2B cannot bind-mount "
            "them, so a stock image fails during log collection. Omit this flag "
            "(the default) to use baked mode instead."
        ),
    )
    parser.add_argument(
        "--baked-image",
        action="store_true",
        help=(
            "Force baked mode (this is already the default when --base-image is "
            "omitted). E2B builds a self-contained image server-side, so no "
            "container registry is needed."
        ),
    )
    parser.add_argument(
        "--workdir",
        default=DEFAULT_WORKDIR,
        help=f"Sandbox working directory (default: {DEFAULT_WORKDIR}).",
    )
    parser.add_argument(
        "--limit", type=int, default=None, help="Generate only the first N tasks per split."
    )
    parser.add_argument(
        "--task-ids",
        nargs="+",
        default=None,
        help="Only these tasks: 'profession/taskN' or 'profession__taskN'.",
    )
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    if args.baked_image and args.base_image:
        print(
            "error: --baked-image and --base-image are mutually exclusive.\n"
            "       Baked mode builds a self-contained image; upload mode reuses "
            "an existing one.",
            file=sys.stderr,
        )
        return 2

    # Baked mode is the default: E2B builds the image server-side from
    # environment/Dockerfile, so no registry is involved. Upload mode is opt-in
    # via --base-image, and requires an image that already carries the directories
    # E2B cannot bind-mount.
    base_image = args.base_image

    # The expected failures here (wrong source root, count mismatch, judge hash
    # drift) are all operator errors with a one-line fix, not crashes. A
    # traceback would bury the message.
    try:
        manifest = run(
            source_root=args.source_root,
            output_root=args.output_root,
            splits=args.splits or ["main"],
            base_image=base_image,
            workdir=args.workdir,
            overwrite=args.overwrite,
            limit=args.limit,
            task_ids=args.task_ids,
        )
    except (FileNotFoundError, FileExistsError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    total = sum(s["count"] for s in manifest["splits"].values())
    print(f"\ngenerated {total} task(s) under {args.output_root}")
    for split, info in manifest["splits"].items():
        print(f"  {split}: {info['count']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
