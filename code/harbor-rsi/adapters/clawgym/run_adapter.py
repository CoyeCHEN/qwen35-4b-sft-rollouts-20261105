from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from adapters.clawgym.adapter import DATASET_SHA256, ClawGymAdapter


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate Harbor tasks for ClawGym-Bench"
    )
    parser.add_argument("--dataset-path", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--task-ids", nargs="*")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--agent-timeout-sec", type=float, default=3000.0)
    parser.add_argument("--verifier-timeout-sec", type=float, default=900.0)
    args = parser.parse_args()
    if hashlib.sha256(args.dataset_path.read_bytes()).hexdigest() != DATASET_SHA256:
        raise ValueError(
            "Dataset bytes do not match the pinned official ClawGym revision"
        )
    adapter = ClawGymAdapter(
        args.output_dir,
        dataset_path=args.dataset_path,
        agent_timeout_sec=args.agent_timeout_sec,
        verifier_timeout_sec=args.verifier_timeout_sec,
        overwrite=args.overwrite,
    )
    paths = adapter.generate(limit=args.limit, task_ids=args.task_ids)
    print(f"generated {len(paths)} ClawGym tasks in {args.output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
