import asyncio
import os
import signal
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

if sys.platform != "linux":
    pytest.skip(
        "Sandbox process supervisor requires Linux /proc and pidfd",
        allow_module_level=True,
    )

from tests.unit.rsi.lifecycle_fixtures import FakeAgent, LocalEnvironment

from harbor.models.agent.context import AgentContext
from harbor.trial import process_supervisor as supervisor
from harbor.trial.agent_lifecycle import (
    AgentCleanupError,
    AgentEnvironmentScope,
    run_agent_with_lifecycle,
)


def alive(pid):
    path = Path(f"/proc/{pid}/stat")
    return path.exists() and path.read_text().split(") ")[1][0] != "Z"


def test_timeout_stops_setsid_double_fork_before_verifier(tmp_path):
    # The orphaned writer starts a new session and loses its original parent.
    code = """
import os, pathlib, time
if os.fork() == 0:
    os.setsid()
    if os.fork() != 0:
        os._exit(0)
    pathlib.Path('writer.pid').write_text(str(os.getpid()))
    time.sleep(2)
    pathlib.Path('late-marker').touch()
    os._exit(0)
os.wait()
time.sleep(120)
"""
    import shlex

    agent = FakeAgent(logs_dir=tmp_path / "logs")
    environment = LocalEnvironment(tmp_path)
    context = AgentContext()

    async def check():
        with pytest.raises(TimeoutError):
            await run_agent_with_lifecycle(
                agent=agent,
                run=agent.run,
                instruction=shlex.join(["python3", "-c", code]),
                environment=environment,
                context=context,
                timeout_sec=0.8,
            )
        assert not alive(int((tmp_path / "writer.pid").read_text()))
        assert context.metadata["agent_status"] == "timeout"
        assert context.metadata["lifecycle"]["cleanup_confirmed"] is True
        await asyncio.sleep(1.5)
        assert not (tmp_path / "late-marker").exists()

    asyncio.run(check())


def test_normal_exit_keeps_intentional_service(tmp_path):
    agent = FakeAgent(logs_dir=tmp_path / "logs")
    environment = LocalEnvironment(tmp_path)
    context = AgentContext()
    asyncio.run(
        run_agent_with_lifecycle(
            agent=agent,
            run=agent.run,
            instruction="sleep 120 >/dev/null 2>&1 & echo $! > service.pid",
            environment=environment,
            context=context,
            timeout_sec=5,
        )
    )
    pid = int((tmp_path / "service.pid").read_text())
    try:
        assert alive(pid)
        assert context.is_empty()
    finally:
        os.kill(pid, signal.SIGKILL)
    release_calls = [
        call for call in environment.calls if " release " in call["command"]
    ]
    assert release_calls
    assert all(call["cwd"] == str(tmp_path) for call in release_calls)


@pytest.mark.parametrize("runtime", [True, False])
def test_release_survives_deleted_task_workdir(tmp_path, runtime):
    workdir = tmp_path / "work"
    workdir.mkdir()
    environment = LocalEnvironment(workdir)
    environment.agent_runtime_dir = tmp_path if runtime else None
    agent = FakeAgent(logs_dir=tmp_path / "logs")

    async def run(**kwargs):
        await agent.exec_as_agent(kwargs["environment"], "true")
        workdir.rmdir()

    asyncio.run(
        run_agent_with_lifecycle(
            agent=agent,
            run=run,
            instruction="",
            environment=environment,
            context=AgentContext(),
            timeout_sec=5,
        )
    )
    assert not workdir.exists()
    assert environment.calls[-1]["cwd"] == (str(tmp_path) if runtime else "/")


def test_scope_uses_installed_agent_lifecycle_interpreter(tmp_path):
    agent = FakeAgent(logs_dir=tmp_path / "logs")
    agent.lifecycle_interpreter = "/tmp/private-python/bin/python"
    scope = AgentEnvironmentScope(LocalEnvironment(tmp_path), agent=agent)

    command = scope.command("start", "/tmp/state", "true")

    assert command.startswith("/tmp/private-python/bin/python ")


def test_release_failure_does_not_mask_agent_failure(tmp_path):
    class ReleaseFailingEnvironment(LocalEnvironment):
        async def exec(self, command, **kwargs):
            if " release " in command:
                return SimpleNamespace(
                    stdout="", stderr="release unavailable", return_code=1
                )
            return await super().exec(command, **kwargs)

    agent = FakeAgent(logs_dir=tmp_path / "logs")
    context = AgentContext()

    async def run(instruction, environment, context):
        await agent.exec_as_agent(environment, "true")
        raise RuntimeError("agent failure")

    async def check():
        with pytest.raises(RuntimeError, match="agent failure") as caught:
            await run_agent_with_lifecycle(
                agent=agent,
                run=run,
                instruction="",
                environment=ReleaseFailingEnvironment(tmp_path),
                context=context,
                timeout_sec=5,
            )
        assert any("release" in note for note in caught.value.__notes__)
        assert context.metadata["agent_status"] == "release_failed"
        assert "release_error" in context.metadata["lifecycle"]

    asyncio.run(check())


