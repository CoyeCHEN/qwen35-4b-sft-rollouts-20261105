"""Slow storage must not starve SSH callbacks or race native cleanup."""

import asyncio
import tempfile
import threading
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from harbor.environments.base import ExecResult
from harbor_remote_docker import environment as module
from harbor_remote_docker.environment import RemoteDockerEnvironment, _local_io
from harbor_remote_docker.transport import file_hash, pack


async def wait_started(event):
    async with asyncio.timeout(2):
        while not event.is_set():
            await asyncio.sleep(0.005)


@pytest.mark.parametrize("cancellations", [1, 2, 5])
async def test_local_io_waits_for_worker_before_propagating_cancel(cancellations):
    started = threading.Event()
    release = threading.Event()
    completed = threading.Event()
    paths = []

    def write(path):
        started.set()
        if not release.wait(2):
            raise TimeoutError("Test worker was not released")
        path.write_bytes(b"archive-complete")
        completed.set()

    async def transfer():
        with tempfile.TemporaryDirectory(prefix="localio-owned-test-") as temporary:
            path = Path(temporary) / "archive.tar"
            paths.append(path)
            await _local_io(write, path)

    task = asyncio.create_task(transfer())
    await wait_started(started)
    for _ in range(cancellations):
        task.cancel()
        await asyncio.sleep(0.01)
        assert not task.done()
        assert paths[0].parent.is_dir()
        assert not completed.is_set()
    release.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert completed.is_set()
    assert not paths[0].parent.exists()


async def test_download_copy_does_not_block_other_native_operations(
    monkeypatch, tmp_path: Path
):
    source = tmp_path / "source"
    source.mkdir()
    (source / "payload.bin").write_bytes(bytes(range(256)) * 4096)
    archive = tmp_path / "source.tar"
    pack(source, archive, contents=True)
    digest = file_hash(archive)
    destination = tmp_path / "destination"
    started = threading.Event()
    release = threading.Event()
    original = module.shutil.copytree

    def slow_copy(*args, **kwargs):
        started.set()
        if not release.wait(2):
            raise TimeoutError("Event loop did not advance during the copy")
        return original(*args, **kwargs)

    monkeypatch.setattr(module.shutil, "copytree", slow_copy)
    provider = object.__new__(RemoteDockerEnvironment)
    provider.workspace = Path("/private-test-workspace")
    provider.transfer_timeout = 5
    provider._container = AsyncMock(return_value="fixture")
    provider._copy_archive_from_container = AsyncMock()
    provider._marker_guard = lambda: ""
    provider.record = lambda *args, **kwargs: None

    async def shell(command, **kwargs):
        if "target" in kwargs:
            module.shutil.copy2(archive, kwargs["target"])
        return ExecResult(stdout=digest + " archive\n", stderr="", return_code=0)

    provider._shell = shell
    ticks = 0

    async def other_native_callbacks():
        nonlocal ticks
        await wait_started(started)
        for _ in range(5):
            await asyncio.sleep(0.005)
            ticks += 1
        release.set()

    async with asyncio.TaskGroup() as group:
        group.create_task(
            provider._transfer("/logs/agent", destination, upload=False, directory=True)
        )
        group.create_task(other_native_callbacks())
    assert ticks == 5
    assert file_hash(destination / "payload.bin") == file_hash(source / "payload.bin")


async def test_local_io_preserves_filesystem_error():
    def fail():
        raise OSError(28, "Storage full")

    with pytest.raises(OSError) as error:
        await _local_io(fail)
    assert error.value.errno == 28


async def test_upload_hash_does_not_block_callbacks(monkeypatch, tmp_path: Path):
    archive = tmp_path / "archive.tar"
    archive.write_bytes(b"public-owned-fixture")
    digest = file_hash(archive)
    started = threading.Event()
    release = threading.Event()
    original = module.file_hash

    def slow_hash(path):
        started.set()
        if not release.wait(2):
            raise TimeoutError("Event loop did not advance during upload hash")
        return original(path)

    monkeypatch.setattr(module, "file_hash", slow_hash)
    provider = object.__new__(RemoteDockerEnvironment)
    provider.workspace = Path("/private-test-workspace")
    provider.transfer_timeout = 5
    provider._marker_guard = lambda: ""
    provider._shell = AsyncMock(
        return_value=ExecResult(stdout=digest + " archive\n", stderr="", return_code=0)
    )
    provider.record = lambda *args, **kwargs: None

    async def callback():
        await wait_started(started)
        await asyncio.sleep(0.01)
        release.set()

    async with asyncio.TaskGroup() as group:
        group.create_task(provider._send_archive(archive, "archive.tar"))
        group.create_task(callback())
    assert provider._shell.await_count == 2
