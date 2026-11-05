#!/usr/bin/env python3
"""Validate a generated JobBench-on-E2B dataset before spending sandbox money.

Checks the things that fail *silently* at runtime, which are the ones worth
catching locally:

  * TOML parses, and the fields Harbor's pydantic models actually accept are
    the fields we meant to set (unknown keys are dropped without complaint).
  * ``instruction.md`` exists and its paths match ``workdir``.
  * ``environment/`` does not accidentally combine a Dockerfile with a
    docker_image — that combination makes Harbor skip uploading the fixture.
  * the fixture is present and non-empty.
  * ``tests/`` carries the judge + rubric + a runnable entrypoint.
  * every ``${VAR}`` in the task's env is one Harbor will expand.

Run it after generating or migrating, and before ``harbor run``.

Usage::

    python scripts/validate_dataset.py datasets/easy
    python scripts/validate_dataset.py datasets/main --strict
"""

from __future__ import annotations

import argparse
import re
import sys
import tomllib
from pathlib import Path

# Harbor's pydantic models default to extra="ignore", so a typo'd key is
# dropped silently. These are the keys that are actually honoured.
LEGAL_ROOT = {
    "schema_version",
    "task",
    "metadata",
    "verifier",
    "agent",
    "environment",
    "solution",
    "steps",
    "artifacts",
    "multi_step_reward_strategy",
    "source",
}
LEGAL_AGENT = {"timeout_sec", "user", "network_mode", "allowed_hosts"}
LEGAL_VERIFIER = {
    "timeout_sec",
    "env",
    "user",
    "environment_mode",
    "environment",
    "network_mode",
    "allowed_hosts",
    "collect",
}
LEGAL_ENVIRONMENT = {
    "build_timeout_sec",
    "docker_image",
    "os",
    "cpus",
    "memory_mb",
    "storage_mb",
    "gpus",
    "gpu_types",
    "tpu",
    "mcp_servers",
    "env",
    "skills_dir",
    "healthcheck",
    "workdir",
    "allow_internet",
    "network_mode",
    "allowed_hosts",
}

# `${VAR}` or `${VAR:-default}` — must be the *entire* value to expand.
_ENV_TEMPLATE = re.compile(r"\$\{([^}:]+)(?::-(.*))?\}")

problems: list[str] = []
warnings: list[str] = []


def fail(task: str, msg: str) -> None:
    problems.append(f"{task}: {msg}")


def warn(task: str, msg: str) -> None:
    warnings.append(f"{task}: {msg}")


