import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from harbor.agents.base import BaseAgent
from harbor.agents.installed.base import ApiRateLimitError, NonZeroAgentExitCodeError
from harbor.agents.installed.open_harness import OpenHarnessAgent
from harbor.models.agent.context import AgentContext


@pytest.fixture(autouse=True)
def prepared_search_tools(monkeypatch):
    # These tests isolate the pre-existing wheel/interpreter contract. Real search
    # preparation and failure behavior are covered in test_search_dependencies.
    monkeypatch.setattr(OpenHarnessAgent, "_ensure_search_dependencies", AsyncMock())


def make_agent(tmp_path, **kwargs):
    wheel = tmp_path / "candidate.whl"
    digest = hashlib.sha256(
        wheel.read_bytes() if wheel.is_file() else b"fixture"
    ).hexdigest()
    return OpenHarnessAgent(
        logs_dir=tmp_path / "agent",
        model_name="deepseek/deepseek-flash",
        wheel_path=str(tmp_path / "candidate.whl"),
        wheel_sha256=digest,
        extra_env={"DEEPSEEK_API_KEY": "test-key"},
        **kwargs,
    )


def test_native_profile_preserves_harness_defaults(tmp_path):
    agent = make_agent(tmp_path)
    assert agent.harness_config() == {"model": "deepseek-flash"}
    assert agent.managed_process_lifecycle
    assert agent.runtime_requirements() == {"writable": True, "executable": True}
    assert type(agent).__mro__[1].__name__ == "BaseInstalledAgent"
    assert not BaseAgent.managed_process_lifecycle
    assert not agent.capabilities.resume


def test_adapter_requires_explicit_wheel_identity_and_rejects_retired_options(tmp_path):
    wheel = tmp_path / "candidate.whl"
    wheel.write_bytes(b"explicit frozen artifact")
    with pytest.raises(ValueError, match="explicit Harness wheel SHA256"):
        OpenHarnessAgent.preflight({"wheel_path": str(wheel)})
    OpenHarnessAgent.preflight(
        {
            "wheel_path": str(wheel),
            "wheel_sha256": hashlib.sha256(wheel.read_bytes()).hexdigest(),
        }
    )
    with pytest.raises(ValueError, match="profile"):
        make_agent(tmp_path, profile="legacy-eval-v1")
    with pytest.raises(ValueError, match="package_path"):
        make_agent(tmp_path, package_path=str(wheel))


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "interpreter,dependency,apt_package",
    [
        ("/usr/bin/python3", "python_venv", "python3-venv"),
        ("/usr/bin/python3.11", "python311", "python3.11-venv"),
        ("/usr/bin/python3.12", "python312", "python3.12-venv"),
        ("/usr/bin/python3.13", "python313", "python3.13-venv"),
    ],
)
async def test_install_repairs_selected_interpreter_ensurepip(
    tmp_path, interpreter, dependency, apt_package
):
    (tmp_path / "candidate.whl").write_bytes(b"fixture")
    agent = make_agent(tmp_path)
    agent.ensure_system_dependencies = AsyncMock()
    agent.exec_as_agent = AsyncMock()
    environment = SimpleNamespace(
        exec=AsyncMock(
            side_effect=[
                SimpleNamespace(return_code=0, stdout=interpreter + "\n"),
                SimpleNamespace(return_code=1),
                SimpleNamespace(return_code=0),
            ]
        ),
        upload_file=AsyncMock(),
    )

    await agent.install(environment)

    assert agent.ensure_system_dependencies.await_args_list[-1].args == (
        environment,
        (dependency,),
    )
    assert apt_package in agent.SYSTEM_PACKAGES[dependency].packages["apt-get"]
    assert interpreter in agent.exec_as_agent.await_args.kwargs["command"]


@pytest.mark.asyncio
async def test_install_stops_if_ensurepip_repair_does_not_work(tmp_path):
    (tmp_path / "candidate.whl").write_bytes(b"fixture")
    agent = make_agent(tmp_path)
    agent.ensure_system_dependencies = AsyncMock()
    environment = SimpleNamespace(
        exec=AsyncMock(
            side_effect=[
                SimpleNamespace(return_code=0, stdout="/usr/bin/python3.12\n"),
                SimpleNamespace(return_code=1),
                SimpleNamespace(return_code=1),
            ]
        ),
        upload_file=AsyncMock(),
    )

    with pytest.raises(RuntimeError, match="python3.12 is missing ensurepip"):
        await agent.install(environment)

    environment.upload_file.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("return_code,stdout", [(1, ""), (0, "")])
