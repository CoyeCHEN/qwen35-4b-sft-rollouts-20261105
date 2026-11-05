"""A terminal Trial must wait for one Provider cleanup acknowledgement."""

import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from harbor.models.trial.config import (
    AgentConfig,
    EnvironmentConfig,
    TaskConfig,
    TrialConfig,
)
from harbor.models.verifier.result import VerifierResult
from harbor.trial.hooks import TrialEvent
from harbor.trial.trial import Trial
from tests.unit.test_trial_cleanup import (
    HangingAgent,
    SlowStopEnvironment,
    _create_task_dir,
)


class ControlledStopEnvironment(SlowStopEnvironment):
    """No backend: only the test may acknowledge stop()."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.allow_stop = asyncio.Event()
        self.stop_failure: Exception | None = None

    async def stop(self, delete: bool) -> None:
        self.stop_call_count += 1
        self.stop_started.set()
        await self.allow_stop.wait()
        self.stop_delete_value = delete
        if self.stop_failure is not None:
            raise self.stop_failure
        self.stop_completed.set()


async def make_trial(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, hanging: bool = False
):
    tmp_path.mkdir()
    task_dir = _create_task_dir(tmp_path)
    agent_name = "HangingAgent" if hanging else "QuickAgent"
    trial = await Trial.create(
        TrialConfig(
            task=TaskConfig(path=task_dir),
            trial_name="cleanup-ack",
            trials_dir=tmp_path / "trials",
            agent=AgentConfig(
                import_path=f"tests.unit.test_trial_cleanup:{agent_name}"
            ),
            environment=EnvironmentConfig(
                import_path=(
                    "tests.unit.test_trial_cleanup_ack:ControlledStopEnvironment"
                ),
                delete=True,
            ),
        )
    )
    monkeypatch.setattr(
        trial,
        "_run_shared_verifier",
        AsyncMock(return_value=VerifierResult(rewards={"reward": 0.0}, return_code=0)),
    )
    environment = trial.agent_environment
    assert isinstance(environment, ControlledStopEnvironment)
    return trial, environment


@pytest.mark.parametrize("hanging", [False, True])
async def test_repeated_cancel_waits_for_ack_before_result_and_end(
    tmp_path, monkeypatch, hanging
):
    trial, environment = await make_trial(
        tmp_path / "trial", monkeypatch, hanging=hanging
    )
    ended = []

    async def on_end(event):
        ended.append(environment.stop_completed.is_set())

    trial.add_hook(TrialEvent.END, on_end)
    task = asyncio.create_task(trial.run())
    if hanging:
        assert isinstance(trial.agent, HangingAgent)
        await trial.agent.running.wait()
        task.cancel()
    await environment.stop_started.wait()
    try:
        for _ in range(2):
            task.cancel()
            await asyncio.sleep(0)
            assert not task.done()
            assert not trial._is_agent_environment_stopped
            assert not trial.paths.result_path.exists()
            assert not ended
        assert environment.stop_call_count == 1
    finally:
        environment.allow_stop.set()

    with pytest.raises(asyncio.CancelledError):
        await task
    assert trial._is_agent_environment_stopped
    assert ended == [True]
    result = json.loads(trial.paths.result_path.read_text())
    assert result["exception_info"]["exception_type"] == "CancelledError"
    assert result["finished_at"]
    if not hanging:
        assert result["failure_phase"] == "cleanup"
        assert result["verifier_result"]["rewards"] == {"reward": 0.0}
    assert environment.stop_call_count == 1


async def test_cancel_during_finalize_still_persists_terminal_result(
    tmp_path, monkeypatch
):
    trial, environment = await make_trial(tmp_path / "trial", monkeypatch)
    trial._init_result()
    ended = []

    async def on_end(event):
        ended.append(environment.stop_completed.is_set())

    trial.add_hook(TrialEvent.END, on_end)
    task = asyncio.create_task(trial._finalize())
    await environment.stop_started.wait()
    try:
        task.cancel()
        await asyncio.sleep(0)
        assert not task.done() and not ended
        assert not trial.paths.result_path.exists()
    finally:
        environment.allow_stop.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    result = json.loads(trial.paths.result_path.read_text())
    assert result["exception_info"]["exception_type"] == "CancelledError"
    assert result["failure_phase"] == "cleanup"
    assert result["finished_at"] and ended == [True]


async def test_failed_cleanup_is_not_ack_and_does_not_cancel_peer(
    tmp_path, monkeypatch
):
    failed, failed_environment = await make_trial(tmp_path / "failed", monkeypatch)
    healthy, healthy_environment = await make_trial(tmp_path / "healthy", monkeypatch)
    failed_environment.stop_failure = RuntimeError("Provider cleanup unconfirmed")
    failed_environment.allow_stop.set()
    healthy_environment.allow_stop.set()

    async with asyncio.TaskGroup() as group:
        bad = group.create_task(failed.run())
        good = group.create_task(healthy.run())
    result = bad.result()
    assert result.verifier_result.rewards == {"reward": 0.0}
    assert result.exception_info.exception_message == "Provider cleanup unconfirmed"
    assert result.failure_phase == "cleanup"
    assert len(result.infrastructure_errors) == 1
    assert result.infrastructure_errors[0].phase == "cleanup"
    assert not failed._is_agent_environment_stopped
    assert failed._environment_cleanup_task is not None
    assert failed._environment_cleanup_task.done()
    assert failed_environment.stop_call_count == 1
    # Re-entering finalization retrieves the same failure, not another stop().
    await failed._stop_agent_environment()
    assert failed_environment.stop_call_count == 1
    assert len(result.infrastructure_errors) == 1
    assert not failed._is_agent_environment_stopped
    assert good.result().exception_info is None
    assert healthy._is_agent_environment_stopped


async def test_concurrent_cleanup_callers_share_one_stop(tmp_path, monkeypatch):
    trial, environment = await make_trial(tmp_path / "trial", monkeypatch)
    first = asyncio.create_task(trial._stop_agent_environment())
    await environment.stop_started.wait()
    second = asyncio.create_task(trial._stop_agent_environment())
    await asyncio.sleep(0)
    try:
        assert environment.stop_call_count == 1
        assert not trial._is_agent_environment_stopped
    finally:
        environment.allow_stop.set()
    await first
    await second
    assert trial._is_agent_environment_stopped
    assert environment.stop_call_count == 1


async def test_provider_cancellation_is_not_a_cleanup_ack(tmp_path, monkeypatch):
    trial, environment = await make_trial(tmp_path / "trial", monkeypatch)

    async def cancelled_stop(delete: bool) -> None:
        environment.stop_call_count += 1
        raise asyncio.CancelledError

    monkeypatch.setattr(environment, "stop", cancelled_stop)
    with pytest.raises(asyncio.CancelledError):
        await trial.run()
    result = json.loads(trial.paths.result_path.read_text())
    assert not trial._is_agent_environment_stopped
    assert environment.stop_call_count == 1
    assert result["finished_at"]
    assert result["verifier_result"]["rewards"] == {"reward": 0.0}
    assert result["infrastructure_errors"][0]["phase"] == "cleanup"
    assert (
        "before acknowledgement"
        in result["infrastructure_errors"][0]["exception_info"]["exception_message"]
    )


async def test_finalize_failure_is_recorded_before_end(tmp_path, monkeypatch):
    trial, environment = await make_trial(tmp_path / "trial", monkeypatch)
    environment.allow_stop.set()
    monkeypatch.setattr(
        trial,
        "_close_bridge",
        AsyncMock(side_effect=RuntimeError("bridge finalization failed")),
    )
    seen = []

    async def on_end(event):
        seen.extend(error.phase for error in event.result.infrastructure_errors)

    trial.add_hook(TrialEvent.END, on_end)
    result = await trial.run()
    assert result.verifier_result.rewards == {"reward": 0.0}
    assert result.exception_info.exception_message == "bridge finalization failed"
    assert len(result.infrastructure_errors) == 1
    assert seen == ["finalize"]
    assert trial._is_agent_environment_stopped
    assert environment.stop_call_count == 1
