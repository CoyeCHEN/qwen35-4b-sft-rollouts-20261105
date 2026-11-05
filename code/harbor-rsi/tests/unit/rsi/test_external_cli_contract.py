"""Opt-in native Job contract against a separately installed OpenHarness wheel.

Set HARBOR_TEST_OPENHARNESS_WHEEL and HARBOR_TEST_OPENHARNESS_CLI. No model
service is contacted: the model descriptor points at the loopback fixture.
"""

import hashlib
import json
import os
import shlex
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import override

import pytest

from harbor.agents.installed.open_harness import OpenHarnessAgent
from harbor.job import Job
from harbor.models.trial.result import TrialResult
from tests.unit.rsi.test_native_job import (
    native_config,
    native_inputs,  # noqa: F401 - register the existing wheel/task fixture
)

pytestmark = pytest.mark.skipif(
    sys.platform != "linux"
    or not all(
        os.environ.get(key)
        for key in ("HARBOR_TEST_OPENHARNESS_WHEEL", "HARBOR_TEST_OPENHARNESS_CLI")
    ),
    reason="Linux and explicit installed OpenHarness wheel/CLI required",
)


@pytest.fixture
def installed_cli():
    wheel = os.environ.get("HARBOR_TEST_OPENHARNESS_WHEEL")
    cli = os.environ.get("HARBOR_TEST_OPENHARNESS_CLI")
    assert wheel and cli
    assert Path(wheel).is_file() and Path(cli).is_file()
    subprocess.run(
        [
            str(Path(cli).parent / "python"),
            "-c",
            """
import importlib.metadata, sys, zipfile
distribution = importlib.metadata.distribution('open-harness-ai')
with zipfile.ZipFile(sys.argv[1]) as archive:
    for member in archive.namelist():
        if member.endswith('.py'):
            assert distribution.locate_file(member).read_bytes() == archive.read(member), member
""",
            wheel,
        ],
        check=True,
        capture_output=True,
        timeout=10,
    )
    return Path(wheel), Path(cli)


