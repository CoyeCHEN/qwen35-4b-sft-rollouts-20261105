"""Static invariants of the generated ALFWorld Harbor dataset.

These read an already-built dataset directory (default
``benchmarks/alfworld/datasets/valid_unseen``, override with ``$ALFWORLD_DATASET``)
and never contact E2B or build images. Building the dataset needs the ALFWorld
runtime; checking it does not.
"""

from __future__ import annotations

import json
import os
import re
import tomllib
from pathlib import Path

import pytest

from benchmarks.alfworld.build_dataset import EXPECTED_TASK_COUNT, SPLIT

REPO_ROOT = Path(__file__).resolve().parents[3]
DATASET = Path(
    os.environ.get(
        "ALFWORLD_DATASET", REPO_ROOT / "benchmarks/alfworld/datasets/valid_unseen"
    )
)

TASK_TYPES = {
    "look_at_obj_in_light",
    "pick_and_place_simple",
    "pick_clean_then_place_in_recep",
    "pick_cool_then_place_in_recep",
    "pick_heat_then_place_in_recep",
    "pick_two_obj_and_place",
}

# Anything here in an agent-readable file would hand the agent the answer or the
# action list the generative protocol withholds.
FORBIDDEN_IN_AGENT_FILES = (
    "admissible",
    "expert_plan",
    "walkthrough",
    "traj_data",
    "policy_commands",
    "goal_predicate",
)


def _manifest() -> dict:
    path = DATASET / "manifest.json"
    if not path.exists():
        pytest.skip(f"no built dataset at {DATASET}; run build_dataset.py first")
    return json.loads(path.read_text(encoding="utf-8"))


def _task_dirs() -> list[Path]:
    if not DATASET.is_dir():
        pytest.skip(f"no built dataset at {DATASET}; run build_dataset.py first")
    return sorted(p for p in DATASET.iterdir() if p.is_dir())


def test_dataset_has_all_134_valid_unseen_tasks():
    manifest = _manifest()
    if manifest["partial"]:
        pytest.skip("dataset was built partially (--limit/--task-type)")
    assert manifest["split"] == SPLIT
    assert manifest["upstream_game_count"] == EXPECTED_TASK_COUNT
    assert manifest["upstream_solvable_count"] == EXPECTED_TASK_COUNT
    assert manifest["task_count"] == EXPECTED_TASK_COUNT
    assert len(manifest["tasks"]) == EXPECTED_TASK_COUNT
    assert len(_task_dirs()) == EXPECTED_TASK_COUNT


def test_task_identities_are_unique():
    manifest = _manifest()
    names = [task["name"] for task in manifest["tasks"]]
    assert len(set(names)) == len(names)
    games = [task["game_sha256"] for task in manifest["tasks"]]
    assert len(set(games)) == len(games), "the same game was packaged twice"


def test_no_valid_seen_leaked_in():
    manifest = _manifest()
    for task in manifest["tasks"]:
        assert task["split"] == SPLIT
    for task_dir in _task_dirs():
        config = tomllib.loads((task_dir / "task.toml").read_text(encoding="utf-8"))
        assert config["metadata"]["alfworld_split"] == SPLIT
        assert SPLIT in config["task"]["tags"]


def test_all_six_task_types_present():
    manifest = _manifest()
    if manifest["partial"]:
        pytest.skip("dataset was built partially")
    assert {task["task_type"] for task in manifest["tasks"]} == TASK_TYPES


def test_episode_budget_is_upstream_50_everywhere():
    manifest = _manifest()
    assert manifest["max_episode_steps"] == 50
    for task_dir in _task_dirs():
        config = tomllib.loads((task_dir / "task.toml").read_text(encoding="utf-8"))
        assert config["metadata"]["alfworld_max_episode_steps"] == 50
        daemon_config = json.loads(
            (task_dir / "environment/private/daemon-config.json").read_text(
                encoding="utf-8"
            )
        )
        assert daemon_config["max_episode_steps"] == 50


def test_oracle_plans_fit_the_episode_budget():
    manifest = _manifest()
    for task in manifest["tasks"]:
        if "oracle_steps" not in task:
            continue
        assert 0 < task["oracle_steps"] <= manifest["max_episode_steps"], task["name"]
        # The seed is recorded so the walkthrough can be regenerated exactly;
        # upstream's handcoded expert is otherwise unseeded and nondeterministic.
        assert isinstance(task["oracle_expert_seed"], int)


