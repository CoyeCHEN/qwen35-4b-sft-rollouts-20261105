"""Opt-in E2B directory transfer: bounded streams, fail-closed staging and retry."""

import asyncio
import errno
import hashlib
import io
import logging
import tarfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest

pytest.importorskip("e2b")

from harbor.environments.e2b import E2BEnvironment
from harbor.environments.e2b_resumable import ResumableE2BEnvironment
from tests.unit.environments.test_e2b import _make_env


def tar_bytes(files):
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode="w") as archive:
        for name, content in files.items():
            member = tarfile.TarInfo(name)
            member.size = len(content)
            archive.addfile(member, io.BytesIO(content))
    return stream.getvalue()


class Stream:
    def __init__(self, data, error=None):
        self.data, self.error, self.closed = data, error, False

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        self.closed = True

    async def __aiter__(self):
        yield self.data[:65536]
        if self.error:
            raise self.error
        for i in range(65536, len(self.data), 65536):
            yield self.data[i : i + 65536]


def environment(tmp_path, data, *, resumable=False):
    env = object.__new__(ResumableE2BEnvironment if resumable else E2BEnvironment)
    env._bulk_download = True
    env.logger = logging.getLogger("archive-test")
    env.trial_paths = SimpleNamespace(trial_dir=tmp_path)
    env._sandbox = SimpleNamespace(
        sandbox_id="owned-test",
        commands=SimpleNamespace(run=AsyncMock()),
        files=SimpleNamespace(read=AsyncMock()),
        connect=AsyncMock(),
    )
    env._sandbox.commands.run.side_effect = lambda cmd, **kw: SimpleNamespace(
        exit_code=0,
        stdout=f"{hashlib.sha256(data).hexdigest()}  transfer.tar\n{len(data)}\n",
        stderr="",
    )
    env._sandbox.files.read.side_effect = lambda *a, **kw: Stream(data)
    if resumable:
        env._handoff_lock = asyncio.Lock()
        env._resume_lock = asyncio.Lock()
        env._record = lambda *args, **kwargs: None
    return env


@pytest.mark.parametrize(
    "files",
    [
        {"nested/data": b"ok", ".hidden": b""},
        {f"artifacts/{i}": b"x" * 100 for i in range(10000)},
        {"large": b"x" * (8 * 1024 * 1024)},
    ],
)
async def test_stream_roundtrip_and_skip_unchanged(tmp_path, files):
    env = environment(tmp_path, tar_bytes(files))
    target = tmp_path / "output"
    await env.download_dir("/source", target)
    times = {n: (target / n).stat().st_mtime_ns for n in files}
    assert all(
        hashlib.sha256((target / n).read_bytes()).digest() == hashlib.sha256(v).digest()
        for n, v in files.items()
    )
    assert env._sandbox.files.read.await_count == 1
    assert env._sandbox.files.read.await_args.kwargs["format"] == "stream"
    await env.download_dir("/source", target)
    assert times == {n: (target / n).stat().st_mtime_ns for n in files}


@pytest.mark.parametrize("name", ["../escape", "/absolute"])
def test_member_path_escape_is_rejected_before_commit(tmp_path, name):
    p = tmp_path / "bad.tar"
    p.write_bytes(tar_bytes({"valid": b"ok", name: b"bad"}))
    staging = tmp_path / "stage"
    staging.mkdir()
    with pytest.raises(ValueError, match="Unsafe"):
        E2BEnvironment._commit_archive(p, staging, tmp_path / "target")
    assert not (tmp_path / "target").exists()


@pytest.mark.parametrize("link", ["/etc/passwd", "../../escape"])
def test_link_escape_is_rejected(tmp_path, link):
    p = tmp_path / "bad.tar"
    with tarfile.open(p, "w") as archive:
        m = tarfile.TarInfo("link")
        m.type, m.linkname = tarfile.SYMTYPE, link
        archive.addfile(m)
    with pytest.raises(tarfile.FilterError):
        E2BEnvironment._commit_archive(p, tmp_path / "stage", tmp_path / "target")
    assert not (tmp_path / "target").exists()


