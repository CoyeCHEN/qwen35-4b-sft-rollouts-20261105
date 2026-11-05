"""Official recursive file methods must not reacquire our handoff guard."""

import asyncio
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest

from harbor.environments.e2b import FileType
from harbor.environments.e2b_resumable import ResumableE2BEnvironment


def environment() -> ResumableE2BEnvironment:
    env = object.__new__(ResumableE2BEnvironment)
    env._handoff_lock = asyncio.Lock()
    env._resume_lock = asyncio.Lock()
    env._sandbox = SimpleNamespace(
        files=SimpleNamespace(
            list=AsyncMock(), read=AsyncMock(return_value=b"official-data")
        ),
        connect=AsyncMock(),
    )
    env._record = lambda *args, **kwargs: None
    return env


@pytest.mark.parametrize("source", ["/workspace", "/logs/verifier"])
async def test_native_recursive_directory_download(source: str, tmp_path: Path) -> None:
    env = environment()

    async def listing(path: str):
        return (
            [SimpleNamespace(path=source + "/nested", type=FileType.DIR)]
            if path == source
            else [SimpleNamespace(path=source + "/nested/output", type=FileType.FILE)]
        )

    env._sandbox.files.list.side_effect = listing
    await asyncio.wait_for(env.download_dir(source, tmp_path), timeout=0.2)
    assert (tmp_path / "nested/output").read_bytes() == b"official-data"
    assert not env._handoff_lock.locked()


async def test_nested_safe_io_does_not_let_another_task_enter() -> None:
    env = environment()
    entered = asyncio.Event()
    release = asyncio.Event()
    second = asyncio.Event()

    async def nested():
        entered.set()
        await release.wait()

    async def parent():
        await env._safe_io(nested)

    async def other():
        second.set()

    async with asyncio.TaskGroup() as group:
        first = group.create_task(env._safe_io(parent))
        await asyncio.wait_for(entered.wait(), 0.2)
        group.create_task(env._safe_io(other))
        await asyncio.sleep(0)
        assert not second.is_set()
        release.set()
        await asyncio.wait_for(first, 0.2)
    assert second.is_set()


async def test_cancellation_releases_recursive_owner() -> None:
    env = environment()

    async def leaf():
        await asyncio.Event().wait()

    async def parent():
        await env._safe_io(leaf)

    with pytest.raises(TimeoutError):
        await asyncio.wait_for(env._safe_io(parent), 0.02)
    assert not env._handoff_lock.locked()
    assert env._io_owner is None
    assert (
        await asyncio.wait_for(env._safe_io(AsyncMock(return_value="next")), 0.2)
        == "next"
    )


async def test_nested_transport_error_recovers_only_at_outer_boundary(
    monkeypatch,
) -> None:
    env = environment()
    leaf = AsyncMock(side_effect=[httpx.ConnectError("disconnected"), "restored"])

    async def parent():
        return await env._safe_io(leaf)

    monkeypatch.setattr("harbor.environments.e2b_resumable.asyncio.sleep", AsyncMock())
    assert await asyncio.wait_for(env._safe_io(parent), 0.2) == "restored"
    assert env._sandbox.connect.await_count == 1
    assert leaf.await_count == 2
    assert env._io_owner is None


async def test_separate_environments_do_not_share_recursive_owner() -> None:
    first, second = environment(), environment()
    entered = asyncio.Event()
    release = asyncio.Event()

    async def operation():
        entered.set()
        await release.wait()

    async with asyncio.TaskGroup() as group:
        group.create_task(first._safe_io(operation))
        await entered.wait()
        assert (
            await asyncio.wait_for(
                second._safe_io(AsyncMock(return_value="independent")), 0.2
            )
            == "independent"
        )
        release.set()