async def test_old_system_python_uses_private_managed_cli_runtime(
    tmp_path, return_code, stdout
):
    (tmp_path / "candidate.whl").write_bytes(b"fixture")
    uv = tmp_path / "uv"
    uv.write_bytes(b"bootstrap artifact")
    digest = hashlib.sha256(uv.read_bytes()).hexdigest()
    agent = make_agent(tmp_path, bootstrap_uv_path=str(uv), bootstrap_uv_sha256=digest)
    agent.ensure_system_dependencies = AsyncMock()
    agent.exec_as_agent = AsyncMock()
    environment = SimpleNamespace(
        exec=AsyncMock(
            return_value=SimpleNamespace(return_code=return_code, stdout=stdout)
        ),
        upload_file=AsyncMock(),
    )

    await agent.install(environment)

    agent.ensure_system_dependencies.assert_awaited_once_with(
        environment, ("coreutils",)
    )
    command = agent.exec_as_agent.await_args.kwargs["command"]
    assert "--managed-python --python 3.12.12" in command
    assert "apt-get" not in command
    assert agent.exec_as_agent.await_args.kwargs["env"][
        "UV_PYTHON_INSTALL_DIR"
    ].startswith("/tmp/")
    artifact = json.loads((agent.logs_dir / "artifact.json").read_text())
    assert artifact["bootstrap"]["uv_sha256"] == digest
    assert artifact["bootstrap"]["system_python_unchanged"]
    assert agent.harness_config() == {"model": "deepseek-flash"}
    assert agent.lifecycle_interpreter == "/tmp/harbor-open-harness-venv/bin/python"


@pytest.mark.asyncio
async def test_install_uses_provider_runtime_directory(tmp_path):
    (tmp_path / "candidate.whl").write_bytes(b"fixture")
    agent = make_agent(tmp_path)
    agent.ensure_system_dependencies = AsyncMock()
    agent.exec_as_agent = AsyncMock()
    environment = SimpleNamespace(
        agent_runtime_dir="/harbor/agent-runtime",
        exec=AsyncMock(
            side_effect=[
                SimpleNamespace(return_code=0, stdout="/usr/bin/python3.12\n"),
                SimpleNamespace(return_code=0),
            ]
        ),
        upload_file=AsyncMock(),
    )

    await agent.install(environment)

    command = agent.exec_as_agent.await_args.kwargs["command"]
    assert "/harbor/agent-runtime/harbor-open-harness-venv" in command
    assert agent.lifecycle_interpreter == (
        "/harbor/agent-runtime/harbor-open-harness-venv/bin/python"
    )
    assert agent.get_version_command().startswith(
        "/harbor/agent-runtime/harbor-open-harness-venv/bin/open-harness"
    )
    assert environment.upload_file.await_args.args[1].startswith(
        "/harbor/agent-runtime/"
    )


@pytest.mark.asyncio
async def test_install_reports_unsupported_noexec_runtime(tmp_path):
    (tmp_path / "candidate.whl").write_bytes(b"fixture")
    agent = make_agent(tmp_path)
    agent.ensure_system_dependencies = AsyncMock()
    agent.exec_as_agent = AsyncMock(
        side_effect=NonZeroAgentExitCodeError("exec probe returned 126")
    )
    environment = SimpleNamespace(
        agent_runtime_dir="/tmp/harbor-agent-runtime",
        exec=AsyncMock(
            side_effect=[
                SimpleNamespace(return_code=0, stdout="/usr/bin/python3.12"),
                SimpleNamespace(return_code=0),
            ]
        ),
        upload_file=AsyncMock(),
    )

    with pytest.raises(RuntimeError, match="writable executable agent runtime"):
        await agent.install(environment)

    environment.upload_file.assert_not_awaited()


@pytest.mark.asyncio
async def test_completion_polling_uses_agent_runtime_cwd(tmp_path):
    agent = make_agent(tmp_path)
    agent._runtime_dir = "/harbor/agent-runtime"
    environment = SimpleNamespace(
        exec=AsyncMock(
            side_effect=[SimpleNamespace(return_code=1), SimpleNamespace(return_code=0)]
        ),
        download_file=AsyncMock(
            side_effect=lambda remote, local: local.write_text(
                '{"identity":"identity","exit_code":0}'
            )
        ),
    )

    await agent._completion(
        environment, "/logs/agent/open-harness.complete.json", "identity"
    )

    assert all(
        call.kwargs["cwd"] == "/harbor/agent-runtime"
        for call in environment.exec.await_args_list
    )


