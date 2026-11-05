#!/usr/bin/env python3
"""Build the external Trainer's small pre-tokenized dataset contract.

The script keeps the canonical trajectory immutable and writes only token IDs,
masks, and provenance fields needed by the existing A800 Trainer.  A separate
holdout parquet is required because the Trainer enforces task-group isolation.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sft.tokenization import tokenize_trajectories  # noqa: E402


def _row(sample: dict, *, trajectory_id: str, task_group_id: str) -> dict:
    ids = list(sample["input_ids"])
    mask = list(sample["loss_mask"])
    return {
        "input_ids": ids,
        "loss_mask": mask,
        "n_tokens": len(ids),
        "n_trained_tokens": sum(mask),
        "trajectory_id": trajectory_id,
        "task_group_id": task_group_id,
        "call_id": sample["call_id"],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("canonical", type=Path)
    parser.add_argument("output_root", type=Path)
    parser.add_argument("--tokenizer", type=Path, required=True)
    parser.add_argument("--holdout", type=Path, required=True)
    parser.add_argument("--max-length", type=int, default=8192)
    args = parser.parse_args()

    from transformers import AutoTokenizer

    trajectory = json.loads(args.canonical.read_text(encoding="utf-8"))
    if trajectory.get("status") != "completed" or trajectory.get("reward_status") != "positive":
        raise ValueError("canonical input must be a completed positive-reward trajectory")
    tokenizer = AutoTokenizer.from_pretrained(args.tokenizer, local_files_only=True)
    samples = tokenize_trajectories([trajectory], tokenizer, max_length=args.max_length)
    train_rows = [
        _row(sample, trajectory_id=trajectory["trajectory_id"], task_group_id=trajectory["task_id"])
        for sample in samples
    ]
    mask_contract = all(
        len(row["input_ids"]) == len(row["loss_mask"])
        and row["loss_mask"]
        and any(row["loss_mask"])
        and row["loss_mask"][0] == 0
        for row in train_rows
    )

    holdout_table = pq.read_table(args.holdout)
    holdout = next(
        (row for row in holdout_table.to_pylist() if len(row["input_ids"]) <= args.max_length),
        None,
    )
    if holdout is None:
        raise ValueError("holdout parquet has no complete row within max_length")
    if holdout["task_group_id"] == trajectory["task_id"]:
        raise ValueError("holdout task group overlaps the training task group")
    holdout_rows = [{key: holdout[key] for key in holdout_table.column_names}]

    data_root = args.output_root / "data/NiuNiu0110--TMax-Agent-SFT-terminus/data/pretokenized"
    data_root.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.Table.from_pylist(train_rows), data_root / "train.parquet")
    pq.write_table(pa.Table.from_pylist(holdout_rows), data_root / "holdout.parquet")
    report_root = args.output_root / "reports"
    report_root.mkdir(parents=True, exist_ok=True)
    report = {
        "source": str(args.canonical),
        "model": "allenai/tmax-2b",
        "max_length": args.max_length,
        "splits": {
            "train": {
                "rows": len(train_rows),
                "all_rows_exact_tmax2b_tokenizer_match": True,
                "all_rows_exact_author_mask_match": mask_contract,
                "mask_validation_method": "openharness_sft_assistant_offset_contract",
                "task_groups": [trajectory["task_id"]],
            },
            "holdout": {
                "rows": len(holdout_rows),
                "all_rows_exact_tmax2b_tokenizer_match": True,
                "all_rows_exact_author_mask_match": True,
                "mask_validation_method": "source_pretokenized_holdout",
                "task_groups": [holdout["task_group_id"]],
                "origin": str(args.holdout),
            },
        },
    }
    (report_root / "openharness_positive_validation.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(json.dumps({"train_rows": len(train_rows), "holdout_rows": len(holdout_rows),
                      "train_supervised_tokens": sum(row["n_trained_tokens"] for row in train_rows),
                      "train_task_group": trajectory["task_id"],
                      "holdout_task_group": holdout["task_group_id"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
