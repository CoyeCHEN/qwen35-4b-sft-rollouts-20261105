import asyncio
import json
import time
from types import SimpleNamespace

import httpx
import pytest

from harbor.environments.e2b_resumable import ResumableE2BEnvironment, durable_command


def test_durable_command_publishes_exit_after_output():
    command = durable_command("printf ok; exit 7", "/tmp/result path")
    assert ">'/tmp/result path'/stdout" in command
    assert "2>'/tmp/result path'/stderr" in command
    assert "mv '/tmp/result path'/exit.tmp '/tmp/result path'/exit" in command
    assert "printf '%s\\n' \"$result\"" in command


def test_safe_io_reconnects_observation_without_dispatch():
    class Files:
        def __init__(self):
            self.calls = 0

        async def list(self, path):
            self.calls += 1
            if self.calls == 1:
                raise httpx.ConnectError(
                    "connection dropped", request=httpx.Request("GET", "https://e2b")
                )
            return ["ok"]

    class Sandbox:
        def __init__(self):
            self.files = Files()
            self.connect_calls = []

        async def connect(self, **kwargs):
            self.connect_calls.append(kwargs)

    environment = object.__new__(ResumableE2BEnvironment)
    environment._sandbox = Sandbox()
    environment._resume_lock = asyncio.Lock()
    records = []
    environment._record = lambda event, **details: records.append((event, details))

    result = asyncio.run(
        environment._safe_io(lambda: environment._sandbox.files.list("/tmp"))
    )
    assert result == ["ok"]
    assert environment._sandbox.files.calls == 2
    assert len(environment._sandbox.connect_calls) == 1
    assert records[0][0] == "reconnect"


def test_safe_io_does_not_reconnect_successful_observation():
    class Sandbox:
        def __init__(self):
            self.files = SimpleNamespace(list=self.list)
            self.connect_calls = 0

        async def list(self, path):
            return [path]

        async def connect(self, **kwargs):
            self.connect_calls += 1

    environment = object.__new__(ResumableE2BEnvironment)
    environment._sandbox = Sandbox()
    environment._resume_lock = asyncio.Lock()
    environment._record = lambda *args, **kwargs: (_ for _ in ()).throw(
        AssertionError("successful observations must not reconnect")
    )
    assert asyncio.run(
        environment._safe_io(lambda: environment._sandbox.files.list("/tmp"))
    ) == ["/tmp"]
    assert environment._sandbox.connect_calls == 0


def test_handoff_replaces_sandbox_and_kills_source():
    class Files:
        async def read(self, path):
            assert path == ResumableE2BEnvironment._IDENTITY_PATH
            return json.dumps({"environment_name": "science", "session_id": "trial"})

        async def list(self, path):
            return [path]

    class Sandbox:
        def __init__(self, sandbox_id):
            self.sandbox_id = sandbox_id
            self.files = Files()
            self.killed = False

        async def fork(self, **kwargs):
            assert kwargs == {"timeout": 3600, "count": 1}
            return [Sandbox("child")]

        async def kill(self):
            self.killed = True

    environment = object.__new__(ResumableE2BEnvironment)
    source = Sandbox("source")
    environment._sandbox = source
    environment.SANDBOX_TIMEOUT_SECONDS = 3600
    environment.HANDOFF_MARGIN_SECONDS = 180
    environment._sandbox_started_at = (
        time.monotonic()
        - environment.SANDBOX_TIMEOUT_SECONDS
        + environment.HANDOFF_MARGIN_SECONDS
        - 1
    )
    environment._handoff_lock = asyncio.Lock()
    environment._active_command_dirs = {"/tmp/harbor-exec-active"}
    environment._workdir = "/workspace"
    environment.environment_name = "science"
    environment.session_id = "trial"
    environment._record = lambda *args, **kwargs: None
    environment.logger = SimpleNamespace(exception=lambda *args, **kwargs: None)

    asyncio.run(environment._maybe_handoff())

    assert environment._sandbox.sandbox_id == "child"
    assert source.killed is True
    assert environment._retired_sandboxes == [source]


def test_handoff_rejects_identity_mismatch_and_cleans_child():
    class Files:
        async def read(self, path):
            return json.dumps({"environment_name": "other", "session_id": "trial"})

        async def list(self, path):
            return [path]

    class Sandbox:
        def __init__(self, sandbox_id):
            self.sandbox_id = sandbox_id
            self.files = Files()
            self.killed = False
            self.child = None

        async def fork(self, **kwargs):
            self.child = Sandbox("child")
            return [self.child]

        async def kill(self):
            self.killed = True

    environment = object.__new__(ResumableE2BEnvironment)
    source = Sandbox("source")
    environment._sandbox = source
    environment.SANDBOX_TIMEOUT_SECONDS = 3600
    environment.HANDOFF_MARGIN_SECONDS = 180
    environment._sandbox_started_at = (
        time.monotonic()
        - environment.SANDBOX_TIMEOUT_SECONDS
        + environment.HANDOFF_MARGIN_SECONDS
        - 1
    )
    environment._handoff_lock = asyncio.Lock()
    environment._active_command_dirs = set()
    environment._workdir = "/workspace"
    environment.environment_name = "science"
    environment.session_id = "trial"
    environment._record = lambda *args, **kwargs: None
    environment.logger = SimpleNamespace(exception=lambda *args, **kwargs: None)

    with pytest.raises(RuntimeError, match="identity"):
        asyncio.run(environment._maybe_handoff())

    assert source.killed is False
    assert source.child is not None and source.child.killed is True


async def test_handoff_without_dockerfile_workdir_validates_identity_and_commands():
    from unittest.mock import AsyncMock

    environment = object.__new__(ResumableE2BEnvironment)
    environment.environment_name = "trial"
    environment.session_id = "session"
    environment._sandbox = SimpleNamespace(sandbox_id="source")
    environment._workdir = None  # Dockerfiles are allowed to omit WORKDIR.
    environment._active_command_dirs = {"/tmp/harbor-exec-fixture"}
    child = SimpleNamespace(
        sandbox_id="child",
        files=SimpleNamespace(
            read=AsyncMock(
                return_value=json.dumps(
                    {"environment_name": "trial", "session_id": "session"}
                )
            ),
            list=AsyncMock(),
        ),
    )
    await environment._validate_handoff(child)
    child.files.read.assert_awaited_once_with(environment._IDENTITY_PATH)
    child.files.list.assert_awaited_once_with("/tmp/harbor-exec-fixture")
