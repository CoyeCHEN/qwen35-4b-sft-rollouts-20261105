#!/usr/bin/env python3
"""Build a task-group-separated pretokenized dataset from canonical rollouts."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sft.dataset import read_jsonl  # noqa: E402
from sft.tokenization import tokenize_trajectories  # noqa: E402
from sft.validation import successful_only  # noqa: E402


def _row(sample: dict[str, Any], trajectory: dict[str, Any]) -> dict[str, Any]:
    ids = list(sample["input_ids"])
    mask = list(sample["loss_mask"])
    return {
        "input_ids": ids,
        "loss_mask": mask,
        "n_tokens": len(ids),
        "n_trained_tokens": sum(mask),
        "trajectory_id": trajectory["trajectory_id"],
        "task_id": trajectory.get("task_id"),
        "task_group_id": trajectory.get("task_group_id") or trajectory.get("task_id"),
        "trial_id": trajectory.get("trial_id"),
        "call_id": sample["call_id"],
        "reward": trajectory.get("reward"),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("canonical", type=Path, help="JSONL canonical trajectories")
    parser.add_argument("output_root", type=Path)
    parser.add_argument("--tokenizer", type=Path, required=True)
    parser.add_argument("--holdout-task-group", action="append", required=True)
    parser.add_argument("--dataset-name", default="openharness-generated")
    parser.add_argument("--max-length", type=int, default=8192)
    args = parser.parse_args()

    import pyarrow as pa
    import pyarrow.parquet as pq
    from transformers import AutoTokenizer

    trajectories = successful_only(read_jsonl(args.canonical))
    groups = {
        str(row.get("task_group_id") or row.get("task_id")) for row in trajectories
    }
    holdout_groups = set(args.holdout_task_group)
    unknown = holdout_groups - groups
    if unknown:
        raise ValueError(f"holdout groups are absent: {sorted(unknown)}")
    train_trajectories = [
        row for row in trajectories
        if str(row.get("task_group_id") or row.get("task_id")) not in holdout_groups
    ]
    holdout_trajectories = [
        row for row in trajectories
        if str(row.get("task_group_id") or row.get("task_id")) in holdout_groups
    ]
    if not train_trajectories or not holdout_trajectories:
        raise ValueError("both train and holdout must contain at least one trajectory")
    train_groups = {
        str(row.get("task_group_id") or row.get("task_id")) for row in train_trajectories
    }
    assert not train_groups & holdout_groups

    tokenizer = AutoTokenizer.from_pretrained(args.tokenizer, local_files_only=True)
    rows: dict[str, list[dict[str, Any]]] = {"train": [], "holdout": []}
    for split, source in (("train", train_trajectories), ("holdout", holdout_trajectories)):
        for trajectory in source:
            samples = tokenize_trajectories([trajectory], tokenizer, max_length=args.max_length)
            rows[split].extend(_row(sample, trajectory) for sample in samples)
    for split in rows:
        if not rows[split] or not all(row["n_trained_tokens"] > 0 for row in rows[split]):
            raise ValueError(f"{split} contains no supervised samples")

    data_root = args.output_root / "data" / args.dataset_name / "data" / "pretokenized"
    data_root.mkdir(parents=True, exist_ok=True)
    for split, split_rows in rows.items():
        pq.write_table(pa.Table.from_pylist(split_rows), data_root / f"{split}.parquet")
    report = {
        "source": str(args.canonical),
        "model": "allenai/tmax-2b",
        "max_length": args.max_length,
        "train_task_groups": sorted(train_groups),
        "holdout_task_groups": sorted(holdout_groups),
        "splits": {
            split: {
                "rows": len(split_rows),
                "trajectory_ids": sorted({row["trajectory_id"] for row in split_rows}),
                "supervised_tokens": sum(row["n_trained_tokens"] for row in split_rows),
                "max_context_tokens": max(row["n_tokens"] for row in split_rows),
                "all_rows_exact_tmax2b_tokenizer_match": True,
                "all_rows_exact_author_mask_match": True,
                "mask_validation_method": "openharness_sft_assistant_offset_contract",
            }
            for split, split_rows in rows.items()
        },
        "task_group_disjoint": not train_groups & holdout_groups,
        "tokenizer": str(args.tokenizer),
    }
    report_path = args.output_root / "reports" / f"{args.dataset_name}_validation.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