def test_every_task_has_the_required_harbor_files():
    for task_dir in _task_dirs():
        for relative in (
            "task.toml",
            "instruction.md",
            "tests/test.sh",
            "environment/Dockerfile",
            "environment/play.py",
            "environment/healthcheck.sh",
            "environment/private/daemon.py",
            "environment/private/daemon-config.json",
            "environment/private/game/game.tw-pddl",
        ):
            assert (task_dir / relative).exists(), f"{task_dir.name}: {relative}"


def test_agent_user_is_not_root_and_verifier_is():
    for task_dir in _task_dirs():
        config = tomllib.loads((task_dir / "task.toml").read_text(encoding="utf-8"))
        assert config["agent"]["user"] == "alfagent"
        assert config["verifier"]["user"] == "root"


def test_hidden_assets_are_confined_to_the_private_dir():
    """traj_data.json (the human walkthrough) must never be packaged at all."""
    for task_dir in _task_dirs():
        assert not list(task_dir.rglob("traj_data.json"))
        pddl = [p.relative_to(task_dir) for p in task_dir.rglob("*.tw-pddl")]
        assert pddl == [Path("environment/private/game/game.tw-pddl")], task_dir.name


def test_agent_visible_files_do_not_leak_protocol_internals():
    """instruction.md and play.py are the only agent-facing content."""
    for task_dir in _task_dirs():
        for relative in ("instruction.md", "environment/play.py"):
            text = (task_dir / relative).read_text(encoding="utf-8").lower()
            for needle in FORBIDDEN_IN_AGENT_FILES:
                assert needle not in text, f"{task_dir.name}/{relative}: {needle}"


def test_instruction_offers_no_action_grammar_or_hints():
    for task_dir in _task_dirs():
        text = (task_dir / "instruction.md").read_text(encoding="utf-8").lower()
        for needle in ("go to <", "take <", "heat <", "cool <", "clean <", "few-shot"):
            assert needle not in text, f"{task_dir.name}: {needle}"


def test_agent_client_exposes_only_observe_and_act():
    for task_dir in _task_dirs():
        text = (task_dir / "environment/play.py").read_text(encoding="utf-8")
        assert 'add_parser("observe"' in text
        assert 'add_parser("act"' in text
        for banned in ("reset", "expert", "solution", "reward", "status"):
            assert f'add_parser("{banned}"' not in text


def test_daemon_config_points_into_the_private_dir():
    for task_dir in _task_dirs():
        config = json.loads(
            (task_dir / "environment/private/daemon-config.json").read_text(
                encoding="utf-8"
            )
        )
        assert config["game_file"].startswith("/opt/alfworld-private/")
        assert config["socket_path"] == "/run/alfworld/private.sock"
        assert config["agent_socket_path"] == "/run/alfworld/agent.sock"


def test_no_api_keys_or_secrets_in_the_dataset():
    for task_dir in _task_dirs():
        for path in task_dir.rglob("*"):
            if not path.is_file() or path.suffix == ".tw-pddl":
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            for needle in ("API_KEY=", "e2b_"):
                assert needle not in text, f"{path}: possible secret {needle}"
            assert not re.search(r"(?<![A-Za-z0-9])sk-[A-Za-z0-9]{16,}", text), (
                f"{path}: possible secret"
            )


def test_verifier_scores_only_upstream_won():
    for task_dir in _task_dirs():
        text = (task_dir / "tests/test.sh").read_text(encoding="utf-8")
        assert '"op": "status"' in text
        assert '.get("won")' in text
        # No invented grading signal.
        for banned in ("walkthrough", "judge", "similarity", "expert"):
            assert banned not in text.lower()


def test_healthcheck_never_restarts_a_ready_daemon():
    for task_dir in _task_dirs():
        text = (task_dir / "environment/healthcheck.sh").read_text(encoding="utf-8")
        assert "refusing to restart" in text
        assert "episode state is lost" in text
        assert not re.search(r"^\s*kill\s+(?!-0\b)", text, re.MULTILINE)


def test_daemon_resets_exactly_once_and_has_no_reset_op():
    for task_dir in _task_dirs():
        text = (task_dir / "environment/private/daemon.py").read_text(encoding="utf-8")
        assert text.count("self._env.reset()") == 1, (
            "env.reset() must be called exactly once"
        )
        assert 'op == "reset"' not in text
        assert '"reset"' not in text.split("allowed_ops")[1].split("\n")[0]


def test_dataset_generation_is_deterministic_for_task_identity():
    """Rebuilding must not change task names; they derive from game identity."""
    from benchmarks.alfworld.build_dataset import _task_name

    manifest = _manifest()
    for task in manifest["tasks"]:
        game = Path("x") / task["scene"] / task["trial"] / "game.tw-pddl"
        assert _task_name(game) == task["name"]
