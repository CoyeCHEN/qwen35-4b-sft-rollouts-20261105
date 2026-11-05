"""Sandbox-side Linux process ownership; stdlib only, independent of any agent."""

import ctypes
import errno
import json
import os
import platform
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


def _linux_fcntl():
    if sys.platform != "linux":
        raise NotImplementedError("Sandbox process supervision requires Linux /proc")
    try:
        import fcntl
    except ImportError as error:
        raise NotImplementedError(
            "Sandbox process supervision requires Linux fcntl"
        ) from error
    return fcntl


def write_json(path, value):
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value) + "\n")
    temporary.replace(path)


def processes():
    rows = {}
    for path in Path("/proc").iterdir():
        if not path.name.isdigit():
            continue
        try:
            stat = (path / "stat").read_text()
            fields = stat[stat.rfind(")") + 2 :].split()
            rows[int(path.name)] = {
                "pid": int(path.name),
                "ppid": int(fields[1]),
                "state": fields[0],
                "start_ticks": int(fields[19]),
            }
        except (FileNotFoundError, ProcessLookupError):
            pass
    return rows


def descendants(rows, root):
    found = {root}
    while True:
        children = {pid for pid, row in rows.items() if row["ppid"] in found}
        enlarged = found | children
        if enlarged == found:
            return {pid: rows[pid] for pid in found - {root}}
        found = enlarged


def reap():
    while True:
        try:
            if os.waitpid(-1, os.WNOHANG)[0] == 0:
                return False
        except ChildProcessError:
            return True


def _pidfd_syscall(number, *args):
    # Managed Python builds may omit os.pidfd_open or signal.pidfd_send_signal
    # even when the Linux kernel supplies both syscalls. Keep the PID handle
    # contract instead of falling back to a PID-reuse-prone os.kill.
    if platform.machine() not in ("x86_64", "aarch64", "riscv64"):
        raise OSError(errno.ENOSYS, "pidfd syscall number unavailable for architecture")
    libc = ctypes.CDLL(None, use_errno=True)
    value = libc.syscall(number, *args)
    if value == -1:
        error = ctypes.get_errno()
        raise OSError(error, os.strerror(error))
    return value


def _pidfd_open(pid):
    if hasattr(os, "pidfd_open"):
        return os.pidfd_open(pid)
    return _pidfd_syscall(434, pid, 0)


def _pidfd_send_signal(fd, sig):
    if hasattr(signal, "pidfd_send_signal"):
        signal.pidfd_send_signal(fd, sig)
    else:
        _pidfd_syscall(424, fd, sig, 0, 0)


def signal_identity(row, sig):
    # Hold a kernel PID handle while checking identity, so an exited/reaped
    # grandchild cannot turn a signal into a signal to an unrelated process.
    try:
        fd = _pidfd_open(row["pid"])
    except ProcessLookupError:
        return
    try:
        try:
            stat = Path(f"/proc/{row['pid']}/stat").read_text()
            start = int(stat[stat.rfind(")") + 2 :].split()[19])
            if start == row["start_ticks"]:
                _pidfd_send_signal(fd, sig)
        except (FileNotFoundError, ProcessLookupError):
            pass
    finally:
        os.close(fd)


def stop_tree(state):
    # Freeze parents before rescanning: setsid/double-fork cannot escape a
    # living subreaper, and stopped ancestors cannot create new descendants.
    deadline = time.monotonic() + 20
    seen = {}
    rows = {}
    frozen_at = None
    while time.monotonic() < deadline:
        no_children = reap()
        rows = descendants(processes(), os.getpid())
        seen.update({(pid, row["start_ticks"]): row for pid, row in rows.items()})
        # /proc enumeration is not atomic. ECHILD from the living subreaper
        # supplies the kernel barrier even if a fork races with that scan.
        if no_children and not rows:
            return {
                "frozen_at": frozen_at or time.time(),
                "stopped_at": time.time(),
                "processes": list(seen.values()),
                "remaining": [],
                "kernel_no_children": True,
            }
        if rows and all(row["state"] in ("T", "t", "Z", "X") for row in rows.values()):
            frozen_at = time.time()
            for row in rows.values():
                signal_identity(row, signal.SIGKILL)
        else:
            for row in rows.values():
                signal_identity(row, signal.SIGSTOP)
        time.sleep(0.01)
    raise RuntimeError("Owned processes did not exit: " + json.dumps(rows))