def test_timeout_also_stops_services_from_completed_commands(tmp_path):
    agent = FakeAgent(logs_dir=tmp_path / "logs")
    environment = LocalEnvironment(tmp_path)
    context = AgentContext()

    async def run(instruction, environment, context):
        await agent.exec_as_agent(environment, "sleep 120 & echo $! > service.pid")
        await agent.exec_as_agent(
            environment, "sleep 120 & echo $! > current.pid; wait"
        )

    async def check():
        with pytest.raises(TimeoutError):
            await run_agent_with_lifecycle(
                agent=agent,
                run=run,
                instruction="",
                environment=environment,
                context=context,
                timeout_sec=0.8,
            )
        assert not alive(int((tmp_path / "service.pid").read_text()))
        assert not alive(int((tmp_path / "current.pid").read_text()))
        assert len(context.metadata["lifecycle"]["scopes"]) == 2

    asyncio.run(check())


def test_cancellation_does_not_masquerade_as_timeout(tmp_path):
    agent = FakeAgent(logs_dir=tmp_path / "logs")
    environment = LocalEnvironment(tmp_path)
    context = AgentContext()

    async def check():
        task = asyncio.create_task(
            run_agent_with_lifecycle(
                agent=agent,
                run=agent.run,
                instruction="sleep 120 & echo $! > sleeper.pid; wait",
                environment=environment,
                context=context,
                timeout_sec=120,
            )
        )
        while not (tmp_path / "sleeper.pid").exists():
            await asyncio.sleep(0.02)
        task.cancel()
        await asyncio.sleep(0.01)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert not alive(int((tmp_path / "sleeper.pid").read_text()))
        assert context.metadata["agent_status"] == "cancelled"

    asyncio.run(check())


def test_cleanup_failure_is_not_timeout_and_blocks_verifier(tmp_path, monkeypatch):
    async def fail(self):
        raise AgentCleanupError("injected lost cleanup acknowledgement")

    monkeypatch.setattr(AgentEnvironmentScope, "_cancel", fail)
    agent = FakeAgent(logs_dir=tmp_path / "logs")
    context = AgentContext()

    async def hang(**kwargs):
        await asyncio.sleep(120)

    async def check():
        with pytest.raises(AgentCleanupError):
            await run_agent_with_lifecycle(
                agent=agent,
                run=hang,
                instruction="",
                environment=LocalEnvironment(tmp_path),
                context=context,
                timeout_sec=0.01,
            )
            pytest.fail("verifier must not be reached after cleanup failure")

    asyncio.run(check())


def test_cancel_before_remote_dispatch_cannot_start_late_work(tmp_path):
    environment = LocalEnvironment(tmp_path)
    scope = AgentEnvironmentScope(environment)

    async def check():
        await scope.prepare()
        state = scope.directory + "/late"
        scope.states.append((state, None))
        await scope.cancel()
        result = await environment.exec(
            command=scope.command("start", state, "touch forbidden-marker"),
        )
        assert result.return_code == 0
        await asyncio.sleep(0.1)
        assert not (tmp_path / "forbidden-marker").exists()

    asyncio.run(check())


def test_harbor_does_not_verify_on_cleanup_error():
    from types import SimpleNamespace
    from unittest.mock import AsyncMock, Mock

    from harbor.trial.single_step import SingleStepTrial

    trial = SimpleNamespace(
        _run_agent_phase=AsyncMock(side_effect=AgentCleanupError("not confirmed")),
        _record_exception=Mock(),
        _sync_agent_output=AsyncMock(),
        result=object(),
        _agent_timeout_sec=5,
        _load_trajectory=None,
        task=SimpleNamespace(
            instruction="",
            config=SimpleNamespace(
                agent=SimpleNamespace(user=None),
            ),
        ),
    )
    with pytest.raises(AgentCleanupError):
        asyncio.run(SingleStepTrial._run_agent(trial))
    trial._record_exception.assert_not_called()
    trial._sync_agent_output.assert_awaited_once()


def test_empty_proc_scan_requires_kernel_no_children(monkeypatch):
    from unittest.mock import Mock

    # A concurrently forked descendant may be absent from a /proc listing.
    reap = Mock(side_effect=[False, False, True])
    monkeypatch.setattr(supervisor, "reap", reap)
    monkeypatch.setattr(supervisor, "processes", dict)
    monkeypatch.setattr(supervisor.time, "sleep", lambda seconds: None)
    report = supervisor.stop_tree(None)
    assert reap.call_count == 3
    assert report["kernel_no_children"] is True


