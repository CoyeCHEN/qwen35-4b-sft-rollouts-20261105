"""A short provider preflight timeout is not the native verifier deadline."""

import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from harbor.models.task.config import TaskConfig
from harbor.environments.base import ExecResult
from harbor.trial.single_step import SingleStepTrial
from harbor_remote_docker.environment import RemoteDockerEnvironment
from harbor_remote_docker.transport import RemoteDockerError


def provider_with_probe_error(error: BaseException) -> RemoteDockerEnvironment:
    provider = object.__new__(RemoteDockerEnvironment)
    provider.endpoint = "ssh://fixture"
    provider.command_timeout = 120
    provider.task_env_config = SimpleNamespace(workdir="/workspace")
    provider._container = AsyncMock(return_value="owned-container")
    provider._run = AsyncMock(side_effect=error)
    return provider


async def probe(provider: RemoteDockerEnvironment, timeout: float | None = 3900):
    return await provider._compose_exec(
        "verifier-script-must-not-be-dispatched",
        service="main",
        cwd="/workspace",
        env=None,
        timeout_sec=timeout,
        user=None,
    )


@pytest.mark.parametrize("timeout", [None, 3900])
async def test_probe_timeout_is_provider_error_before_command_dispatch(timeout):
    original = TimeoutError("fixture preflight timeout")
    provider = provider_with_probe_error(original)
    with pytest.raises(RemoteDockerError, match="workdir probe timed out") as caught:
        await probe(provider, timeout)
    assert caught.value.__cause__ is original
    provider._run.assert_awaited_once()
    assert provider._run.await_args.kwargs["timeout"] == 30
    assert provider._run.await_args.args[0][-3:] == ["test", "-d", "/workspace"]


async def test_native_verifier_retains_provider_failure_instead_of_3900s_timeout():
    provider = provider_with_probe_error(TimeoutError("fixture preflight timeout"))

    async def verify(**kwargs):
        return await probe(provider, kwargs["timeout_sec"])

    trial = SimpleNamespace(
        config=SimpleNamespace(verifier=SimpleNamespace(disable=False)),
        task=SimpleNamespace(config=TaskConfig()),
        result=SimpleNamespace(verifier_result=None),
        _verifier_timeout_sec=3900,
        _emit=AsyncMock(),
        _now=lambda: datetime.now(timezone.utc),
        _run_shared_verifier=verify,
    )
    with pytest.raises(RemoteDockerError, match="workdir probe timed out"):
        await SingleStepTrial._run_verifier(trial)
    assert trial.result.verifier_result is None
    assert trial.result.verifier.finished_at is not None


async def test_parent_cancellation_is_preserved():
    provider = provider_with_probe_error(asyncio.CancelledError())
    with pytest.raises(asyncio.CancelledError):
        await probe(provider)


async def test_parent_deadline_still_expires_as_timeout():
    async def blocked(*args, **kwargs):
        await asyncio.sleep(10)

    provider = provider_with_probe_error(TimeoutError())
    provider._run = blocked
    with pytest.raises(TimeoutError):
        async with asyncio.timeout(0.01):
            await probe(provider)


@pytest.mark.parametrize("workdir", ["/workspace", "/app"])
@pytest.mark.parametrize(
    ("stdout", "stderr"),
    [
        (
            "",
            "command [ssh -o ConnectTimeout=30 -T -- fixture docker system dial-stdio] "
            "has exited with exit status 255, make sure the URL is valid, and Docker "
            "18.09 or later is installed on the remote host: stderr=\n",
        ),
        ("", "OCI runtime exec failed: unable to start container process"),
        ("unexpected test output", ""),
    ],
)
async def test_diagnostic_exit_one_is_not_a_missing_workdir(workdir, stdout, stderr):
    provider = provider_with_probe_error(TimeoutError())
    provider.task_env_config = SimpleNamespace(workdir=workdir)
    provider._task_workdir_unavailable = False
    provider._run = AsyncMock(
        side_effect=[
            ExecResult(stdout=stdout, stderr=stderr, return_code=1),
            ExecResult(stdout="dispatched", stderr="", return_code=0),
        ]
    )
    provider._platform = SimpleNamespace(
        exec_shell_args=lambda command: ["sh", "-c", command]
    )
    provider._output_callback = lambda: None
    provider.record = lambda *args, **kwargs: None

    with pytest.raises(RemoteDockerError, match="workdir probe"):
        await provider._compose_exec(
            "must-not-be-dispatched",
            service="main",
            cwd=workdir,
            env=None,
            timeout_sec=30,
            user=None,
        )
    provider._run.assert_awaited_once()
    assert not provider._task_workdir_unavailable
