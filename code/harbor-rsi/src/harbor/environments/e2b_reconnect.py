"""Reconnect E2B output streams to the same PID, never re-dispatch commands."""

from __future__ import annotations

import asyncio
import time
from typing import override

import httpcore
import httpx
from connectrpc.code import Code
from connectrpc.errors import ConnectError
from e2b.sandbox.commands.command_handle import CommandExitException

from harbor.environments.base import ExecResult
from harbor.environments.definition import effective_exec_cwd
from harbor.environments.e2b import E2BEnvironment


def transport_failure(error):
    return (
        isinstance(error, ConnectError) and error.code == Code.UNAVAILABLE
    ) or isinstance(error, (httpx.TransportError, httpcore.NetworkError))


async def wait_reconnecting(
    commands, handle, timeout_sec=None, retries=3, delay=1, logger=None
):
    pid = handle.pid
    deadline = time.monotonic() + timeout_sec if timeout_sec else None
    for attempt in range(retries + 1):
        try:
            if attempt:
                remaining = max(0, deadline - time.monotonic()) if deadline else 0
                if deadline and not remaining:
                    raise TimeoutError("E2B connection budget exhausted")
                handle = await commands.connect(
                    pid, timeout=remaining, request_timeout=10
                )
            return await handle.wait()
        except Exception as error:
            if not transport_failure(error) or attempt == retries:
                raise
            if logger:
                logger.warning(
                    "E2B output stream interrupted; reconnecting same PID %s (%s/%s)",
                    pid,
                    attempt + 1,
                    retries,
                )
            await asyncio.sleep(delay * (attempt + 1))


class ReconnectingE2BEnvironment(E2BEnvironment):
    """Opt-in stream reconnection without modifying the standard E2B backend."""

    @override
    async def exec(self, command, cwd=None, env=None, timeout_sec=None, user=None):
        if self._sandbox is None:
            raise RuntimeError("Sandbox not started")
        user = self._resolve_user(user)
        handle = await self._dispatch_command(
            command,
            cwd=effective_exec_cwd(cwd, self.task_env_config.workdir, self._workdir),
            env=self._merge_env(env),
            timeout_sec=timeout_sec,
            user=str(user) if user is not None else "root",
        )
        try:
            result = await wait_reconnecting(
                self._sandbox.commands,
                handle,
                timeout_sec,
                logger=getattr(self, "logger", None),
            )
        except CommandExitException as error:
            result = error
        return ExecResult(
            stdout=result.stdout, stderr=result.stderr, return_code=result.exit_code
        )
