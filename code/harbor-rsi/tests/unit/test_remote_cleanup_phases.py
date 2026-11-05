"""Bounded cleanup retains uncertainty and identifies the interrupted phase."""

import asyncio
from types import MethodType, SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from harbor_remote_docker.environment import RemoteDockerEnvironment


def fixture(resources):
    rows = []
    obj = SimpleNamespace(
        _ssh=["isolated"],
        cleanup_timeout=0.025,
        _resources=AsyncMock(side_effect=resources),
        _workspace_created=False,
        _cleanup_resources_compose_file=Mock(),
        _cleanup_env_compose_file=Mock(),
        record=lambda event, **kw: rows.append({"action": event, **kw}),
        _docker=lambda *args: list(args),
    )
    obj._cleanup_phase = MethodType(RemoteDockerEnvironment._cleanup_phase, obj)
    return obj, MethodType(RemoteDockerEnvironment.stop, obj), rows


@pytest.mark.asyncio
async def test_slow_container_delete_keeps_timeout_and_later_resources_unknown():
    obj, stop, rows = fixture(
        [{"container": ["owned-container"], "network": ["owned-network"], "volume": []}]
    )

    async def slow(command):
        await asyncio.sleep(60)

    obj._run = AsyncMock(side_effect=slow)
    with pytest.raises(TimeoutError):
        await stop(delete=True)
    assert (
        rows[-1]["action"] == "cleanup_pending"
        and rows[-1]["error_type"] == "TimeoutError"
    )
    unknown = [r for r in rows if r.get("outcome") == "UNKNOWN"]
    assert (
        unknown[-1]["phase"] == "remove_resource" and unknown[-1]["kind"] == "container"
    )
    assert (
        unknown[-1]["resource_id"] == "owned-container"
        and unknown[-1]["elapsed_sec"] >= 0.02
    )
    obj._run.assert_awaited_once()
    assert not any(r["action"] == "cleaned" for r in rows)


@pytest.mark.asyncio
async def test_already_absent_resources_are_idempotently_confirmed():
    empty = {"container": [], "network": [], "volume": []}
    obj, stop, rows = fixture([empty, empty])
    obj._run = AsyncMock()
    await stop(delete=True)
    assert rows[-1]["action"] == "cleaned"
    obj._run.assert_not_awaited()
    assert [r["phase"] for r in rows if r.get("outcome") == "ACKNOWLEDGED"] == [
        "discover_resources",
        "confirm_resources_absent",
    ]


@pytest.mark.asyncio
async def test_external_cancellation_is_not_rewritten_as_success():
    entered = asyncio.Event()
    obj, stop, rows = fixture([{"container": ["owned"], "network": [], "volume": []}])

    async def blocked(command):
        entered.set()
        await asyncio.sleep(60)

    obj._run = AsyncMock(side_effect=blocked)
    task = asyncio.create_task(stop(delete=True))
    await entered.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert (
        rows[-1]["action"] == "cleanup_pending"
        and rows[-1]["error_type"] == "CancelledError"
    )
    assert not any(r["action"] == "cleaned" for r in rows)