def serve(state, command):
    fcntl = _linux_fcntl()
    with (state / "lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if (state / "cancel").exists():
            return
        libc = ctypes.CDLL(None, use_errno=True)
        if libc.prctl(36, 1, 0, 0, 0) != 0:  # PR_SET_CHILD_SUBREAPER
            raise OSError(ctypes.get_errno(), "PR_SET_CHILD_SUBREAPER failed")
        identity = processes()[os.getpid()]
        write_json(state / "owner.json", identity)
        with (state / "stdout").open("wb") as out, (state / "stderr").open("wb") as err:
            child = subprocess.Popen(["bash", "-c", command], stdout=out, stderr=err)
        write_json(state / "started.json", {"at": time.time(), "pid": child.pid})
    while True:
        if (state / "cancel").exists():
            try:
                write_json(state / "stopped.json", stop_tree(state))
            except BaseException as exc:  # noqa: BLE001 - retain process ownership on every cleanup failure
                write_json(state / "error.json", {"error": repr(exc)})
                # Retain ownership on failure. Host must abort verification.
                while True:
                    time.sleep(1)
            return
        code = child.poll()
        if code is not None and not (state / "result.json").exists():
            write_json(state / "result.json", {"return_code": code, "at": time.time()})
        if (state / "release").exists():
            return  # Normal completion deliberately leaves services alive.
        time.sleep(0.02)


def control(state, action):
    fcntl = _linux_fcntl()
    state.mkdir(mode=0o700, parents=True, exist_ok=True)
    with (state / "lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        (state / action).touch()
        owner_path = state / "owner.json"
        owner = json.loads(owner_path.read_text()) if owner_path.exists() else None
    deadline = time.monotonic() + 25
    while time.monotonic() < deadline:
        rows = processes()
        current = rows.get(owner["pid"]) if owner else None
        alive = (
            owner is not None
            and current is not None
            and current["start_ticks"] == owner["start_ticks"]
            and current["state"] not in ("Z", "X")
        )
        if not alive:
            if action == "cancel":
                stopped = state / "stopped.json"
                if owner and not stopped.exists():
                    raise RuntimeError(
                        "Supervisor disappeared without cleanup acknowledgement"
                    )
                report: dict[str, Any] = (
                    json.loads(stopped.read_text())
                    if owner
                    else {
                        "stopped_at": time.time(),
                        "remaining": [],
                        "not_started": True,
                    }
                )
                # PID identities prevent confusing PID reuse with a survivor.
                survivors = [
                    p
                    for p in report.get("processes", [])
                    if p["pid"] in rows
                    and rows[p["pid"]]["start_ticks"] == p["start_ticks"]
                ]
                if survivors:
                    raise RuntimeError(
                        "Processes still present: " + json.dumps(survivors)
                    )
                report["confirmed_at"] = time.time()
                print(json.dumps(report))
            return
        error = state / "error.json"
        if error.exists():
            raise RuntimeError(error.read_text())
        time.sleep(0.02)
    raise RuntimeError("Supervisor did not acknowledge " + action)


def waiter_exit_code(return_code: int) -> int:
    """Preserve the native waiter's existing sys.exit integer, including signals."""
    return return_code if return_code >= 0 else 128 - return_code


def main():
    fcntl = _linux_fcntl()
    action, directory = sys.argv[1:3]
    state = Path(directory)
    if action == "start":
        state.mkdir(mode=0o700, parents=True, exist_ok=True)
        with (state / "lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            if not (state / "cancel").exists():
                with (state / "supervisor.log").open("ab") as log:
                    subprocess.Popen(
                        [sys.executable, __file__, "serve", directory, sys.argv[3]],
                        stdin=subprocess.DEVNULL,
                        stdout=log,
                        stderr=log,
                        start_new_session=True,
                    )
    elif action == "serve":
        serve(state, sys.argv[3])
    elif action == "completed":
        result = json.loads((state / "result.json").read_text())
        code = result.get("return_code") if isinstance(result, dict) else None
        if not isinstance(code, int) or isinstance(code, bool):
            raise RuntimeError("Invalid native command completion acknowledgement")
        print(json.dumps(result))
    elif action == "wait":
        while not (state / "result.json").exists():
            if (state / "cancel").exists():
                return 125
            time.sleep(0.02)
        result = json.loads((state / "result.json").read_text())
        for name, stream in (("stdout", sys.stdout), ("stderr", sys.stderr)):
            with (state / name).open("rb") as handle:
                while chunk := handle.read(65536):
                    stream.buffer.write(chunk)
            stream.flush()
        return waiter_exit_code(result["return_code"])
    else:
        control(state, action)
    return 0


if __name__ == "__main__":
    sys.exit(main())