def test_open_harness_does_not_classify_tool_text_as_provider_rate_limit(tmp_path):
    agent = make_agent(tmp_path)
    result = SimpleNamespace(
        return_code=1,
        stderr="",
        stdout="\n".join(
            [
                json.dumps(
                    {
                        "type": "message_update",
                        "text": "The website returned HTTP 429 rate limit; retrying tool call.",
                    }
                ),
                json.dumps({"type": "result", "status": "error", "exitCode": 1}),
            ]
        ),
    )

    error = agent._classify_exec_error("open-harness", result)

    assert type(error) is NonZeroAgentExitCodeError
    assert not isinstance(error, ApiRateLimitError)


def test_open_harness_classifies_structured_error_message(tmp_path):
    agent = make_agent(tmp_path)
    result = SimpleNamespace(
        return_code=1,
        stderr="",
        stdout=json.dumps(
            {
                "type": "error",
                "message": "DeepSeek rate limit exceeded",
            }
        ),
    )

    error = agent._classify_exec_error("open-harness", result)

    assert type(error) is ApiRateLimitError


def test_open_harness_does_not_scan_tool_text_without_terminal_event(tmp_path):
    agent = make_agent(tmp_path)
    result = SimpleNamespace(
        return_code=1,
        stderr="",
        stdout=json.dumps(
            {
                "type": "message_update",
                "text": "The website returned HTTP 429; retrying.",
            }
        ),
    )

    error = agent._classify_exec_error("open-harness", result)

    assert type(error) is NonZeroAgentExitCodeError
    assert not isinstance(error, ApiRateLimitError)


@pytest.mark.asyncio
async def test_managed_runtime_rejects_changed_bootstrap_before_upload(tmp_path):
    (tmp_path / "candidate.whl").write_bytes(b"fixture")
    uv = tmp_path / "uv"
    uv.write_bytes(b"unexpected bytes")
    agent = make_agent(
        tmp_path, bootstrap_uv_path=str(uv), bootstrap_uv_sha256="0" * 64
    )
    agent.ensure_system_dependencies = AsyncMock()
    environment = SimpleNamespace(
        exec=AsyncMock(return_value=SimpleNamespace(return_code=1)),
        upload_file=AsyncMock(),
    )

    with pytest.raises(ValueError, match="Bootstrap uv SHA256"):
        await agent.install(environment)

    environment.upload_file.assert_not_awaited()


@pytest.mark.asyncio
async def test_completion_downloads_remote_marker_without_shared_mount(tmp_path):
    agent = make_agent(tmp_path)
    environment = SimpleNamespace(
        exec=AsyncMock(return_value=SimpleNamespace(return_code=0))
    )

    async def download(remote, target):
        assert remote == "/logs/agent/completion.json"
        Path(target).write_text(json.dumps({"identity": "current", "exit_code": 0}))

    environment.download_file = AsyncMock(side_effect=download)
    await agent._completion(environment, "/logs/agent/completion.json", "current")
    environment.download_file.assert_awaited_once()
    assert not (agent.logs_dir / "completion.json").exists()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload,error",
    [
        ({"identity": "stale", "exit_code": 0}, RuntimeError),
        ({"identity": "current", "exit_code": 7}, NonZeroAgentExitCodeError),
        ({"identity": "current", "exit_code": "0"}, RuntimeError),
    ],
)
async def test_completion_rejects_wrong_identity_or_failure(tmp_path, payload, error):
    agent = make_agent(tmp_path)
    environment = SimpleNamespace(
        exec=AsyncMock(return_value=SimpleNamespace(return_code=0))
    )

    async def download(remote, target):
        Path(target).write_text(json.dumps(payload))

    environment.download_file = download
    with pytest.raises(error):
        await agent._completion(environment, "/marker", "current")


@pytest.mark.asyncio
async def test_run_preserves_instruction_and_original_streams(tmp_path):
    agent = make_agent(tmp_path)
    instruction = "printf '%s' '$HOME'; echo `literal`\nsecond line\n"
    uploaded = {}

    async def upload(local, remote):
        uploaded[remote] = Path(local).read_text()

    environment = SimpleNamespace(upload_file=AsyncMock(side_effect=upload))
    agent.exec_as_agent = AsyncMock(return_value=SimpleNamespace(stdout="/task\n"))
    agent._upload_config_text = AsyncMock()
    agent._completion = AsyncMock()
    await agent.run(instruction, environment, AgentContext())
    command = agent.exec_as_agent.await_args.kwargs["command"]
    assert list(uploaded.values()) == [instruction]
    assert "--prompt-file" in command
    assert "--no-session" not in command and "grep" not in command
    assert "--literal" not in command
    assert "stderr.log" in command and "stdout.jsonl" in command
    assert "test-key" not in command
    assert agent.exec_as_agent.await_args.kwargs["cwd"] == "/task"


