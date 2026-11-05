#!/usr/bin/env python3
"""Command-line interface to the household environment.

This is a stateless client. The environment itself is held by a separate
process, so every invocation continues the same episode rather than starting a
new one.

Usage:

    play.py observe
    play.py act "<action>"
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import sys

DEFAULT_SOCKET = "/run/alfworld/agent.sock"
SOCKET_ENV_VAR = "ALFWORLD_AGENT_SOCKET"


def _request(socket_path: str, payload: dict) -> dict:
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.settimeout(120)
            client.connect(socket_path)
            client.sendall((json.dumps(payload) + "\n").encode("utf-8"))
            with client.makefile("r") as stream:
                line = stream.readline()
    except OSError as exc:
        raise SystemExit(
            f"error: cannot reach the environment service at {socket_path}: {exc}"
        )
    if not line:
        raise SystemExit("error: the environment service closed the connection")
    try:
        return json.loads(line)
    except ValueError:
        raise SystemExit("error: the environment service returned malformed output")


def _emit(response: dict) -> int:
    if not response.get("ok"):
        print(f"error: {response.get('error', 'unknown error')}", file=sys.stderr)
        return 1

    observation = response.get("observation", "")
    print(observation.strip())
    if response.get("episode_over"):
        print()
        print("The episode is over. No further actions are possible.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="play.py",
        description="Interact with the household environment.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("observe", help="Show the current observation.")
    act = subparsers.add_parser("act", help="Take one action in the environment.")
    act.add_argument("action", help="The action to take, in plain English.")

    args = parser.parse_args(argv)
    socket_path = os.environ.get(SOCKET_ENV_VAR, DEFAULT_SOCKET)

    if args.command == "observe":
        payload = {"op": "observe"}
    else:
        # The action is forwarded verbatim. Nothing here rewrites, corrects or
        # validates it; the environment decides how to respond.
        payload = {"op": "act", "action": args.action}

    return _emit(_request(socket_path, payload))


if __name__ == "__main__":
    sys.exit(main())
