"""Exercise the native Trial chain with fake agents and environments."""

import asyncio
from unittest.mock import AsyncMock

import pytest

from harbor.models.trial.config import (
    AgentConfig,
    EnvironmentConfig,
    TaskConfig,
    TrialConfig,
)
from harbor.models.verifier.result import VerifierResult
from harbor.trial.agent_lifecycle import AgentCleanupError, AgentEnvironmentScope
from harbor.trial.trial import Trial
from tests.unit.rsi.lifecycle_fixtures import FakeAgent
from tests.unit.test_trial_cleanup import _create_task_dir


async def make_trial(tmp_path, *, managed=False, name="trial"):
    tmp_path.mkdir(parents=True, exist_ok=True)
    task = _create_task_dir(tmp_path)
    trial = await Trial.create(
        TrialConfig(
            task=TaskConfig(path=task),
            trial_name=name,
            trials_dir=tmp_path / "trials",
            agent=AgentConfig(import_path="tests.unit.test_trial_cleanup:QuickAgent"),
            environment=EnvironmentConfig(
                import_path="tests.unit.test_trial_cleanup:MountedEnvironment"
            ),
        )
    )
    if managed:
        trial.agent = FakeAgent(logs_dir=trial.paths.agent_dir)
        trial.agent.setup = AsyncMock()
    trial.agent.managed_process_lifecycle = managed
    trial._agent_timeout_sec = 0.02
    trial._run_shared_verifier = AsyncMock(
        return_value=VerifierResult(rewards={"reward": 1.0})
    )
    return trial


@pytest.mark.parametrize("managed", [False, True])
async def test_inner_transport_timeout_is_not_native_agent_deadline(tmp_path, managed):
    trial = await make_trial(tmp_path, managed=managed)
    trial.agent.run = AsyncMock(side_effect=TimeoutError("transport budget expired"))
    result = await trial.run()
    assert result.exception_info.exception_type == "TimeoutError"
    assert result.exception_info.exception_message == "transport budget expired"
    trial._run_shared_verifier.assert_not_awaited()


@pytest.mark.parametrize("managed", [False, True])
@pytest.mark.parametrize("reward", [0.0, 0.6111111111111112, 1.0])
async def test_deadline_preserves_native_reward_and_exception(
    tmp_path, managed, reward
):
    trial = await make_trial(tmp_path, managed=managed)

    async def hang(**kwargs):
        await asyncio.sleep(10)

    trial.agent.run = hang
    trial._run_shared_verifier.return_value = VerifierResult(rewards={"reward": reward})
    result = await trial.run()
    assert result.exception_info.exception_type == "AgentTimeoutError"
    assert result.verifier_result.rewards == {"reward": reward}
    assert not result.infrastructure_errors
    trial._run_shared_verifier.assert_awaited_once()
    if managed:
        assert result.agent_result.metadata["lifecycle"]["cleanup_confirmed"]


async def test_one_trial_timeout_does_not_cancel_peer(tmp_path):
    timed = await make_trial(tmp_path / "timed", managed=True)
    healthy = await make_trial(tmp_path / "healthy")

    async def hang(**kwargs):
        await asyncio.sleep(10)

    timed.agent.run = hang
    async with asyncio.TaskGroup() as group:
        first = group.create_task(timed.run())
        second = group.create_task(healthy.run())
    assert first.result().exception_info.exception_type == "AgentTimeoutError"
    assert second.result().exception_info is None
    assert second.result().verifier_result.rewards == {"reward": 1.0}


async def test_deadline_and_cleanup_failure_are_both_recorded(tmp_path, monkeypatch):
    trial = await make_trial(tmp_path, managed=True)

    async def hang(**kwargs):
        await asyncio.sleep(10)

    async def fail(self):
        raise AgentCleanupError("termination acknowledgement lost")

    trial.agent.run = hang
    monkeypatch.setattr(AgentEnvironmentScope, "_cancel", fail)
    result = await trial.run()
    assert result.exception_info.exception_type == "AgentTimeoutError"
    assert any(
        e.exception_info.exception_type == "AgentCleanupError"
        for e in result.infrastructure_errors
    )
    assert result.verifier_result is None
    trial._run_shared_verifier.assert_not_awaited()


async def test_verifier_failure_after_deadline_keeps_timeout_and_missing_reward(
    tmp_path,
):
    trial = await make_trial(tmp_path)

    async def hang(**kwargs):
        await asyncio.sleep(10)

    trial.agent.run = hang
    trial._run_shared_verifier.side_effect = RuntimeError("verifier failed")
    result = await trial.run()
    assert result.exception_info.exception_type == "AgentTimeoutError"
    assert result.verifier_result is None
    assert result.secondary_errors[0].phase == "verification"
    assert (
        result.secondary_errors[0].exception_info.exception_message == "verifier failed"
    )


async def test_cleanup_failure_does_not_replace_primary_agent_failure(tmp_path):
    trial = await make_trial(tmp_path)
    trial.agent.run = AsyncMock(side_effect=RuntimeError("agent failed"))
    trial.agent_environment.stop = AsyncMock(side_effect=RuntimeError("cleanup failed"))
    result = await trial.run()
    assert result.exception_info.exception_message == "agent failed"
    assert any(
        e.exception_info.exception_message == "cleanup failed"
        for e in result.infrastructure_errors
    )