@pytest.mark.asyncio
async def test_run_adds_optional_recorder_argument(tmp_path):
    agent = make_agent(tmp_path, record_trajectory=True)
    environment = SimpleNamespace(upload_file=AsyncMock())
    agent.exec_as_agent = AsyncMock(return_value=SimpleNamespace(stdout="/task\n"))
    agent._upload_config_text = AsyncMock()
    agent._completion = AsyncMock()

    await agent.run("task", environment, AgentContext())

    command = agent.exec_as_agent.await_args.kwargs["command"]
    assert "--trajectory-dir /logs/agent/openharness-rollout" in command


@pytest.mark.asyncio
async def test_run_omits_recorder_argument_by_default(tmp_path):
    agent = make_agent(tmp_path)
    environment = SimpleNamespace(upload_file=AsyncMock())
    agent.exec_as_agent = AsyncMock(return_value=SimpleNamespace(stdout="/task\n"))
    agent._upload_config_text = AsyncMock()
    agent._completion = AsyncMock()

    await agent.run("task", environment, AgentContext())

    command = agent.exec_as_agent.await_args.kwargs["command"]
    assert "--trajectory-dir" not in command


@pytest.mark.parametrize("as_file", [False, True])
def test_native_config_passes_through_and_explicit_options_override(tmp_path, as_file):
    native = {
        "model": "deepseek-flash",
        "thinkingLevel": "max",
        "requestOptions": {"temperature": 1.0, "maxTokens": 123},
        "compaction": {"reserveTokens": 81920},
        "backgroundJobs": {"keepProcesses": True, "handoffTimeout": 600},
        "recording": {"enabled": True},
        "sessionDir": "/logs/agent/sessions",
        "finish": {"enabled": False},
        "toolSearch": "off",
    }
    source = native
    if as_file:
        source = tmp_path / "native.json"
        source.write_text(json.dumps(native))
    agent = make_agent(tmp_path, config=source, max_tokens=65536)
    expected = {**native, "requestOptions": {"temperature": 1.0, "maxTokens": 65536}}
    assert agent.capabilities.native_config
    assert agent.harness_config() == expected
    assert native["requestOptions"]["maxTokens"] == 123


def test_native_config_model_mismatch_fails(tmp_path):
    with pytest.raises(ValueError, match="model must match"):
        make_agent(tmp_path, config={"model": "another-model"}).harness_config()


@pytest.mark.parametrize("fails", [False, True])
async def test_install_environment_is_scoped_and_restored_on_failure(
    tmp_path, monkeypatch, fails
):
    from contextvars import ContextVar
    from types import MethodType
    from harbor.environments.base import BaseEnvironment

    monkeypatch.setenv("TEST_INSTALL_WHEELS", "/readonly/agent-wheels")
    agent = make_agent(
        tmp_path,
        install_env={"PIP_NO_INDEX": "1", "PIP_FIND_LINKS": "${TEST_INSTALL_WHEELS}"},
    )
    environment = SimpleNamespace(
        _persistent_env={"TASK_OPTION": "retained"},
        _exec_env_overlays=ContextVar("install-scope", default=()),
    )
    environment.scoped_exec_env = MethodType(
        BaseEnvironment.scoped_exec_env, environment
    )

    async def install(env):
        assert BaseEnvironment._merge_env(env, None) == {
            "TASK_OPTION": "retained",
            "PIP_NO_INDEX": "1",
            "PIP_FIND_LINKS": "/readonly/agent-wheels",
        }
        if fails:
            raise RuntimeError("failed isolated installation")

    agent._install_cli = AsyncMock(side_effect=install)
    if fails:
        with pytest.raises(RuntimeError, match="failed isolated installation"):
            await agent.install(environment)
    else:
        await agent.install(environment)
    assert BaseEnvironment._merge_env(environment, None) == {"TASK_OPTION": "retained"}


def test_install_env_credentials_must_be_references(tmp_path):
    with pytest.raises(ValueError, match="inherited"):
        make_agent(tmp_path, install_env={"PRIVATE_TOKEN": "literal-fixture-value"})
    with pytest.raises(ValueError, match="inherited"):
        make_agent(
            tmp_path,
            install_env={
                "PIP_INDEX_URL": "https://user:password@example.invalid/simple"
            },
        )
    make_agent(tmp_path, install_env={"PRIVATE_TOKEN": "${PRIVATE_TOKEN}"})
