"""Portable readers import independently of Linux-only execution support."""

import builtins
import os
import subprocess
import sys
from pathlib import Path

import pytest

from harbor.extensions.rsi.trajectory import _lock_rollout
from harbor.trial import process_supervisor


def test_portable_imports_and_helpers_do_not_import_fcntl():
    source = Path(__file__).parents[3] / "src"
    program = """
import builtins
original_import = builtins.__import__
def without_fcntl(name, globals=None, locals=None, fromlist=(), level=0):
    if name == 'fcntl' and (globals or {}).get('__name__') in {
        'harbor.extensions.rsi.trajectory', 'harbor.trial.process_supervisor'
    }:
        raise ModuleNotFoundError("No module named 'fcntl'", name='fcntl')
    return original_import(name, globals, locals, fromlist, level)
builtins.__import__ = without_fcntl
from harbor.agents.installed.open_harness import OpenHarnessAgent
from harbor.extensions.rsi.trajectory import build_atif_trajectory
from harbor.trial.process_supervisor import descendants, waiter_exit_code
assert OpenHarnessAgent.managed_process_lifecycle
assert callable(build_atif_trajectory)
assert waiter_exit_code(-15) == 143
rows = {1: {'ppid': 0}, 2: {'ppid': 1}, 3: {'ppid': 2}}
assert descendants(rows, 1) == {2: rows[2], 3: rows[3]}
"""
    subprocess.run(
        [sys.executable, "-c", program],
        env={
            **os.environ,
            "PYTHONPATH": os.pathsep.join(
                [str(source), os.environ.get("PYTHONPATH", "")]
            ),
        },
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )


def test_real_rollout_lock_fails_explicitly_without_fcntl(tmp_path, monkeypatch):
    original_import = builtins.__import__

    def without_fcntl(name, *args, **kwargs):
        if name == "fcntl":
            raise ModuleNotFoundError("No module named 'fcntl'", name="fcntl")
        return original_import(name, *args, **kwargs)

    journal = tmp_path / "events.jsonl"
    journal.write_bytes(b"closed fixture\n")
    monkeypatch.setattr(builtins, "__import__", without_fcntl)
    with journal.open("rb") as file:
        with pytest.raises(NotImplementedError, match="POSIX advisory file locking"):
            _lock_rollout(file)
    assert journal.read_bytes() == b"closed fixture\n"


@pytest.mark.parametrize("entry", ["serve", "control", "main"])
def test_linux_supervisor_rejects_other_platforms_before_mutation(
    tmp_path, monkeypatch, entry
):
    state = tmp_path / "must-not-be-created"
    monkeypatch.setattr(process_supervisor.sys, "platform", "win32")
    with pytest.raises(NotImplementedError, match="requires Linux /proc"):
        if entry == "serve":
            process_supervisor.serve(state, "unused")
        elif entry == "control":
            process_supervisor.control(state, "cancel")
        else:
            process_supervisor.main()
    assert not state.exists()
