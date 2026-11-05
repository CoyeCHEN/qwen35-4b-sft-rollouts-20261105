"""Generic installed-agent cancellation barrier for Harbor's agent phase."""

from __future__ import annotations

import asyncio
import json
import shlex
import sys
import tempfile
import time
import uuid
from typing import Any
from importlib.resources import files
from pathlib import Path

from harbor.agents.installed.base import BaseInstalledAgent
from harbor.trial.errors import AgentTimeoutError
from harbor.trial.process_supervisor import waiter_exit_code


class AgentCleanupError(RuntimeError):
    """Cleanup could not be proven; Harbor must not start the verifier."""

    agent_timeout: AgentTimeoutError | None = None


class AgentExecutionInterruptedError(RuntimeError):
    """The native waiter ended without actual command completion evidence."""


async def finish_barrier(task):
    """A second host cancellation must not interrupt the termination barrier."""
    while not task.done():
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError:
            continue
    return task.result()


class AgentEnvironmentScope:
    def __init__(self, environment, agent: BaseInstalledAgent | None = None):
        self.environment = environment
        self.lifecycle_interpreter = (
            getattr(agent, "lifecycle_interpreter", None) or "python3"
        )
        runtime_dir = getattr(environment, "agent_runtime_dir", None)
        self.control_cwd = str(runtime_dir) if runtime_dir is not None else "/"
        self.directory = f"{runtime_dir or '/tmp'}/harbor-lifecycle-{uuid.uuid4().hex}"
        self.script = self.directory + ".py"
        self.states = []
        self.pending = set()
        self.cleanup_task = None
        self.report: dict[str, Any] = {"scopes": []}

    def __getattr__(self, name):
        return getattr(self.environment, name)

    async def prepare(self):
        source = files("harbor.trial").joinpath("process_supervisor.py").read_bytes()
        with tempfile.TemporaryDirectory(prefix="harbor-lifecycle-") as directory:
            path = Path(directory) / "supervisor.py"
            path.write_bytes(source)
            await self.environment.upload_file(path, self.script)

    def command(self, action, state, *args):
        return shlex.join(
            [self.lifecycle_interpreter, self.script, action, state, *args]
        )

    async def exec(self, command, **kwargs):
        if self.cleanup_task is not None:
            raise AgentCleanupError(
                "Agent phase is cancelled; no new commands may start"
            )
        state = f"{self.directory}/{len(self.states)}"
        self.states.append((state, kwargs.get("user")))
        wrapped = (
            self.command("start", state, command) + " && " + self.command("wait", state)
        )
        task = asyncio.create_task(self.environment.exec(command=wrapped, **kwargs))
        self.pending.add(task)
        try:
            try:
                result = await asyncio.shield(task)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self.report["interrupted_execution"] = {
                    "reason": "waiter_transport_error",
                    "state": state,
                    "transport_error": repr(exc),
                }
                await self.cancel()
                raise AgentExecutionInterruptedError(
                    "Native waiter failed before command completion: " + state
                ) from exc
            try:
                completed = await self._control("completed", state, kwargs.get("user"))
            except AgentCleanupError as exc:
                self.report["interrupted_execution"] = {
                    "reason": "missing_command_completion_ack",
                    "state": state,
                    "waiter_return_code": result.return_code,
                    "completion_error": str(exc),
                }
                await self.cancel()
                raise AgentExecutionInterruptedError(
                    "Native waiter ended without durable command completion: " + state
                ) from exc
            self.report.setdefault("command_completions", []).append(completed)
            expected_return_code = waiter_exit_code(completed["return_code"]) & 0xFF
            if result.return_code != expected_return_code:
                self.report["interrupted_execution"] = {
                    "reason": "waiter_status_mismatch",
                    "state": state,
                    "waiter_return_code": result.return_code,
                    "command_return_code": completed["return_code"],
                    "expected_waiter_return_code": expected_return_code,
                    "command_completion_ack_verified": True,
                    "background_services_preserved": True,
                }
                raise AgentExecutionInterruptedError(
                    "Native waiter status does not match command completion: " + state
                )
            return result
        except asyncio.CancelledError:
            await self.cancel()
            raise
        finally:
            if task.done():
                self.pending.discard(task)

    async def _control(self, action, state, user):
        try:
            result = await self.environment.exec(
                command=self.command(action, state),
                user=user,
                timeout_sec=30,
                cwd=self.control_cwd,
            )
            if result.return_code != 0:
                raise AgentCleanupError(f"{action} failed for {state}: {result.stderr}")
            if action in ("cancel", "completed"):
                return {"state": state, **json.loads(result.stdout)}
        except Exception as exc:
            raise AgentCleanupError(
                f"Lifecycle {action} was not acknowledged: {exc}"
            ) from exc

    async def _cancel(self):
        self.report["cancel_requested_at"] = time.time()
        self.report["cancel_requested_monotonic"] = asyncio.get_running_loop().time()
        results = await asyncio.gather(
            *(self._control("cancel", state, user) for state, user in self.states),
            return_exceptions=True,
        )
        errors = [result for result in results if isinstance(result, BaseException)]
        self.report["scopes"] = [
            result for result in results if isinstance(result, dict)
        ]
        if errors:
            self.report["cleanup_confirmed"] = False
            raise AgentCleanupError(
                "Cannot confirm agent tree termination: " + str(errors)
            )
        if self.pending:
            try:
                await asyncio.wait_for(
                    asyncio.gather(*self.pending, return_exceptions=True),
                    timeout=10,
                )
            except TimeoutError as exc:
                raise AgentCleanupError(
                    "Remote execution waiters did not finish"
                ) from exc
        self.report.update(
            cleanup_confirmed=True,
            confirmed_at=time.time(),
            confirmed_monotonic=asyncio.get_running_loop().time(),
        )

    async def cancel(self):
        if self.cleanup_task is None:
            self.cleanup_task = asyncio.create_task(self._cancel())
        await finish_barrier(self.cleanup_task)

    async def release(self):
        for state, user in self.states:
            await self._control("release", state, user)


