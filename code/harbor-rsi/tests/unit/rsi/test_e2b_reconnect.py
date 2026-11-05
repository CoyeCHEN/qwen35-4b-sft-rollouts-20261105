import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

from connectrpc.code import Code
from connectrpc.errors import ConnectError
import pytest

from harbor.environments.e2b_reconnect import wait_reconnecting


def test_reconnects_same_pid_without_running_command_again():
    first = SimpleNamespace(
        pid=42, wait=AsyncMock(side_effect=ConnectError(Code.UNAVAILABLE, "reset"))
    )
    second = SimpleNamespace(wait=AsyncMock(return_value="done"))
    commands = SimpleNamespace(connect=AsyncMock(return_value=second), run=AsyncMock())
    assert asyncio.run(wait_reconnecting(commands, first, delay=0)) == "done"
    assert commands.connect.await_args.args == (42,)
    commands.run.assert_not_awaited()


def test_command_failure_is_not_reconnected():
    handle = SimpleNamespace(
        pid=42, wait=AsyncMock(side_effect=ValueError("command failed"))
    )
    commands = SimpleNamespace(connect=AsyncMock())
    with pytest.raises(ValueError):
        asyncio.run(wait_reconnecting(commands, handle, delay=0))
    commands.connect.assert_not_awaited()


def test_reconnect_is_bounded_and_respects_cancellation():
    error = ConnectError(Code.UNAVAILABLE, "reset")
    handle = SimpleNamespace(pid=42, wait=AsyncMock(side_effect=error))
    commands = SimpleNamespace(connect=AsyncMock(side_effect=error))
    with pytest.raises(ConnectError):
        asyncio.run(wait_reconnecting(commands, handle, retries=2, delay=0))
    assert commands.connect.await_count == 2
    handle.wait = AsyncMock(side_effect=asyncio.CancelledError)
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(wait_reconnecting(commands, handle, delay=0))
