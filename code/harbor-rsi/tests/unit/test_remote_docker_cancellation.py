"""Local subprocess fault injection; no SSH, Docker, or model calls."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from harbor_remote_docker import transport


async def test_transport_bounds_exit_acknowledgement_after_timeout(monkeypatch):
    async def blocked_read(*args):
        await asyncio.sleep(10)

    async def delayed_wait():
        await asyncio.sleep(1)

    process = SimpleNamespace(
        stdout=SimpleNamespace(read=blocked_read),
        stderr=SimpleNamespace(read=blocked_read),
        returncode=None,
        kill=Mock(),
        wait=delayed_wait,
    )
    monkeypatch.setattr(
        asyncio, "create_subprocess_exec", AsyncMock(return_value=process)
    )
    monkeypatch.setattr(transport, "_EXIT_WAIT_TIMEOUT_SEC", 0.02, raising=False)
    with pytest.raises(transport.RemoteDockerError, match="exit was not acknowledged"):
        await asyncio.wait_for(transport.run(["fixture"], timeout=0.005), 0.2)
    process.kill.assert_called_once()


async def test_transport_cancel_terminates_local_client_and_preserves_cancel(
    monkeypatch,
):
    ready = asyncio.Event()

    async def blocked_read(*args):
        ready.set()
        await asyncio.sleep(10)

    process = SimpleNamespace(
        stdout=SimpleNamespace(read=blocked_read),
        stderr=None,
        returncode=None,
        kill=Mock(),
        wait=AsyncMock(return_value=-9),
    )
    monkeypatch.setattr(
        asyncio, "create_subprocess_exec", AsyncMock(return_value=process)
    )
    task = asyncio.create_task(transport.run(["fixture"], timeout=None))
    await ready.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    process.kill.assert_called_once()
    process.wait.assert_awaited_once()


async def test_transport_timeout_reaps_real_local_client():
    import sys

    started = asyncio.get_running_loop().time()
    with pytest.raises(TimeoutError):
        await transport.run(
            [sys.executable, "-c", "import time; time.sleep(60)"], timeout=0.02
        )
    assert asyncio.get_running_loop().time() - started < 2