async def run_agent_with_lifecycle(
    *,
    agent,
    run,
    instruction,
    environment,
    context,
    timeout_sec,
):
    """Keep Harbor's official deadline and timeout exception/verification policy."""
    if not isinstance(agent, BaseInstalledAgent):
        deadline = asyncio.timeout(timeout_sec)
        try:
            async with deadline:
                return await run(
                    instruction=instruction, environment=environment, context=context
                )
        except TimeoutError as exc:
            if not deadline.expired():
                raise
            raise AgentTimeoutError(
                f"Agent execution timed out after {timeout_sec} seconds"
            ) from exc
    scope = AgentEnvironmentScope(environment, agent=agent)
    status = None
    started = asyncio.get_running_loop().time()
    deadline = asyncio.timeout(timeout_sec)
    scope.report.update(agent_started_monotonic=started, agent_budget_sec=timeout_sec)

    async def execute():
        await scope.prepare()
        return await run(instruction=instruction, environment=scope, context=context)

    try:
        async with deadline:
            await execute()
    except TimeoutError as exc:
        status = "timeout" if deadline.expired() else "error"
        try:
            await scope.cancel()
        except AgentCleanupError as cleanup:
            if deadline.expired():
                cleanup.agent_timeout = AgentTimeoutError(
                    f"Agent execution timed out after {timeout_sec} seconds"
                )
            raise
        if deadline.expired():
            raise AgentTimeoutError(
                f"Agent execution timed out after {timeout_sec} seconds"
            ) from exc
        raise
    except asyncio.CancelledError:
        status = "cancelled"
        await scope.cancel()
        raise
    except AgentExecutionInterruptedError:
        status = "interrupted"
        raise
    except AgentCleanupError as exc:
        status = "cleanup_failed"
        if deadline.expired():
            exc.agent_timeout = AgentTimeoutError(
                f"Agent execution timed out after {timeout_sec} seconds"
            )
        raise
    finally:
        primary_error = sys.exc_info()[1]
        scope.report["deadline_expired"] = deadline.expired()
        if isinstance(primary_error, AgentCleanupError):
            scope.report.update(
                cleanup_confirmed=False, cleanup_error=str(primary_error)
            )
        try:
            if scope.cleanup_task is None:
                try:
                    await scope.release()
                except asyncio.CancelledError:
                    if primary_error is None:
                        status = "cancelled"
                        await scope.cancel()
                        raise
                    scope.report["release_error"] = (
                        "release interrupted by cancellation"
                    )
                    primary_error.add_note(scope.report["release_error"])
                except BaseException as exc:
                    scope.report.update(
                        release_error=repr(exc), cleanup_confirmed=False
                    )
                    if primary_error is None:
                        status = "cleanup_failed"
                        raise
                    # Preserve the first failure while auditing release.
                    primary_error.add_note(
                        f"Agent lifecycle release also failed: {exc}"
                    )
                    status = status or "release_failed"
        finally:
            if status is not None or scope.report.get("release_error"):
                scope.report["agent_elapsed_sec"] = (
                    asyncio.get_running_loop().time() - started
                )
                metadata = {"agent_status": status, "lifecycle": scope.report}
                context.metadata = {**(context.metadata or {}), **metadata}
                agent.logs_dir.mkdir(parents=True, exist_ok=True)
                (agent.logs_dir / "lifecycle.json").write_text(
                    json.dumps(metadata, indent=2) + "\n"
                )
