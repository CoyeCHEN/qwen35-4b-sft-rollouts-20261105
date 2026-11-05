"""E2B memory resume and durable command results without command replay.

Task deadlines remain host wall-clock deadlines. A sandbox timeout pauses the
same VM; a failed observation reconnects it and reads the original command's
files. For a longer agent command, ``fork`` creates a new running copy with
the complete memory state; the source is validated and killed immediately
afterward. The provider briefly has both copies running during that handoff,
so this path is only for a single active agent command and is recorded as a
lifecycle boundary. No agent session or task is restarted.
"""

from __future__ import annotations

import asyncio
import json
import shlex
import time
import uuid
from typing import Any, cast, override

import httpx
from connectrpc.errors import ConnectError
from e2b import AsyncSandbox
from e2b.exceptions import (
    FileNotFoundException,
    SandboxNotFoundException,
    TimeoutException,
)

from harbor.environments.base import ExecResult
from harbor.environments.definition import effective_exec_cwd
from harbor.models.task.config import NetworkMode

from .e2b_one_hour import OneHourE2BEnvironment

RECOVERABLE = (
    ConnectError,
    httpx.TransportError,
    TimeoutException,
    SandboxNotFoundException,
)


def durable_command(command: str, directory: str) -> str:
    path = shlex.quote(directory)
    return (
        f"mkdir -p {path} || exit $?; "
        f"if /bin/bash -lc {shlex.quote(command)} >{path}/stdout 2>{path}/stderr; "
        "then result=0; else result=$?; fi; "
        f"printf '%s\\n' \"$result\" >{path}/exit.tmp && "
        f"mv {path}/exit.tmp {path}/exit"
    )