@pytest.mark.parametrize(
    "provider", ["MountedFixtureEnvironment", "CustomFixtureEnvironment"]
)
@pytest.mark.parametrize("mode", ["normal", "model_error", "timeout_after_write"])
async def test_installed_wheel_native_job(
    tmp_path, request, installed_cli, provider, mode, monkeypatch
):
    wheel, cli = installed_cli
    task, _ = request.getfixturevalue("native_inputs")
    (task / "environment/nested/input.bin").write_text("wheel contract ok\n")
    if mode == "timeout_after_write":
        (task / "task.toml").write_text(
            "[agent]\ntimeout_sec = 2\n[verifier]\ntimeout_sec = 5\n[environment]\n"
        )
    calls = []
    release = threading.Event()

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            calls.append(
                json.loads(self.rfile.read(int(self.headers["content-length"])))
            )
            if mode == "model_error":
                self.send_error(400, "offline fixture error")
                return
            if mode == "timeout_after_write" and len(calls) == 2:
                release.wait(15)
                return
            delta = (
                {
                    "tool_calls": [
                        {
                            "index": 0,
                            "id": "write-1",
                            "function": {
                                "name": "write",
                                "arguments": json.dumps(
                                    {
                                        "path": "output.bin",
                                        "content": "wheel contract ok\n",
                                    }
                                ),
                            },
                        }
                    ]
                }
                if len(calls) == 1
                else {"content": "done"}
            )
            delta["reasoning_content"] = f"offline-thinking-{len(calls)}"
            chunks = [
                {
                    "id": "offline",
                    "model": "fixture",
                    "choices": [{"index": 0, "delta": delta, "finish_reason": None}],
                },
                {
                    "choices": [
                        {
                            "index": 0,
                            "delta": {},
                            "finish_reason": "tool_calls"
                            if len(calls) == 1
                            else "stop",
                        }
                    ],
                    "usage": {
                        "prompt_tokens": 20,
                        "completion_tokens": 5,
                        "total_tokens": 25,
                    },
                },
            ]
            body = (
                "".join("data: " + json.dumps(x) + "\n\n" for x in chunks)
                + "data: [DONE]\n\n"
            ).encode()
            self.send_response(200)
            self.send_header("content-type", "text/event-stream")
            self.send_header("content-length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        @override
        def log_message(self, format: str, *args) -> None:
            pass

    async def use_installed_wheel(agent, environment):
        agent.preflight(agent.options.model_dump())
        agent._configure_runtime_paths(environment)
        # Installation was performed in an isolated venv before this opt-in
        # test. Launch that pinned CLI through the existing provider fixture.
        launcher = tmp_path / "cli-launcher"
        launcher.write_text(f'#!/bin/sh\nexec {shlex.quote(str(cli))} "$@"\n')
        launcher.chmod(0o755)
        await environment.upload_file(launcher, agent._remote_cli)
        await environment.exec(f"chmod 755 {shlex.quote(agent._remote_cli)}")
        agent.lifecycle_interpreter = str(cli.parent / "python")
        agent._write_install_artifact(hashlib.sha256(wheel.read_bytes()).hexdigest())

    monkeypatch.setattr(OpenHarnessAgent, "install", use_installed_wheel)
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        config = native_config(tmp_path, (task, wheel), provider)
        config.agents[0].kwargs.update(
            model_descriptor={
                "id": "fixture",
                "api": "openai-completions",
                "provider": "deepseek",
                "baseUrl": f"http://127.0.0.1:{server.server_port}",
                "reasoning": True,
                "thinkingLevelMap": {"low": "low", "high": "high", "max": "max"},
                "input": ["text"],
                "contextWindow": 100000,
                "maxTokens": 65536,
                "cost": {"input": 0, "output": 0, "cacheRead": 0, "cacheWrite": 0},
            },
            config={
                "thinkingLevel": "max",
                "persist": True,
                "sessionDir": str(tmp_path / "sessions"),
                "recording": {"enabled": True},
                "requestOptions": {"temperature": 1.0, "maxTokens": 123},
                "resources": {
                    "autoDiscover": False,
                    "skillsEnabled": False,
                    "templatesEnabled": False,
                },
                "enableAgentTool": False,
                "enableSkillTool": False,
                "toolSearch": "off",
                "compaction": {
                    "enabled": True,
                    "reserveTokens": 81920,
                    "keepRecentTokens": 20000,
                    "maxTurns": 0,
                },
                "backgroundJobs": {
                    "enabled": True,
                    "maxConcurrent": 2,
                    "keepProcesses": True,
                    "handoffTimeout": 600,
                },
                "finish": {"enabled": False},
                "timeBudget": {"seconds": 0},
                "tokenObservation": {"enabled": False},
            },
            record_trajectory=True,
            max_tokens=65536,
        )
        config.agents[0].kwargs["model_descriptor"]["contextWindow"] = 262144
        job = await Job.create(config)
        result = await job.run()
        trial = result.trial_results[0]
        assert trial.verifier_result is not None
        assert trial.verifier_result.rewards == {"reward": float(mode != "model_error")}
        assert trial.verifier_result.return_code == 0
        assert not trial.infrastructure_errors
        assert calls[0]["max_tokens"] == 65536
        assert calls[0]["thinking"] == {"type": "enabled"}
        assert calls[0]["reasoning_effort"] == "max"
        assert calls[0]["temperature"] == 1.0
        assert "top_p" not in calls[0]
        assert (
            calls[0]["messages"][-1]["content"] == (task / "instruction.md").read_text()
        )
        directory = job.job_dir / trial.trial_name
        effective = json.loads((directory / "agent/effective-config.json").read_text())
        assert effective["model"]["contextWindow"] == 262144
        assert effective["compaction"]["reserveTokens"] == 81920
        assert effective["backgroundJobs"]["handoffTimeout"] == 600
        assert effective["finish"] == {"enabled": False}
        trace = directory / "agent/openharness-rollout"
        assert (trace / "events.jsonl").is_file()
        assert list((tmp_path / "sessions").rglob("*.jsonl"))
        validation = subprocess.run(
            [str(cli.parent / "open-harness-traces"), "validate", str(trace)],
            capture_output=True,
            text=True,
            timeout=15,
        )
        if mode == "normal":
            assert validation.returncode == 0, validation.stdout + validation.stderr
            assert json.loads(validation.stdout)["complete"]
            assistant = next(
                m for m in calls[1]["messages"] if m["role"] == "assistant"
            )
            assert assistant["reasoning_content"] == "offline-thinking-1"
            assert calls[1]["messages"][-1]["role"] == "tool"
            assert calls[1]["messages"][-1]["tool_call_id"] == "write-1"
            assert sum(m["role"] == "user" for m in calls[1]["messages"]) == 1
        elif mode == "timeout_after_write":
            assert validation.returncode != 0
        assert (directory / "agent/open-harness.stdout.jsonl").is_file()
        assert (directory / "agent/open-harness.stderr.log").is_file()
        assert (directory / "agent/trajectory.json").is_file()
        assert (
            TrialResult.model_validate_json((directory / "result.json").read_text())
            == trial
        )
        if mode == "timeout_after_write":
            assert trial.exception_info is not None
            assert trial.agent_result is not None
            assert trial.agent_result.metadata is not None
            assert trial.exception_info.exception_type == "AgentTimeoutError"
            assert trial.agent_result.metadata["lifecycle"]["cleanup_confirmed"]
        else:
            marker = json.loads(
                (directory / "agent/open-harness.complete.json").read_text()
            )
            assert marker["exit_code"] == int(mode == "model_error")
            if mode == "model_error":
                assert trial.exception_info is not None
                assert (
                    trial.exception_info.exception_type == "NonZeroAgentExitCodeError"
                )
            else:
                assert trial.exception_info is None
    finally:
        release.set()
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
