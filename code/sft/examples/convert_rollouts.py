#!/usr/bin/env python3
"""Convert one Recorder v2 or RLBridge file to canonical JSONL."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Make the checked-out repository usable before an editable install.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from adapters.openharness_v2 import load_rollout as load_openharness
from adapters.rlbridge import load_rollout as load_rlbridge
from sft.dataset import write_jsonl


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", choices=("openharness_v2", "rlbridge"))
    parser.add_argument("input")
    parser.add_argument("output")
    args = parser.parse_args()
    loader = load_openharness if args.source == "openharness_v2" else load_rlbridge
    row = loader(args.input)
    write_jsonl(args.output, [row])
    print(json.dumps({"trajectory_id": row["trajectory_id"], "status": row["status"],
                      "reward_status": row["reward_status"], "validation_issues": row["metadata"].get("validation_issues", [])},
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
