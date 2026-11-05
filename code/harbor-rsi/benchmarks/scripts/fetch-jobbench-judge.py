#!/usr/bin/env python3
"""Fetch the pinned upstream judge; never accept unverified source."""

from __future__ import annotations

import hashlib
import sys
import urllib.request
from pathlib import Path

EVAL_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(EVAL_ROOT / "jobbench" / "src"))
from jobbench_e2b import adapter  # noqa: E402


def main() -> None:
    target = adapter.VENDOR_DIR / "judge.py"
    if target.is_file():
        adapter.load_judge()
        print("Pinned JobBench judge verified.")
        return
    url = (
        f"https://raw.githubusercontent.com/Job-Bench/job-bench-eval/"
        f"{adapter.EVALUATOR_COMMIT}/eval/judge.py"
    )
    with urllib.request.urlopen(url, timeout=60) as response:
        content = response.read()
    if hashlib.sha256(content).hexdigest() != adapter.EVALUATOR_SHA256:
        raise ValueError("Downloaded judge SHA256 differs from the pinned source")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(content)
    adapter.load_judge()
    print("Pinned JobBench judge downloaded and verified.")


if __name__ == "__main__":
    main()
