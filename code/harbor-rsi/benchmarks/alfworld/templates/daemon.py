#!/usr/bin/env python3
"""Persistent ALFWorld episode daemon for one Harbor task.

ALFWorld state lives in a live TextWorld environment object, not on the
filesystem, so a shell-per-step agent cannot own it. This daemon holds exactly
one episode for the lifetime of the task and answers a narrow line protocol over
a Unix domain socket.

It runs as root. Hidden benchmark assets (the game file, PDDL, traj_data) and the
private success state stay on this side of the socket; ``play.py`` only relays
the observations the agent is entitled to see.

Protocol (one JSON object per line, request and response):

    {"op": "observe"}                -> agent-visible observation
    {"op": "act", "action": "..."}   -> step the episode, agent-visible feedback
    {"op": "status"}                 -> privileged: episode/success state
    {"op": "ping"}                   -> readiness probe

``status`` is reachable only through the root-owned socket, which the agent user
cannot open; it exists for the verifier, not for the agent.
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import socketserver
import sys
import threading
import traceback
from pathlib import Path

# Configuration is read from a root-only file rather than argv: any local user
# can read /proc/<pid>/cmdline, which would leak the hidden game path.
CONFIG_ENV_VAR = "ALFWORLD_DAEMON_CONFIG"


class EpisodeError(RuntimeError):
    """The episode could not be created or stepped."""


class Episode:
    """Exactly one ALFWorld episode, created once and never reset again.

    ``env.reset()`` is called a single time, in ``start()``. There is no reset
    operation in the protocol: silently rewinding a partially completed episode
    would turn an infrastructure fault into a fabricated benchmark result.
    """

    def __init__(self, config: dict) -> None:
        self._config = config
        self._lock = threading.Lock()
        self._env = None
        self._started = False
        self._observation = ""
        self._done = False
        self._won = False
        self._steps = 0
        self._max_steps = int(config["max_episode_steps"])
        self._task_description = ""

    # -- upstream construction -------------------------------------------------

    def _build_env(self):
        """Register and make the upstream TextWorld env for this single game.

        This mirrors ``AlfredTWEnv.init_env`` for the eval path: the same
        wrappers, the same requested infos and the same episode limit. The
        expert wrapper is deliberately absent, exactly as upstream omits it for
        ``eval_out_of_distribution``.
        """
        import textworld
        import textworld.gym
        from alfworld.agents.environment.alfred_tw_env import (
            AlfredDemangler,
            AlfredInfos,
        )

        game_file = self._config["game_file"]
        if not os.path.isfile(game_file):
            raise EpisodeError(f"ALFWorld game file is missing: {game_file}")

        # domain_randomization is False for every eval split upstream.
        wrappers = [AlfredDemangler(shuffle=False), AlfredInfos]
        request_infos = textworld.EnvInfos(
            won=True, admissible_commands=True, extras=["gamefile"]
        )
        env_id = textworld.gym.register_games(
            [game_file],
            request_infos,
            batch_size=1,
            asynchronous=True,
            max_episode_steps=self._max_steps,
            wrappers=wrappers,
        )
        return textworld.gym.make(env_id)

    def start(self) -> None:
        with self._lock:
            if self._started:
                raise EpisodeError("Episode already started")
            self._env = self._build_env()
            obs, info = self._env.reset()
            self._started = True
            self._observation = obs[0]
            self._won = bool(info["won"][0])
            self._task_description = self._extract_task(self._observation)

    @staticmethod
    def _extract_task(observation: str) -> str:
        for line in observation.splitlines():
            stripped = line.strip()
            if stripped.lower().startswith("your task is to:"):
                return stripped
        return ""

    # -- operations ------------------------------------------------------------

    def observe(self) -> str:
        with self._lock:
            self._require_started()
            return self._observation

    def act(self, action: str) -> dict:
        """Step the episode with the agent's raw action.

        The action string is passed to ALFWorld unchanged. There is no
        admissible-command lookup, no fuzzy matching and no normalization: an
        illegal action must receive ALFWorld's own feedback.
        """
        with self._lock:
            self._require_started()
            if self._done:
                # Upstream keeps returning the terminal state; say so plainly
                # rather than inventing a new observation.
                return {
                    "observation": self._observation,
                    "episode_over": True,
                    "steps_taken": self._steps,
                    "steps_remaining": 0,
                }

            try:
                obs, _reward, done, info = self._env.step([action])
            except Exception as exc:  # upstream/TextWorld failure
                raise EpisodeError(f"ALFWorld step failed: {exc}") from exc

            self._steps += 1
            self._observation = obs[0]
            self._won = bool(info["won"][0])
            self._done = bool(done[0]) or self._steps >= self._max_steps
            return {
                "observation": self._observation,
                "episode_over": self._done,
                "steps_taken": self._steps,
                "steps_remaining": max(0, self._max_steps - self._steps),
            }

    def status(self) -> dict:
        """Privileged episode state for the verifier."""
        with self._lock:
            return {
                "started": self._started,
                "won": self._won,
                "episode_over": self._done,
                "steps_taken": self._steps,
                "max_episode_steps": self._max_steps,
                "task_description": self._task_description,
            }

    def steps_remaining(self) -> int:
        with self._lock:
            return max(0, self._max_steps - self._steps)

    def is_over(self) -> bool:
        with self._lock:
            return self._done

    def _require_started(self) -> None:
        if not self._started:
            raise EpisodeError("Episode has not been initialized")


class _Handler(socketserver.StreamRequestHandler):
    episode: Episode = None  # set on the server class

    def handle(self) -> None:
        for raw in self.rfile:
            line = raw.decode("utf-8", errors="replace").strip()
            if not line:
                continue
            self.wfile.write((json.dumps(self._dispatch(line)) + "\n").encode())
            self.wfile.flush()

    def _dispatch(self, line: str) -> dict:
        try:
            request = json.loads(line)
        except ValueError:
            return {"ok": False, "error": "malformed request", "kind": "protocol"}
        if not isinstance(request, dict):
            return {
                "ok": False,
                "error": "request must be an object",
                "kind": "protocol",
            }

        op = request.get("op")
        try:
            if op == "ping":
                return {"ok": True, "ready": self.episode is not None}
            if op == "observe":
                return {
                    "ok": True,
                    "observation": self.episode.observe(),
                    "episode_over": self.episode.is_over(),
                    "steps_remaining": self.episode.steps_remaining(),
                }
            if op == "act":
                action = request.get("action")
                if not isinstance(action, str):
                    return {
                        "ok": False,
                        "error": "act requires a string action",
                        "kind": "protocol",
                    }
                return {"ok": True, **self.episode.act(action)}
            if op == "status":
                return {"ok": True, **self.episode.status()}
            return {"ok": False, "error": f"unknown op: {op!r}", "kind": "protocol"}
        except EpisodeError as exc:
            return {"ok": False, "error": str(exc), "kind": "episode"}
        except Exception as exc:  # pragma: no cover - defensive
            return {
                "ok": False,
                "error": f"internal daemon error: {exc}",
                "kind": "internal",
            }


class _Server(socketserver.ThreadingUnixStreamServer):
    daemon_threads = True
    allow_reuse_address = True


def _serve(config: dict) -> int:
    socket_path = Path(config["socket_path"])
    socket_path.parent.mkdir(parents=True, exist_ok=True)
    if socket_path.exists():
        socket_path.unlink()

    episode = Episode(config)
    episode.start()

    handler = type("_BoundHandler", (_Handler,), {"episode": episode})
    server = _Server(str(socket_path), handler)

    # The socket is root-only: this is what keeps the privileged `status`
    # channel and the episode itself out of the agent's reach. play.py is
    # setuid-free and reaches the daemon through a separate relay socket.
    os.chmod(socket_path, 0o600)

    agent_socket_path = config.get("agent_socket_path")
    if agent_socket_path:
        _start_agent_relay(Path(agent_socket_path), socket_path, config)

    ready_path = config.get("ready_path")
    if ready_path:
        Path(ready_path).write_text("ready\n", encoding="utf-8")

    server.serve_forever()
    return 0


def _start_agent_relay(agent_socket: Path, private_socket: Path, config: dict) -> None:
    """Expose only observe/act to the agent user over a second socket.

    The agent may reach the episode, but not the privileged operations. Filtering
    happens here, on the root side, rather than in the client: a client-side
    check would be trivially bypassed by talking to the socket directly.
    """
    agent_socket.parent.mkdir(parents=True, exist_ok=True)
    if agent_socket.exists():
        agent_socket.unlink()

    allowed_ops = {"observe", "act", "ping"}

    class _RelayHandler(socketserver.StreamRequestHandler):
        def handle(self) -> None:
            for raw in self.rfile:
                line = raw.decode("utf-8", errors="replace").strip()
                if not line:
                    continue
                self.wfile.write((json.dumps(self._relay(line)) + "\n").encode())
                self.wfile.flush()

        def _relay(self, line: str) -> dict:
            try:
                request = json.loads(line)
            except ValueError:
                return {"ok": False, "error": "malformed request", "kind": "protocol"}
            if not isinstance(request, dict) or request.get("op") not in allowed_ops:
                return {
                    "ok": False,
                    "error": "unsupported operation",
                    "kind": "protocol",
                }
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
                client.connect(str(private_socket))
                client.sendall((json.dumps(request) + "\n").encode())
                with client.makefile("r") as stream:
                    response = stream.readline()
            try:
                return json.loads(response)
            except ValueError:
                return {
                    "ok": False,
                    "error": "daemon returned a malformed response",
                    "kind": "internal",
                }

    relay = _Server(str(agent_socket), _RelayHandler)
    os.chmod(agent_socket, 0o666)
    threading.Thread(target=relay.serve_forever, daemon=True).start()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        default=os.environ.get(CONFIG_ENV_VAR),
        help=(
            f"Path to the root-only daemon config JSON. Defaults to ${CONFIG_ENV_VAR}."
        ),
    )
    args = parser.parse_args(argv)
    if not args.config:
        parser.error(f"--config or ${CONFIG_ENV_VAR} is required")

    config = json.loads(Path(args.config).read_text(encoding="utf-8"))
    try:
        return _serve(config)
    except Exception:
        # Surface startup failures as infrastructure faults with a full
        # traceback; never fall back to a fresh episode.
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