def check_task(task_dir: Path, *, strict: bool) -> None:
    name = task_dir.name

    # --- task.toml -----------------------------------------------------------
    config_path = task_dir / "task.toml"
    if not config_path.is_file():
        fail(name, "no task.toml")
        return
    try:
        cfg = tomllib.loads(config_path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        fail(name, f"task.toml does not parse: {exc}")
        return

    unknown = set(cfg) - LEGAL_ROOT
    if unknown:
        fail(name, f"unknown top-level keys (silently ignored by Harbor): {sorted(unknown)}")

    for section, legal in (
        ("agent", LEGAL_AGENT),
        ("verifier", LEGAL_VERIFIER),
        ("environment", LEGAL_ENVIRONMENT),
    ):
        if section in cfg:
            extra = set(cfg[section]) - legal
            # mcp_servers entries are lists of tables; only flag scalar-level keys.
            extra = {k for k in extra if not isinstance(cfg[section][k], list)}
            if extra:
                fail(name, f"[{section}] has non-schema keys (silently ignored): {sorted(extra)}")

    env = cfg.get("environment", {})
    workdir = env.get("workdir")
    if not workdir:
        fail(name, "no [environment].workdir")

    # --- the silent-fixture-loss combination ---------------------------------
    has_dockerfile = (task_dir / "environment" / "Dockerfile").is_file()
    has_image = bool(env.get("docker_image"))
    if has_dockerfile and has_image:
        fail(
            name,
            "environment/Dockerfile AND docker_image are both set — Harbor will use "
            "the image and NOT upload environment/, so the fixture never reaches "
            "the sandbox (no error is raised). Remove one.",
        )
    if not has_dockerfile and not has_image:
        fail(name, "neither docker_image nor environment/Dockerfile — nothing to run")

    # --- agent.user ----------------------------------------------------------
    if cfg.get("agent", {}).get("user") not in (None, "root"):
        fail(name, f"[agent].user = {cfg['agent']['user']!r} — E2B has no such user")

    if "storage_mb" in env:
        warn(name, "[environment].storage_mb is never read by the E2B environment")

    # --- instruction.md ------------------------------------------------------
    instr_path = task_dir / "instruction.md"
    if not instr_path.is_file():
        fail(name, "no instruction.md (Harbor will not recognise this as a task)")
    else:
        instr = instr_path.read_text(encoding="utf-8")
        if workdir and workdir not in instr:
            fail(name, f"instruction.md never mentions workdir {workdir!r}")
        if "{workdir}" in instr:
            fail(name, "instruction.md still has an unrendered {workdir} placeholder")

    # --- fixture -------------------------------------------------------------
    task_folder = task_dir / "environment" / "task_folder"
    if not task_folder.is_dir():
        fail(name, "no environment/task_folder/")
    else:
        files = [p for p in task_folder.rglob("*") if p.is_file()]
        if not files:
            fail(name, "environment/task_folder/ is empty")
        if not (task_folder / "TASK_INSTRUCTIONS.txt").is_file():
            fail(name, "environment/task_folder/TASK_INSTRUCTIONS.txt missing")

    # --- leaked answer material ---------------------------------------------
    env_dir = task_dir / "environment"
    for leaked in ("task_card.md", "files_required_to_search", "RUBRICS.json", "judge.py"):
        if (env_dir / leaked).exists():
            fail(name, f"{leaked} must not be under environment/ (agent can read it)")

    # --- tests/ --------------------------------------------------------------
    tests = task_dir / "tests"
    for required in ("test.sh", "judge.py", "RUBRICS.json"):
        if not (tests / required).is_file():
            fail(name, f"tests/{required} missing")
    if (tests / "test.sh").is_file():
        sh = (tests / "test.sh").read_text(encoding="utf-8")
        if "__WORKDIR__" in sh:
            fail(name, "tests/test.sh still has an unrendered __WORKDIR__ placeholder")
        # The script may reference the output dir literally or via a variable it
        # sets; accept either, but require the workdir to actually appear.
        if workdir and workdir not in sh:
            fail(name, f"tests/test.sh never references workdir {workdir!r}")
        for legacy in ("/opt/gdpval-agent-python", "/home/user"):
            if legacy in sh:
                fail(name, f"tests/test.sh still references the Siflow path {legacy}")

    # --- env templates -------------------------------------------------------
    for key, value in cfg.get("verifier", {}).get("env", {}).items():
        if not isinstance(value, str):
            continue
        if "${" in value and not _ENV_TEMPLATE.fullmatch(value):
            fail(
                name,
                f"[verifier.env].{key} = {value!r} — ${{VAR}} only expands when it is "
                "the ENTIRE value, so this is passed through literally",
            )

    # --- the shape that silently fails on E2B --------------------------------
    # E2B has no bind mounts, so /logs, /tests, /solution and the workdir must
    # already exist in the image. A bare `python:3.12-slim` will not have them,
    # and Harbor's own error for the missing path is misleading:
    #   FileNotFoundException: path not found: lstat /logs
    # raised during log collection, i.e. after the sandbox has been spent.
    #
    # Baked mode is self-verifying here (the generated Dockerfile creates the
    # dirs), so only runtime-upload mode is worth flagging — and only when the
    # image is one of the known-bare ones.
    if not has_dockerfile and has_image:
        image = env["docker_image"]
        bare = ("python:", "ubuntu:", "debian:", "alpine:", "busybox:", "node:")
        if image.startswith(bare) and "jobbench" not in image:
            fail(
                name,
                f"docker_image={image!r} is a stock image without /logs, /tests or "
                "/solution. E2B cannot bind-mount them, so Harbor will fail during "
                "log collection *after* the trial has run. Use a JobBench image, or "
                "--baked-image mode.",
            )

    if strict and not problems:
        pass


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("dataset_dir", type=Path, help="Dataset root, or a single task directory.")
    parser.add_argument("--strict", action="store_true", help="Treat warnings as failures.")
    args = parser.parse_args()

    root = args.dataset_dir
    if not root.is_dir():
        print(f"not a directory: {root}", file=sys.stderr)
        return 2

    # Accept either a dataset root (children are tasks) or one task dir.
    if (root / "task.toml").is_file():
        tasks = [root]
    else:
        tasks = sorted(p for p in root.iterdir() if p.is_dir() and (p / "task.toml").is_file())
        if not tasks:
            print(f"no tasks found under {root}", file=sys.stderr)
            return 2

    for task in tasks:
        check_task(task, strict=args.strict)

    print(f"checked {len(tasks)} task(s) under {root}")
    if warnings:
        print(f"\n{len(warnings)} warning(s):")
        for w in warnings:
            print(f"  ! {w}")
    if problems:
        print(f"\n{len(problems)} problem(s):")
        for p in problems:
            print(f"  x {p}")
        return 1

    if args.strict and warnings:
        return 1
    print("OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