class ResumableE2BEnvironment(OneHourE2BEnvironment):
    POLL_SECONDS = 2
    HANDOFF_MARGIN_SECONDS = 180
    _IDENTITY_PATH = "/tmp/harbor-rsi-sandbox-identity.json"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._resume_lock = asyncio.Lock()
        self._handoff_lock = asyncio.Lock()
        self._io_owner: asyncio.Task[Any] | None = None
        self._sandbox_started_at: float | None = None
        self._active_command_dirs: set[str] = set()
        self._retired_sandboxes: list[AsyncSandbox] = []

    def _record(self, event, **details):
        path = self.trial_paths.trial_dir / "e2b-lifecycle.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a") as output:
            output.write(
                json.dumps(dict(time=time.time(), event=event, **details)) + "\n"
            )

    @override
    async def _create_sandbox(self):
        self._sandbox = await AsyncSandbox.create(
            template=self._template_name,
            metadata={
                "environment_name": self.environment_name,
                "session_id": self.session_id,
            },
            envs=self._startup_env(),
            timeout=self.SANDBOX_TIMEOUT_SECONDS,
            lifecycle={
                "on_timeout": {"action": "pause", "keep_memory": True},
                "auto_resume": False,
            },
            allow_internet_access=self.network_policy.network_mode
            != NetworkMode.NO_NETWORK,
            network=self._sandbox_create_network_options(),
        )
        await self._sandbox.files.write(
            self._IDENTITY_PATH,
            json.dumps(
                {
                    "environment_name": self.environment_name,
                    "session_id": self.session_id,
                }
            ),
        )
        self._sandbox_started_at = time.monotonic()
        self._record(
            "created",
            sandbox_id=self._sandbox.sandbox_id,
            timeout=self.SANDBOX_TIMEOUT_SECONDS,
        )

    async def _validate_handoff(self, sandbox: AsyncSandbox) -> None:
        if sandbox.sandbox_id == cast(AsyncSandbox, self._sandbox).sandbox_id:
            raise RuntimeError("E2B fork returned the source sandbox")
        identity = await sandbox.files.read(self._IDENTITY_PATH)
        data = json.loads(identity)
        if data != {
            "environment_name": self.environment_name,
            "session_id": self.session_id,
        }:
            raise RuntimeError("E2B fork identity does not match the trial")
        if self._workdir is not None:
            await sandbox.files.list(self._workdir)
        for directory in self._active_command_dirs:
            await sandbox.files.list(directory)

    async def _maybe_handoff(self) -> None:
        started_at = self._sandbox_started_at
        if started_at is None or self._sandbox is None:
            return
        if (
            time.monotonic() - started_at
            < self.SANDBOX_TIMEOUT_SECONDS - self.HANDOFF_MARGIN_SECONDS
        ):
            return

        async with self._handoff_lock:
            if self._sandbox is None or self._sandbox_started_at is None:
                return
            if (
                time.monotonic() - self._sandbox_started_at
                < self.SANDBOX_TIMEOUT_SECONDS - self.HANDOFF_MARGIN_SECONDS
            ):
                return
            source = self._sandbox
            self._record("handoff_started", source_sandbox_id=source.sandbox_id)
            forks = await source.fork(
                timeout=self.SANDBOX_TIMEOUT_SECONDS,
                count=1,
            )
            if len(forks) != 1 or isinstance(forks[0], BaseException):
                error = (
                    forks[0] if forks else RuntimeError("E2B fork returned no sandbox")
                )
                raise RuntimeError("E2B sandbox handoff failed") from error
            child = forks[0]
            try:
                await self._validate_handoff(child)
            except Exception:
                try:
                    await child.kill()
                except Exception:
                    self.logger.exception("Could not clean up invalid E2B fork")
                raise

            self._sandbox = child
            self._sandbox_started_at = time.monotonic()
            retired = getattr(self, "_retired_sandboxes", None)
            if retired is None:
                retired = self._retired_sandboxes = []
            retired.append(source)
            try:
                await source.kill()
            except Exception as error:
                self._record(
                    "handoff_cleanup_failed",
                    source_sandbox_id=source.sandbox_id,
                    child_sandbox_id=child.sandbox_id,
                    error_type=type(error).__name__,
                )
                raise RuntimeError(
                    "Could not terminate the source E2B sandbox"
                ) from error
            self._record(
                "handoff_completed",
                source_sandbox_id=source.sandbox_id,
                sandbox_id=child.sandbox_id,
            )

    async def _kill_active_command(self, pid: int) -> None:
        sandbox = self._sandbox
        if sandbox is None:
            return
        try:
            handle = await sandbox.commands.connect(pid, request_timeout=30)
            await handle.kill()
        except Exception:
            self.logger.exception("Could not stop active command %s", pid)

    async def _safe_io(self, operation):
        if self._sandbox is None:
            raise RuntimeError("Sandbox not started")
        current_task = asyncio.current_task()
        # Official directory download recurses through self.download_dir and
        # self.download_file. Those calls are already protected by the outer
        # operation; reacquiring the same non-reentrant lock would self-deadlock.
        # Task identity keeps independently scheduled operations serialized.
        if (
            current_task is not None
            and getattr(self, "_io_owner", None) is current_task
        ):
            return await operation()
        handoff_lock = getattr(self, "_handoff_lock", None)
        if handoff_lock is None:
            handoff_lock = self._handoff_lock = asyncio.Lock()
        # Only idempotent observation/upload operations may enter this retry.
        for attempt in range(3):
            try:
                async with handoff_lock:
                    self._io_owner = current_task
                    try:
                        return await operation()
                    finally:
                        self._io_owner = None
            except RECOVERABLE as error:
                if attempt == 2:
                    raise
                self._record("reconnect", error_type=type(error).__name__)
                async with self._resume_lock:
                    sandbox = self._sandbox
                    if sandbox is None:
                        raise RuntimeError("Sandbox stopped during reconnect")
                    await sandbox.connect(
                        timeout=self.SANDBOX_TIMEOUT_SECONDS,
                        on_resume="restore",
                        request_timeout=30,
                    )
                await asyncio.sleep(1)

    @override
    async def exec(self, command, cwd=None, env=None, timeout_sec=None, user=None):
        if self._sandbox is None:
            raise RuntimeError("Sandbox not started")
        directory = "/tmp/harbor-exec-" + uuid.uuid4().hex
        self._active_command_dirs.add(directory)
        # Ensure a paused sandbox is running BEFORE dispatch; do not retry a
        # post-dispatch failure because the command may already have started.
        await self._safe_io(
            lambda: cast(AsyncSandbox, self._sandbox).files.list("/tmp")
        )
        async with self._handoff_lock:
            handle = await self._dispatch_command(
                durable_command(command, directory),
                cwd=effective_exec_cwd(
                    cwd, self.task_env_config.workdir, self._workdir
                ),
                env=self._merge_env(env),
                timeout_sec=None,
                user=str(self._resolve_user(user) or "root"),
            )
            await handle.disconnect()
        missing = 0
        last_check = time.monotonic()
        try:
            async with asyncio.timeout(timeout_sec or None):
                while True:
                    await self._maybe_handoff()
                    try:
                        status = await self._safe_io(
                            lambda: cast(AsyncSandbox, self._sandbox).files.read(
                                directory + "/exit"
                            )
                        )
                        break
                    except FileNotFoundException:
                        if time.monotonic() - last_check > 30:
                            processes = await self._safe_io(
                                lambda: cast(
                                    AsyncSandbox, self._sandbox
                                ).commands.list()
                            )
                            missing = (
                                missing + 1
                                if not any(p.pid == handle.pid for p in processes)
                                else 0
                            )
                            if missing >= 2:
                                raise RuntimeError(
                                    f"Command {handle.pid} disappeared without durable exit status"
                                )
                            last_check = time.monotonic()
                        await asyncio.sleep(self.POLL_SECONDS)
                stdout = await self._safe_io(
                    lambda: cast(AsyncSandbox, self._sandbox).files.read(
                        directory + "/stdout"
                    )
                )
                stderr = await self._safe_io(
                    lambda: cast(AsyncSandbox, self._sandbox).files.read(
                        directory + "/stderr"
                    )
                )
                return ExecResult(
                    stdout=stdout, stderr=stderr, return_code=int(status.strip())
                )
        except (TimeoutError, asyncio.CancelledError):
            # Agent-phase descendant cleanup is enforced by the existing
            # lifecycle barrier. This stops the remaining remote waiter.
            try:
                await self._kill_active_command(handle.pid)
            except Exception:
                self.logger.exception(
                    "Could not stop remote command waiter %s", handle.pid
                )
            raise
        finally:
            self._active_command_dirs.discard(directory)

    @override
    async def upload_file(self, source_path, target_path):
        return await self._safe_io(
            lambda: super(ResumableE2BEnvironment, self).upload_file(
                source_path, target_path
            )
        )

    @override
    async def upload_dir(self, source_dir, target_dir):
        return await self._safe_io(
            lambda: super(ResumableE2BEnvironment, self).upload_dir(
                source_dir, target_dir
            )
        )

    @override
    async def download_file(self, source_path, target_path):
        return await self._safe_io(
            lambda: super(ResumableE2BEnvironment, self).download_file(
                source_path, target_path
            )
        )

    @override
    async def download_dir(self, source_dir, target_dir):
        return await self._safe_io(
            lambda: super(ResumableE2BEnvironment, self).download_dir(
                source_dir, target_dir
            )
        )

    @override
    async def _apply_network_policy(self, network_policy):
        return await self._safe_io(
            lambda: super(ResumableE2BEnvironment, self)._apply_network_policy(
                network_policy
            )
        )

    @override
    async def stop(self, delete: bool):
        await super().stop(delete=delete)
        retired = self._retired_sandboxes
        self._retired_sandboxes = []
        for sandbox in retired:
            try:
                await sandbox.kill()
            except Exception:
                self.logger.exception(
                    "Could not clean up retired E2B sandbox %s", sandbox.sandbox_id
                )
