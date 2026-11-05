"""Offline regressions for interrupted installed-agent output collection."""

import asyncio
import json
import shutil
import sys
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from harbor.extensions.rsi.trajectory import build_atif_trajectory
from harbor.models.agent.context import AgentContext
from harbor.trial.trial import Trial
from tests.unit.rsi.test_contract import make_agent
from tests.unit.rsi.lifecycle_fixtures import LocalEnvironment


def test_lifecycle_metadata_does_not_skip_post_run_collection():
    context = AgentContext(metadata={"agent_status": "timeout", "lifecycle": {}})
    hook = Mock(side_effect=lambda ctx: setattr(ctx, "n_input_tokens", 17))
    trial = SimpleNamespace(
        user_agent=None, agent=SimpleNamespace(populate_context_post_run=hook)
    )
    Trial._populate_agent_context(trial, context)
    hook.assert_called_once_with(context)
    assert context.n_input_tokens == 17
    assert context.metadata["agent_status"] == "timeout"


def test_existing_usage_is_not_overwritten():
    hook = Mock()
    trial = SimpleNamespace(
        user_agent=None, agent=SimpleNamespace(populate_context_post_run=hook)
    )
    Trial._populate_agent_context(
        trial, AgentContext(n_input_tokens=0, metadata={"status": "done"})
    )
    hook.assert_not_called()


def test_retry_messages_after_snapshot_are_retained_once():
    first = {
        "role": "assistant",
        "content": [{"type": "text", "text": "first"}],
        "usage": {"input": 7, "output": 2},
    }
    second = {
        "role": "assistant",
        "content": [{"type": "text", "text": "after retry"}],
        "usage": {"input": 11, "output": 3},
    }
    lines = [
        json.dumps(e)
        for e in [
            {"type": "message_end", "message": first},
            {"type": "agent_end", "messages": [first]},
            {"type": "auto_retry_end", "success": True},
            {"type": "message_end", "message": second},
            {"type": "message_start", "message": {"role": "assistant"}},
        ]
    ]
    data = build_atif_trajectory(
        lines, instruction="task", model_name="fake", agent_version="test"
    )
    assert [s["message"] for s in data["steps"] if s["source"] == "agent"] == [
        "first",
        "after retry",
    ]
    assert data["final_metrics"]["total_prompt_tokens"] == 18


@pytest.mark.parametrize("exit_code", [0, 7])
@pytest.mark.skipif(
    sys.platform != "linux", reason="LocalEnvironment executes a Linux shell fixture"
)
async def test_cli_logs_are_collected_as_files_without_replaying_stream(
    tmp_path, exit_code
):
    """Run the actual adapter shell; slow exec output must not delay completion."""
    from harbor.agents.installed.base import NonZeroAgentExitCodeError

    class FileEnvironment(LocalEnvironment):
        async def download_file(self, source_path, target_path):
            shutil.copyfile(source_path, target_path)

        async def exec(self, command, **kwargs):
            result = await super().exec(command, **kwargs)
            # Simulate backpressure on the SSH exec stdout channel. File
            # downloads happen later, outside the native agent deadline.
            if len(result.stdout) > 4096:
                await asyncio.sleep(1)
            return result

    agent = make_agent(tmp_path)
    logs = tmp_path / "remote-logs"
    logs.mkdir()
    cli = tmp_path / "fixture-cli"
    cli.write_text(
        f"#!/bin/sh\nhead -c 65536 /dev/zero | tr '\\0' x\necho error >&2\nexit {exit_code}\n"
    )
    cli.chmod(0o755)
    agent._remote_cli = str(cli)
    agent._runtime_dir = str(tmp_path)
    agent.environment_logs_dir = logs
    env = FileEnvironment(tmp_path)
    if exit_code:
        with pytest.raises(NonZeroAgentExitCodeError):
            await asyncio.wait_for(agent.run("task", env, AgentContext()), 0.5)
    else:
        await asyncio.wait_for(agent.run("task", env, AgentContext()), 0.5)
    assert (logs / "open-harness.stdout.jsonl").stat().st_size == 65536
    assert (logs / "open-harness.stderr.log").read_text() == "error\n"
    assert (
        json.loads((logs / "open-harness.complete.json").read_text())["exit_code"]
        == exit_code
    )
