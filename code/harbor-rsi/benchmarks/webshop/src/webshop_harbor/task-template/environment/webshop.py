#!/usr/bin/env python3
"""Small CLI for the stateful WebShop sidecar."""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request

BASE_URL = os.environ.get("WEBSHOP_URL", "http://webshop:3000").rstrip("/")


def request(path: str, payload: dict[str, str] | None = None) -> dict:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        BASE_URL + path,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST" if data is not None else "GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise SystemExit(
            f"WebShop rejected the request ({exc.code}): {detail}"
        ) from exc
    except urllib.error.URLError as exc:
        raise SystemExit(f"WebShop service is unavailable: {exc}") from exc


def print_state(state: dict, *, as_json: bool) -> None:
    if as_json:
        print(json.dumps(state, indent=2, ensure_ascii=False))
        return
    print(f"Instruction: {state['instruction']}")
    print(f"Step: {state['steps']}/{state['max_steps']}  Done: {state['done']}")
    print("\nObservation:\n" + state["observation"])
    actions = state.get("available_actions") or {}
    print("\nAvailable actions:\n" + json.dumps(actions, indent=2, ensure_ascii=False))
    if state.get("last_action"):
        print(f"\nLast action: {state['last_action']}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("observe")
    search = sub.add_parser("search")
    search.add_argument("query")
    click = sub.add_parser("click")
    click.add_argument("value")
    act = sub.add_parser("act")
    act.add_argument("action")
    sub.add_parser("result")
    args = parser.parse_args()

    if args.command == "observe":
        state = request("/state")
    elif args.command == "result":
        state = request("/result")
    else:
        action = (
            f"search[{args.query}]"
            if args.command == "search"
            else f"click[{args.value}]"
            if args.command == "click"
            else args.action
        )
        state = request("/act", {"action": action})
    print_state(state, as_json=args.json)
    return 0


if __name__ == "__main__":
    sys.exit(main())