def test_fork_during_cleanup_is_frozen_and_killed(monkeypatch):
    from unittest.mock import Mock

    root = os.getpid()
    parent = {"pid": 12345, "ppid": root, "state": "T", "start_ticks": 1}
    late = {"pid": 12346, "ppid": root, "state": "R", "start_ticks": 2}
    stopped = {**late, "state": "T"}
    monkeypatch.setattr(
        supervisor, "reap", Mock(side_effect=[False, False, False, True])
    )
    monkeypatch.setattr(
        supervisor,
        "processes",
        Mock(
            side_effect=[
                {parent["pid"]: parent},
                {late["pid"]: late},
                {late["pid"]: stopped},
                {},
            ]
        ),
    )
    send = Mock()
    monkeypatch.setattr(supervisor, "signal_identity", send)
    monkeypatch.setattr(supervisor.time, "sleep", lambda seconds: None)
    report = supervisor.stop_tree(None)
    send.assert_any_call(late, signal.SIGSTOP)
    send.assert_any_call(stopped, signal.SIGKILL)
    assert report["kernel_no_children"] is True


def test_concurrent_process_scopes_do_not_cancel_each_other(tmp_path):
    async def check():
        first, second = tmp_path / "first", tmp_path / "second"
        first.mkdir()
        second.mkdir()
        envs = [LocalEnvironment(first), LocalEnvironment(second)]
        agents = [FakeAgent(logs_dir=p / "logs") for p in (first, second)]
        contexts = [AgentContext(), AgentContext()]

        async def timeout_run():
            with pytest.raises(TimeoutError):
                await run_agent_with_lifecycle(
                    agent=agents[0],
                    run=agents[0].run,
                    instruction="sleep 60 & echo $! > child.pid; wait",
                    environment=envs[0],
                    context=contexts[0],
                    timeout_sec=0.3,
                )

        async def healthy_run():
            await run_agent_with_lifecycle(
                agent=agents[1],
                run=agents[1].run,
                instruction="sleep 60 >/dev/null 2>&1 & echo $! > child.pid; sleep 0.5",
                environment=envs[1],
                context=contexts[1],
                timeout_sec=5,
            )

        try:
            async with asyncio.TaskGroup() as group:
                group.create_task(timeout_run())
                group.create_task(healthy_run())
            assert not alive(int((first / "child.pid").read_text()))
            assert alive(int((second / "child.pid").read_text()))
        finally:
            path = second / "child.pid"
            if path.exists():
                pid = int(path.read_text())
                row = supervisor.processes().get(pid)
                if row:
                    supervisor.signal_identity(row, signal.SIGKILL)

    asyncio.run(check())


def test_clock_correction_does_not_change_native_deadline(tmp_path, monkeypatch):
    import itertools

    wall = itertools.count(1000.0, -100.0)
    monkeypatch.setattr("harbor.trial.agent_lifecycle.time.time", lambda: next(wall))
    agent = FakeAgent(logs_dir=tmp_path / "logs")
    context = AgentContext()

    async def hang(**kwargs):
        await asyncio.sleep(10)

    async def check():
        with pytest.raises(TimeoutError):
            await run_agent_with_lifecycle(
                agent=agent,
                run=hang,
                instruction="",
                environment=LocalEnvironment(tmp_path),
                context=context,
                timeout_sec=0.02,
            )

    asyncio.run(check())
    report = context.metadata["lifecycle"]
    assert report["confirmed_at"] < report["cancel_requested_at"]
    assert report["confirmed_monotonic"] >= report["cancel_requested_monotonic"]
    assert 0.02 <= report["agent_elapsed_sec"] < 1
    assert report["deadline_expired"] is True


def test_normal_exit_release_failure_still_writes_lifecycle(tmp_path, monkeypatch):
    async def fail(self):
        raise AgentCleanupError("release acknowledgement lost")

    async def done(**kwargs):
        pass

    monkeypatch.setattr(AgentEnvironmentScope, "release", fail)
    agent = FakeAgent(logs_dir=tmp_path / "logs")
    context = AgentContext()
    with pytest.raises(AgentCleanupError):
        asyncio.run(
            run_agent_with_lifecycle(
                agent=agent,
                run=done,
                instruction="",
                environment=LocalEnvironment(tmp_path),
                context=context,
                timeout_sec=1,
            )
        )
    assert (agent.logs_dir / "lifecycle.json").exists()
    assert context.metadata["lifecycle"]["cleanup_confirmed"] is False
    assert (
        "release acknowledgement lost" in context.metadata["lifecycle"]["release_error"]
    )
