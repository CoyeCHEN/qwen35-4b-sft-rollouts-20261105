"""The sandbox supervisor must cancel safely with managed Python builds."""

import os
import errno
import platform
import signal
import subprocess
import sys

import pytest

if sys.platform != "linux":
    pytest.skip(
        "Sandbox process supervisor requires Linux /proc and pidfd",
        allow_module_level=True,
    )

from harbor.trial.process_supervisor import processes, signal_identity
from harbor.trial import process_supervisor as supervisor
from unittest.mock import Mock


@pytest.mark.skipif(
    platform.system() != "Linux"
    or platform.machine() not in ("x86_64", "aarch64", "riscv64"),
    reason="pidfd syscalls are Linux-specific",
)
def test_pidfd_fallback_preserves_process_identity_without_python_wrappers(monkeypatch):
    child = subprocess.Popen(["sleep", "60"])
    try:
        row = processes()[child.pid]
        monkeypatch.delattr(os, "pidfd_open", raising=False)
        monkeypatch.delattr(signal, "pidfd_send_signal", raising=False)

        signal_identity({**row, "start_ticks": row["start_ticks"] + 1}, signal.SIGTERM)
        assert child.poll() is None

        signal_identity(row, signal.SIGTERM)
        assert child.wait(timeout=5) == -signal.SIGTERM
    finally:
        if child.poll() is None:
            child.kill()
            child.wait(timeout=5)


def test_python_pidfd_apis_take_precedence(monkeypatch):
    opened, sent = Mock(return_value=42), Mock()
    fallback = Mock(side_effect=AssertionError("unexpected syscall fallback"))
    monkeypatch.setattr(os, "pidfd_open", opened, raising=False)
    monkeypatch.setattr(signal, "pidfd_send_signal", sent, raising=False)
    monkeypatch.setattr(supervisor, "_pidfd_syscall", fallback)
    assert supervisor._pidfd_open(123) == 42
    supervisor._pidfd_send_signal(42, signal.SIGKILL)
    opened.assert_called_once_with(123)
    sent.assert_called_once_with(42, signal.SIGKILL)


@pytest.mark.parametrize("error", [errno.ENOSYS, errno.EPERM, errno.EINVAL])
def test_syscall_error_is_not_ignored_or_replaced_by_pid_kill(monkeypatch, error):
    import ctypes

    monkeypatch.setattr(supervisor.platform, "machine", lambda: "x86_64")
    monkeypatch.delattr(os, "pidfd_open", raising=False)
    monkeypatch.setattr(
        ctypes, "CDLL", lambda *args, **kwargs: Mock(syscall=Mock(return_value=-1))
    )
    monkeypatch.setattr(ctypes, "get_errno", lambda: error)
    kill = Mock(side_effect=AssertionError("unsafe PID-only fallback"))
    monkeypatch.setattr(os, "kill", kill)
    with pytest.raises(OSError) as caught:
        supervisor._pidfd_open(123)
    assert caught.value.errno == error
    kill.assert_not_called()


def test_unknown_architecture_fails_closed(monkeypatch):
    monkeypatch.setattr(supervisor.platform, "machine", lambda: "unknown")
    with pytest.raises(OSError) as caught:
        supervisor._pidfd_syscall(434, 123, 0)
    assert caught.value.errno == errno.ENOSYS


@pytest.mark.parametrize(
    "mismatch,error",
    [
        (False, None),
        (True, None),
        (False, FileNotFoundError()),
        (False, ProcessLookupError()),
        (False, PermissionError(errno.EPERM, "denied")),
    ],
)
def test_identity_check_and_fd_close_on_every_outcome(monkeypatch, mismatch, error):
    from pathlib import Path

    fields = ["0"] * 20
    fields[19] = "7"
    read = (
        Mock(side_effect=error)
        if error
        else Mock(return_value="123 (child) " + " ".join(fields))
    )
    monkeypatch.setattr(Path, "read_text", read)
    monkeypatch.setattr(supervisor, "_pidfd_open", Mock(return_value=42))
    sent, closed = Mock(), Mock()
    monkeypatch.setattr(supervisor, "_pidfd_send_signal", sent)
    monkeypatch.setattr(os, "close", closed)
    row = {"pid": 123, "start_ticks": 8 if mismatch else 7}
    if isinstance(error, PermissionError):
        with pytest.raises(PermissionError):
            signal_identity(row, signal.SIGTERM)
    else:
        signal_identity(row, signal.SIGTERM)
    closed.assert_called_once_with(42)
    assert sent.called == (not mismatch and error is None)


def test_process_exited_before_pidfd_open_is_safe(monkeypatch):
    monkeypatch.setattr(
        supervisor, "_pidfd_open", Mock(side_effect=ProcessLookupError())
    )
    sent = Mock()
    monkeypatch.setattr(supervisor, "_pidfd_send_signal", sent)
    signal_identity({"pid": 123, "start_ticks": 7}, signal.SIGKILL)
    sent.assert_not_called()


@pytest.mark.parametrize(
    "error", [ProcessLookupError(), PermissionError(errno.EPERM, "denied")]
)
def test_send_failure_closes_handle_without_unsafe_fallback(monkeypatch, error):
    from pathlib import Path

    fields = ["0"] * 20
    fields[19] = "7"
    monkeypatch.setattr(
        Path, "read_text", Mock(return_value="123 (child) " + " ".join(fields))
    )
    monkeypatch.setattr(supervisor, "_pidfd_open", Mock(return_value=42))
    monkeypatch.setattr(supervisor, "_pidfd_send_signal", Mock(side_effect=error))
    closed = Mock()
    monkeypatch.setattr(os, "close", closed)
    if isinstance(error, PermissionError):
        with pytest.raises(PermissionError):
            signal_identity({"pid": 123, "start_ticks": 7}, signal.SIGKILL)
    else:
        signal_identity({"pid": 123, "start_ticks": 7}, signal.SIGKILL)
    closed.assert_called_once_with(42)


def test_tree_timeout_never_reports_cleanup_confirmed(monkeypatch):
    monkeypatch.setattr(supervisor.time, "monotonic", Mock(side_effect=[0, 0, 21]))
    monkeypatch.setattr(supervisor.time, "sleep", Mock())
    monkeypatch.setattr(supervisor, "reap", lambda: False)
    monkeypatch.setattr(supervisor, "processes", dict)
    with pytest.raises(RuntimeError, match="did not exit"):
        supervisor.stop_tree(None)