def test_existing_target_link_is_rejected(tmp_path):
    p = tmp_path / "a.tar"
    p.write_bytes(tar_bytes({"nested/file": b"data"}))
    target = tmp_path / "target"
    target.mkdir()
    (target / "nested").symlink_to(tmp_path)
    with pytest.raises(ValueError, match="escapes|symlink"):
        E2BEnvironment._commit_archive(p, tmp_path / "stage", target)
    assert not (tmp_path / "file").exists()


async def test_interrupted_or_corrupt_stream_never_commits(tmp_path):
    data = tar_bytes({"manifest.json": b"complete"})
    env = environment(tmp_path, data)
    stream = Stream(data, httpx.ReadTimeout("interrupted"))
    env._sandbox.files.read.side_effect = None
    env._sandbox.files.read.return_value = stream
    with pytest.raises(httpx.ReadTimeout):
        await env._download_dir_archive("/source", tmp_path / "target")
    assert stream.closed
    assert not (tmp_path / "target").exists()
    env._sandbox.files.read.return_value = Stream(b"corrupt")
    with pytest.raises(ValueError, match="mismatch"):
        await env._download_dir_archive("/source", tmp_path / "target")
    assert not (tmp_path / "target").exists()


async def test_archive_command_failure_has_no_silent_fallback(tmp_path):
    env = environment(tmp_path, b"")
    env._sandbox.commands.run.side_effect = None
    env._sandbox.commands.run.return_value = SimpleNamespace(
        exit_code=1, stdout="", stderr="tar missing"
    )
    with pytest.raises(RuntimeError, match="archive failed"):
        await env._download_dir_archive("/source", tmp_path / "target")
    env._sandbox.files.read.assert_not_awaited()


async def test_resumable_boundary_recovers_failed_stream(tmp_path, monkeypatch):
    data = tar_bytes({"data": b"valid"})
    env = environment(tmp_path, data, resumable=True)
    streams = [Stream(data, httpx.ConnectError("disconnected")), Stream(data)]
    env._sandbox.files.read.side_effect = streams
    monkeypatch.setattr("harbor.environments.e2b_resumable.asyncio.sleep", AsyncMock())
    await env._safe_io(
        lambda: env._download_dir_archive("/source", tmp_path / "target")
    )
    env._sandbox.connect.assert_awaited_once()
    assert (tmp_path / "target/data").read_bytes() == b"valid"
    assert env._io_owner is None


@pytest.mark.parametrize("transfer_fails", [False, True])
@pytest.mark.parametrize("cleanup_fails", [False, True])
async def test_evidence_write_failure_preserves_error_and_attempts_cleanup(
    tmp_path, monkeypatch, transfer_fails, cleanup_fails
):
    data = tar_bytes({"data": b"valid"})
    env = environment(tmp_path, data)
    transfer_error = httpx.ReadTimeout("interrupted")
    env._sandbox.files.read.side_effect = None
    env._sandbox.files.read.return_value = Stream(
        data, transfer_error if transfer_fails else None
    )
    archive_result = env._sandbox.commands.run.side_effect

    def command_result(command, **kwargs):
        if command.startswith("rm -f --") and cleanup_fails:
            raise RuntimeError("cleanup failed")
        return archive_result(command, **kwargs)

    env._sandbox.commands.run.side_effect = command_result
    evidence_error = OSError(errno.ENOSPC, "evidence disk full")
    original_open = Path.open

    def open_path(path, *args, **kwargs):
        if path == tmp_path / "e2b-transfers.jsonl":
            raise evidence_error
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", open_path)
    expected = transfer_error if transfer_fails else evidence_error
    target = tmp_path / "target"
    with pytest.raises(type(expected)) as caught:
        await env._download_dir_archive("/source", target)

    assert caught.value is expected
    assert target.exists() is not transfer_fails
    assert env._sandbox.files.read.return_value.closed
    assert env._sandbox.commands.run.await_args.args[0].startswith("rm -f --")


async def test_default_download_uses_existing_file_listing(tmp_path):
    env = _make_env(tmp_path)
    env._sandbox = SimpleNamespace(
        files=SimpleNamespace(list=AsyncMock(return_value=[])),
        commands=SimpleNamespace(run=AsyncMock()),
    )

    await env.download_dir("/source", tmp_path / "target")

    env._sandbox.files.list.assert_awaited_once_with("/source")
    env._sandbox.commands.run.assert_not_awaited()
