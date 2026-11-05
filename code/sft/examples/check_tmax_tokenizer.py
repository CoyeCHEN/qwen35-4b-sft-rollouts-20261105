#!/usr/bin/env python3
"""Run the real tokenizer/mask check when an A800 model checkout is available.

The script is intentionally local-only: it never downloads weights or tokenizer
files and never starts a Trainer.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from adapters.openharness_v2 import load_rollout
from sft.tokenization import tokenize_trajectories


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("rollout", help="Recorder v2 directory")
    parser.add_argument("--model", default=os.environ.get("TMAX_MODEL_PATH"), required=False)
    parser.add_argument("--revision", default=os.environ.get("TMAX_TOKENIZER_REVISION"))
    parser.add_argument("--max-length", type=int, default=8192)
    args = parser.parse_args()
    if not args.model:
        raise SystemExit("set TMAX_MODEL_PATH to a local TMax 2B checkout")
    try:
        from transformers import AutoTokenizer
    except ImportError as error:
        raise SystemExit("transformers is required on the A800 host") from error
    tokenizer = AutoTokenizer.from_pretrained(args.model, revision=args.revision,
                                              trust_remote_code=True, local_files_only=True)
    trajectory = load_rollout(args.rollout)
    samples = tokenize_trajectories([trajectory], tokenizer, max_length=args.max_length)
    for sample in samples:
        supervised = [token for token, active in zip(sample["input_ids"], sample["loss_mask"]) if active]
        print({"call_id": sample["call_id"], "tokens": len(sample["input_ids"]),
               "supervised_tokens": len(supervised),
               "supervised_text": tokenizer.decode(supervised, skip_special_tokens=False)})


if __name__ == "__main__":
    main()
