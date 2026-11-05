"""Bounded subprocess I/O and checked archives; no scheduler or task state."""

import asyncio
import hashlib
import os
import re
import tarfile
from contextlib import ExitStack
from pathlib import Path, PurePosixPath
from urllib.parse import urlsplit

from harbor.environments.base import ExecResult, OutputCallback

_EXIT_WAIT_TIMEOUT_SEC = 10.0


class RemoteDockerError(RuntimeError):
    """Remote infrastructure failed or ownership could not be verified."""


def ssh_target(endpoint: str) -> list[str]:
    parsed = urlsplit(endpoint)
    if (
        parsed.scheme != "ssh"
        or not parsed.hostname
        or parsed.password
        or parsed.path not in ("", "/")
        or parsed.query
        or parsed.fragment
        or not re.fullmatch(r"[a-zA-Z0-9_.:-]+", parsed.hostname)
        or parsed.hostname.startswith("-")
        or (parsed.username and not re.fullmatch(r"[a-zA-Z0-9_.-]+", parsed.username))
    ):
        raise ValueError(
            "Expected ssh://[user@]host[:port], without credentials or socket path"
        )
    argv = [
        "ssh",
        "-T",
        "-o",
        "BatchMode=yes",
        "-o",
        "ConnectTimeout=15",
        "-o",
        "StrictHostKeyChecking=yes",
    ]
    if parsed.port:
        argv.extend(["-p", str(parsed.port)])
    if parsed.username:
        argv.extend(["-l", parsed.username])
    return [*argv, parsed.hostname]


def file_hash(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def pack(
    source: Path, target: Path, *, contents: bool = False, name: str = "input"
) -> None:
    """Preserve modes and internal relative links; refuse escaping or special inputs."""
    root = source.resolve() if source.is_dir() else source.parent.resolve()
    paths = (
        sorted(source.rglob("*"))
        if contents
        else [source, *sorted(source.rglob("*"))]
        if source.is_dir()
        else [source]
    )
    with tarfile.open(target, "w", dereference=False) as archive:
        for path in paths:
            if path.is_symlink():
                if os.path.isabs(
                    os.readlink(path)
                ) or not path.resolve().is_relative_to(root):
                    raise ValueError("Archive symlink escapes the declared input tree")
            elif not (path.is_file() or path.is_dir()):
                raise ValueError("Archive contains a special file")
            relative = path.relative_to(source).as_posix() if path != source else ""
            arcname = relative if contents else str(PurePosixPath(name) / relative)
            info = archive.gettarinfo(str(path), arcname)
            info.uid = info.gid = 0
            info.uname = info.gname = ""
            with ExitStack() as stack:
                archive.addfile(
                    info,
                    stack.enter_context(path.open("rb")) if info.isfile() else None,
                )


def unpack(source: Path, target: Path) -> None:
    """Extract to a fresh directory, rejecting unsafe links before any writes."""
    with tarfile.open(source) as archive:
        members = archive.getmembers()
        for member in members:
            if not (
                member.isfile() or member.isdir() or member.issym() or member.islnk()
            ):
                raise RemoteDockerError("Remote archive contains a special file")
            tarfile.data_filter(member, str(target))
        archive.extractall(target, members=members, filter="data")


async def run(
    argv: list[str],
    *,
    timeout: float | None,
    env: dict[str, str] | None = None,
    data: bytes | None = None,
    source: Path | None = None,
    target: Path | None = None,
    on_output: OutputCallback | None = None,
) -> ExecResult:
    """Never replay a command after an ambiguous SSH failure or cancellation."""
    with ExitStack() as stack:
        process = await asyncio.create_subprocess_exec(
            *argv,
            env=env,
            stdin=stack.enter_context(source.open("rb"))
            if source
            else asyncio.subprocess.PIPE
            if data is not None
            else asyncio.subprocess.DEVNULL,
            stdout=stack.enter_context(target.open("wb"))
            if target
            else asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        output: dict[str, list[str]] = {"stdout": [], "stderr": []}

        async def read(stream, label):
            if stream is None:
                return
            while chunk := await stream.read(65536):
                text = chunk.decode(errors="replace")
                output[label].append(text)
                if on_output:
                    await on_output(text, label)

        async def write():
            if data is not None:
                stdin = process.stdin
                if stdin is None:
                    raise RemoteDockerError("Local transport stdin pipe is unavailable")
                stdin.write(data)
                await stdin.drain()
                stdin.close()
                await stdin.wait_closed()

        try:
            async with asyncio.timeout(timeout):
                async with asyncio.TaskGroup() as group:
                    group.create_task(read(process.stdout, "stdout"))
                    group.create_task(read(process.stderr, "stderr"))
                    group.create_task(write())
                return_code = await process.wait()
        except BaseException as primary:
            if process.returncode is None:
                try:
                    process.kill()
                except ProcessLookupError:
                    pass  # The local client exited between the check and kill.
            try:
                async with asyncio.timeout(_EXIT_WAIT_TIMEOUT_SEC):
                    await process.wait()
            except TimeoutError:
                # This concerns the local SSH/Docker client only. It never
                # claims that the remote agent tree has been terminated.
                raise RemoteDockerError(
                    "Local transport exit was not acknowledged after cancellation"
                ) from primary
            raise
        return ExecResult(
            stdout="".join(output["stdout"]),
            stderr="".join(output["stderr"]),
            return_code=return_code,
        )
