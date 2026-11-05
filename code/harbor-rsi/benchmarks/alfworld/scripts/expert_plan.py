#!/usr/bin/env python3
"""Emit ALFWorld's handcoded expert walkthrough for one game, as JSON.

Used only to build Oracle solutions. It runs in its own process because the
expert wrapper is loaded here and must never be present on the eval path.

    {"won": true, "steps": 12, "seed": 0, "plan": ["look", "go to shelf 1", ...]}

Upstream's handcoded expert calls the global ``random`` module without seeding
it (``alfworld.agents.expert.handcoded_expert``: it picks among candidate
objects and, when it repeats itself, among admissible commands). Consecutive
runs therefore produce different walkthroughs for the same game, and some of
them exhaust the episode budget without winning. Seeding ``random`` makes one
attempt reproducible, and attempts are tried in a fixed seed order until one
wins inside the budget; the winning seed is reported so the plan can be
regenerated exactly. A narrow oracle-only compatibility repair handles games
whose admissible placement grammar is ``put ... in/on ...`` while the policy
still checks for its older ``move ... to ...`` spelling.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path


def _task_targets(game_file: str) -> tuple[str, str, str]:
    """Read the target classes needed for the oracle-only command repair."""
    try:
        data = json.loads(
            (Path(game_file).parent / "traj_data.json").read_text(encoding="utf-8")
        )
        params = data["pddl_params"]
        return (
            str(data.get("task_type", "")).lower(),
            str(params.get("object_target", "")).lower(),
            str(params.get("parent_target", "")).lower(),
        )
    except (OSError, KeyError, TypeError, json.JSONDecodeError):
        return "", "", ""


def _repair_target_put(
    admissible_commands: list[str], object_target: str, parent_target: str
) -> str | None:
    """Return a legal target placement command when the expert stalls.

    ALFWorld's handcoded policy checks for the legacy ``move`` spelling. Some
    generated TextWorld games expose the same action as ``put ... in/on ...``;
    in those games the policy keeps exploring even though the target placement
    is immediately available. This repair is confined to oracle generation and
    selects only an action already returned by TextWorld as admissible.
    """
    if not object_target or not parent_target:
        return None
    for command in admissible_commands:
        words = command.split()
        if (
            len(words) >= 6
            and words[0] == "put"
            and words[1] == object_target
            and words[3] == "in/on"
            and words[4] == parent_target
        ):
            return command
    return None


def _walkthrough(
    env,
    max_episode_steps: int,
    task_type: str = "",
    object_target: str = "",
    parent_target: str = "",
) -> tuple[bool, list[str]]:
    """Run the expert once for a whole episode and return its actions."""
    _obs, info = env.reset()
    plan: list[str] = []
    won = False
    for _ in range(max_episode_steps):
        suggestion = info["extra.expert_plan"][0]
        if not suggestion:
            break
        action = suggestion[0]
        if task_type == "pick_two_obj_and_place":
            repair = _repair_target_put(
                info.get("admissible_commands", [[]])[0], object_target, parent_target
            )
            if repair is not None:
                action = repair
        _obs, _reward, done, info = env.step([action])
        plan.append(action)
        won = bool(info["won"][0])
        if won or bool(done[0]):
            break
    return won, plan


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game-file", required=True)
    parser.add_argument("--base-config", required=True)
    parser.add_argument("--max-episode-steps", type=int, required=True)
    parser.add_argument(
        "--attempts",
        type=int,
        default=100,
        help=(
            "How many seeds to try before giving up on a winning walkthrough. "
            "Some games need dozens: the hardest observed in valid_unseen "
            "(pick_heat_then_place_in_recep-Mug-None-Cabinet-10) first wins on "
            "seed 25, using 48 of its 50 steps."
        ),
    )
    args = parser.parse_args(argv)

    import textworld
    import textworld.gym
    import yaml
    from alfworld.agents.environment.alfred_tw_env import (
        AlfredDemangler,
        AlfredExpert,
        AlfredExpertType,
        AlfredInfos,
    )

    yaml.safe_load(Path(args.base_config).read_text(encoding="utf-8"))

    request_infos = textworld.EnvInfos(
        won=True, admissible_commands=True, extras=["gamefile", "expert_plan"]
    )
    env_id = textworld.gym.register_games(
        [args.game_file],
        request_infos,
        batch_size=1,
        asynchronous=True,
        max_episode_steps=args.max_episode_steps,
        wrappers=[
            AlfredDemangler(shuffle=False),
            AlfredInfos,
            AlfredExpert(AlfredExpertType.HANDCODED),
        ],
    )
    env = textworld.gym.make(env_id)
    task_type, object_target, parent_target = _task_targets(args.game_file)

    attempts = []
    for seed in range(args.attempts):
        random.seed(seed)
        won, plan = _walkthrough(
            env, args.max_episode_steps, task_type, object_target, parent_target
        )
        attempts.append({"seed": seed, "won": won, "steps": len(plan)})
        if won:
            json.dump(
                {
                    "won": True,
                    "seed": seed,
                    "steps": len(plan),
                    "plan": plan,
                    "attempts": attempts,
                },
                sys.stdout,
            )
            return 0

    json.dump(
        {"won": False, "seed": None, "steps": 0, "plan": [], "attempts": attempts},
        sys.stdout,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
