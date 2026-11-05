#!/usr/bin/env python3
"""Translate the official WebShop reward into Harbor's reward contract."""

from __future__ import annotations

import json
import os
import time
import urllib.request
from pathlib import Path

URL = os.environ.get("WEBSHOP_URL", "http://webshop:3000").rstrip("/")
OUT = Path("/logs/verifier")
AGENT_COMPLETE = Path("/logs/agent/open-harness.complete")


def wait_for_agent() -> None:
    timeout = float(os.environ.get("WEBSHOP_AGENT_COMPLETION_TIMEOUT_SEC", "2400"))
    deadline = time.monotonic() + timeout
    while not AGENT_COMPLETE.is_file():
        if time.monotonic() >= deadline:
            raise TimeoutError(
                f"agent completion marker did not appear within {timeout:g} seconds"
            )
        time.sleep(0.25)
    exit_code = int(AGENT_COMPLETE.read_text(encoding="utf-8").strip())
    if exit_code != 0:
        raise RuntimeError(f"agent command exited with status {exit_code}")


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    wait_for_agent()
    with urllib.request.urlopen(URL + "/result", timeout=30) as response:
        result = json.load(response)
    reward = float(result.get("reward", 0.0) or 0.0)
    reward = min(1.0, max(0.0, reward))
    metrics = {
        "reward": reward,
        "webshop_reward": reward,
        "webshop_success": 1.0 if reward == 1.0 else 0.0,
        "webshop_done": 1.0 if result.get("done") else 0.0,
        "webshop_steps": float(result.get("steps", 0) or 0),
        "webshop_max_steps": float(result.get("max_steps", 0) or 0),
        "webshop_action_limit_reached": float(
            result.get("termination_reason") == "action_limit"
        ),
    }
    (OUT / "reward.json").write_text(
        json.dumps(metrics, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    (OUT / "reward.txt").write_text(f"{reward:.12g}\n", encoding="utf-8")
    (OUT / "webshop_result.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
