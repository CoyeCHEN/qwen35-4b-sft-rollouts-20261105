from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from harbor.environments.base import ExecResult

from harbor_remote_docker.compose import load_compose_source, validate_compose
from harbor_remote_docker.environment import RemoteDockerEnvironment
from harbor_remote_docker.transport import (
    RemoteDockerError,
    file_hash,
    pack,
    ssh_target,
    unpack,
)


def test_compose_reset_is_safe_and_does_not_change_global_yaml_loader():
    import yaml

    text = "services:\n  main:\n    build: !reset null\n    image: sha256:abc\n"
    assert load_compose_source(text)["services"]["main"]["build"] is None
    with pytest.raises(yaml.constructor.ConstructorError):
        yaml.safe_load(text)
    with pytest.raises(yaml.constructor.ConstructorError):
        load_compose_source("value: !!python/object/apply:os.system ['false']")
    assert load_compose_source("include: unsafe.yaml")["include"] == "unsafe.yaml"


def test_ssh_endpoint_never_accepts_credentials_or_shell_text():
    assert ssh_target("ssh://alice@docker-host:2222")[-1] == "docker-host"
    with pytest.raises(ValueError):
        ssh_target("ssh://alice:password@docker-host")
    with pytest.raises(ValueError):
        ssh_target("ssh://docker-host/var/run/docker.sock")
    with pytest.raises(ValueError):
        ssh_target("ssh://docker-host;rm -rf /")


def test_compose_rejects_host_sensitive_features(tmp_path: Path):
    source = tmp_path / "input.txt"
    source.write_text("input")
    base = {
        "name": "harbor-test",
        "services": {
            "main": {
                "build": {"context": str(tmp_path)},
                "volumes": [
                    {
                        "type": "bind",
                        "source": str(source),
                        "target": "/input",
                        "read_only": True,
                    }
                ],
            }
        },
    }
    assert list(validate_compose(base, "harbor-test", [tmp_path])) == [source.resolve()]
    for field, value in (
        ("privileged", True),
        ("network_mode", "host"),
        ("devices", ["/dev/null:/dev/null"]),
    ):
        document = json.loads(json.dumps(base))
        document["services"]["main"][field] = value
        with pytest.raises(ValueError):
            validate_compose(document, "harbor-test", [tmp_path])


def test_nested_binary_archive_round_trip_and_hash(tmp_path: Path):
    source = tmp_path / "source"
    (source / "nested").mkdir(parents=True)
    payload = bytes(range(256)) * 4096
    (source / "nested" / "input.bin").write_bytes(payload)
    archive = tmp_path / "payload.tar"
    restored = tmp_path / "restored"
    pack(source, archive)
    unpack(archive, restored)
    assert (restored / "input" / "nested" / "input.bin").read_bytes() == payload
    assert file_hash(archive) == hashlib.sha256(archive.read_bytes()).hexdigest()


@pytest.mark.parametrize("option", ["no-new-privileges", "no-new-privileges:true"])
def test_compose_preserves_restrictive_no_new_privileges(tmp_path, option):
    document = {
        "name": "harbor-test",
        "services": {
            "main": {"security_opt": [option], "read_only": True, "cap_drop": ["ALL"]}
        },
    }
    assert validate_compose(document, "harbor-test", [tmp_path]) == {}
    assert document["services"]["main"]["security_opt"] == [option]


@pytest.mark.parametrize(
    "option", ["no-new-privileges:false", "seccomp:unconfined", "apparmor:unconfined"]
)
def test_compose_rejects_other_security_overrides(tmp_path, option):
    document = {"name": "harbor-test", "services": {"main": {"security_opt": [option]}}}
    with pytest.raises(ValueError, match="restrictive no-new-privileges"):
        validate_compose(document, "harbor-test", [tmp_path])


def test_provider_configuration_is_external_and_capabilities_are_explicit(
    tmp_path: Path,
):
    environment = tmp_path / "environment"
    environment.mkdir()
    (environment / "Dockerfile").write_text("FROM alpine:3.20\n")
    task_paths = __import__("harbor.models.trial.paths", fromlist=["TrialPaths"])
    config = __import__(
        "harbor.models.task.config", fromlist=["EnvironmentConfig"]
    ).EnvironmentConfig()
    trial_paths = task_paths.TrialPaths(tmp_path / "trial")
    trial_paths.mkdir()
    provider = RemoteDockerEnvironment(
        environment_dir=environment,
        environment_name="fixture",
        session_id="fixture-session",
        trial_paths=trial_paths,
        task_env_config=config,
        endpoint="ssh://docker-host",
        staging_root="/var/tmp/harbor-rsi",
        agent_runtime_volume=True,
    )
    assert provider.capabilities.mounted is False
    assert provider.capabilities.docker_compose is True
    assert "docker-host" in provider._ssh or provider._ssh == []
    provider.configure_agent_runtime(writable=True, executable=True)
    assert str(provider.agent_runtime_dir) == "/harbor/agent-runtime"
    assert provider.agent_runtime_requirements == {
        "writable": True,
        "executable": True,
    }
    assert provider._agent_runtime_volume_key == "agent-runtime"
    with pytest.raises(ValueError):
        RemoteDockerEnvironment(
            environment_dir=environment,
            environment_name="fixture",
            session_id="fixture-session",
            trial_paths=trial_paths,
            task_env_config=config,
            endpoint="ssh://docker-host",
            staging_root="/home/../unsafe",
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("storage", ["default", "existing", "volume"])
async def test_agent_runtime_volume_is_identity_scoped_and_added_before_start(
    tmp_path: Path,
    storage: str,
):
    environment = tmp_path / "environment"
    environment.mkdir()
    (environment / "Dockerfile").write_text("FROM alpine:3.20\n")
    from harbor.models.task.config import EnvironmentConfig
    from harbor.models.trial.paths import TrialPaths

    trial_paths = TrialPaths(tmp_path / "trial")
    trial_paths.mkdir()
    provider = RemoteDockerEnvironment(
        environment_dir=environment,
        environment_name="fixture",
        session_id="fixture-session",
        trial_paths=trial_paths,
        task_env_config=EnvironmentConfig(),
        endpoint="ssh://docker-host",
        staging_root="/var/tmp/harbor-rsi",
        agent_runtime_volume=storage == "volume",
        **(
            {"agent_runtime_dir": "/logs/agent/runtime"}
            if storage == "existing"
            else {}
        ),
    )
    provider.configure_agent_runtime(writable=True, executable=True)
    provider._compose = AsyncMock(
        return_value=ExecResult(
            stdout=json.dumps(
                {
                    "name": provider.project,
                    "services": {"main": {"image": "alpine:3.20"}},
                    "volumes": {},
                }
            ),
            stderr="",
            return_code=0,
        )
    )
    provider._resources = AsyncMock(
        return_value={"container": [], "network": [], "volume": []}
    )
    provider._shell = AsyncMock(
        return_value=ExecResult(stdout="", stderr="", return_code=0)
    )
    provider.evidence.parent.mkdir(parents=True, exist_ok=True)
    await provider._prepare_remote()

    document = json.loads(provider._remote_compose.read_text())
    if storage != "volume":
        assert not document["services"]["main"].get("volumes")
        assert not document["volumes"]
        assert str(provider.agent_runtime_dir) == (
            "/logs/agent/runtime"
            if storage == "existing"
            else "/tmp/harbor-agent-runtime"
        )
        return
    assert document["services"]["main"]["volumes"] == [
        {
            "type": "volume",
            "source": "agent-runtime",
            "target": "/harbor/agent-runtime",
        }
    ]
    assert (
        document["volumes"]["agent-runtime"]["labels"][
            "io.harbor.remote-docker.identity"
        ]
        == provider.identity
    )


@pytest.mark.asyncio
async def test_verifier_test_volume_is_opt_in_and_identity_scoped(tmp_path: Path):
    environment = tmp_path / "environment"
    environment.mkdir()
    (environment / "Dockerfile").write_text("FROM alpine:3.20\n")
    from harbor.models.task.config import EnvironmentConfig
    from harbor.models.trial.paths import TrialPaths

    trial_paths = TrialPaths(tmp_path / "trial")
    trial_paths.mkdir()
    provider = RemoteDockerEnvironment(
        environment_dir=environment,
        environment_name="fixture",
        session_id="fixture-session",
        trial_paths=trial_paths,
        task_env_config=EnvironmentConfig(),
        endpoint="ssh://docker-host",
        staging_root="/var/tmp/harbor-rsi",
        verifier_test_volume=True,
    )
    provider._compose = AsyncMock(
        return_value=ExecResult(
            stdout=json.dumps(
                {
                    "name": provider.project,
                    "services": {"main": {"image": "alpine:3.20"}},
                    "volumes": {},
                }
            ),
            stderr="",
            return_code=0,
        )
    )
    provider._resources = AsyncMock(
        return_value={"container": [], "network": [], "volume": []}
    )
    provider._shell = AsyncMock(
        return_value=ExecResult(stdout="", stderr="", return_code=0)
    )
    provider.evidence.parent.mkdir(parents=True, exist_ok=True)
    await provider._prepare_remote()

    document = json.loads(provider._remote_compose.read_text())
    assert {
        "type": "volume",
        "source": "verifier-tests",
        "target": "/tests",
    } in document["services"]["main"]["volumes"]
    assert (
        document["volumes"]["verifier-tests"]["labels"][
            "io.harbor.remote-docker.identity"
        ]
        == provider.identity
    )


@pytest.mark.asyncio
async def test_transport_failure_is_not_replayed(monkeypatch, tmp_path: Path):
    calls: list[list[str]] = []
    records: list[tuple[str, dict]] = []

    async def fake_run(argv, **kwargs):
        calls.append(argv)
        return ExecResult(stdout="", stderr="connection reset by peer", return_code=255)

    import harbor_remote_docker.environment as module

    monkeypatch.setattr(module, "run", fake_run)
    provider = object.__new__(RemoteDockerEnvironment)
    provider.identity = "identity"
    provider.project = "project"
    provider.session_id = "session"
    provider.workspace = Path("/var/tmp/harbor-rsi/project")
    provider.command_timeout = 1
    provider._client_env = lambda: {}
    provider.record = lambda action, **details: records.append((action, details))
    with pytest.raises(RemoteDockerError, match="transport failed"):
        await provider._run(["ssh", "docker-host", "true"])
    assert calls == [["ssh", "docker-host", "true"]]
    assert records[-1][0] == "transport_lost"
    assert records[-1][1]["stderr_tail"] == "connection reset by peer"


@pytest.mark.asyncio
async def test_failed_remote_operation_keeps_stdout_and_stderr_evidence(monkeypatch):
    import harbor_remote_docker.environment as module

    async def fake_run(argv, **kwargs):
        return ExecResult(
            stdout="compose stdout", stderr="compose stderr", return_code=1
        )

    monkeypatch.setattr(module, "run", fake_run)
    records: list[tuple[str, dict]] = []
    provider = object.__new__(RemoteDockerEnvironment)
    provider.identity = "identity"
    provider.project = "project"
    provider.session_id = "session"
    provider.command_timeout = 1
    provider._client_env = lambda: {}
    provider.record = lambda action, **details: records.append((action, details))

    with pytest.raises(RemoteDockerError, match="compose stderr"):
        await provider._run(["docker", "compose", "up"])

    assert records == [
        (
            "operation_failed",
            {
                "exit_code": 1,
                "operation": "docker compose up",
                "stderr_tail": "compose stderr",
                "stdout_tail": "compose stdout",
                "resources_may_remain": True,
            },
        )
    ]


@pytest.mark.asyncio
async def test_upload_uses_tar_fallback_for_read_only_rootfs(tmp_path: Path):
    archive = tmp_path / "transfer.tar"
    archive.write_bytes(b"archive")
    provider = object.__new__(RemoteDockerEnvironment)
    provider.remote_socket_path = "/var/run/docker.sock"
    provider.transfer_timeout = 60
    provider._marker_guard = lambda: "guard; "
    provider.record = lambda *args, **kwargs: None
    provider._shell = AsyncMock(
        side_effect=[
            RemoteDockerError(
                "Remote operation failed (exit 1); stderr: "
                "Error response from daemon: container rootfs is marked read-only"
            ),
            ExecResult(stdout="", stderr="", return_code=0),
        ]
    )

    await provider._copy_archive_to_container(
        archive, "container-id", "/tmp", "'/remote/archive.tar'"
    )

    assert provider._shell.await_count == 2
    fallback = provider._shell.await_args_list[1]
    assert "docker --host unix:///var/run/docker.sock exec -i" in fallback.args[0]
    assert "tar -xpf - -C /tmp" in fallback.args[0]
    assert "-w /" in fallback.args[0]
    assert fallback.kwargs["source"] == archive


@pytest.mark.asyncio
async def test_upload_uses_declared_read_only_tar_path_without_cp(tmp_path: Path):
    archive = tmp_path / "transfer.tar"
    archive.write_bytes(b"archive")
    provider = object.__new__(RemoteDockerEnvironment)
    provider.remote_socket_path = "/var/run/docker.sock"
    provider.transfer_timeout = 60
    provider._read_only_services = {"main"}
    provider._marker_guard = lambda: "guard; "
    provider._shell = AsyncMock()

    await provider._copy_archive_to_container(
        archive, "container-id", "/tmp", "'/remote/archive.tar'"
    )

    provider._shell.assert_awaited_once()
    command = provider._shell.await_args.args[0]
    assert "docker --host unix:///var/run/docker.sock exec -i -u root" in command
    assert "-w /" in command
    assert "docker --host unix:///var/run/docker.sock cp" not in command


@pytest.mark.asyncio
async def test_download_uses_tar_stream_for_read_only_rootfs(tmp_path: Path):
    provider = object.__new__(RemoteDockerEnvironment)
    provider.remote_socket_path = "/var/run/docker.sock"
    provider.transfer_timeout = 60
    provider._read_only_services = {"main"}
    provider._marker_guard = lambda: "guard; "
    provider._shell = AsyncMock()

    await provider._copy_archive_from_container(
        "container-id", "/tmp/probe.bin", "'/remote/archive.tar'"
    )

    provider._shell.assert_awaited_once()
    command = provider._shell.await_args.args[0]
    assert (
        "docker --host unix:///var/run/docker.sock exec -u root -w / container-id"
        in command
    )
    assert "tar -cpf - -C /tmp probe.bin" in command
    assert "> '/remote/archive.tar'" in command


@pytest.mark.asyncio
@pytest.mark.parametrize("directory", [False, True])
async def test_upload_survives_deleted_container_default_workdir(
    tmp_path: Path, directory: bool
):
    source = tmp_path / "source"
    if directory:
        source.mkdir()
        (source / "payload.bin").write_bytes(bytes(range(256)))
    else:
        source.write_bytes(bytes(range(256)))
    provider = object.__new__(RemoteDockerEnvironment)
    provider.workspace = tmp_path / "workspace"
    provider._container = AsyncMock(return_value="container-id")
    provider._send_archive = AsyncMock()
    provider._copy_archive_to_container = AsyncMock()
    provider._shell = AsyncMock()
    provider._marker_guard = lambda: "guard; "
    provider.record = lambda *args, **kwargs: None

    def execute(command, *, service, user, cwd=None):
        # Docker cannot start a process in the deleted image WORKDIR.
        if cwd is None:
            return ExecResult(
                stdout="OCI runtime exec failed: chdir to cwd failed",
                stderr="",
                return_code=127,
            )
        return ExecResult(
            stdout="", stderr="", return_code=1 if command.startswith("test -d") else 0
        )

    provider.service_exec = AsyncMock(side_effect=execute)
    await provider._transfer(
        source, "/logs/agent/output", upload=True, directory=directory
    )
    provider._send_archive.assert_awaited_once()
    provider._copy_archive_to_container.assert_awaited_once()
    assert all(
        call.kwargs["cwd"] == "/" for call in provider.service_exec.await_args_list
    )


@pytest.mark.asyncio
async def test_prepare_remote_preserves_shell_variables_before_compose_render(
    monkeypatch, tmp_path: Path
):
    compose_path = tmp_path / "docker-compose.yaml"
    compose_path.write_text("services:\n  main:\n    image: alpine:3.20\n")
    project = "harbor-test"
    document = {
        "name": project,
        "services": {
            "main": {
                "image": "alpine:3.20",
                "entrypoint": ["sh", "-c", 'code=$$?; printf "%s" "$$code"'],
            }
        },
    }
    provider = object.__new__(RemoteDockerEnvironment)
    provider.extra_docker_compose_paths = []
    provider.project = project
    provider.identity = "identity"
    provider.endpoint = "ssh://docker-host"
    provider.environment_dir = tmp_path
    provider.root = tmp_path / "remote-root"
    provider.workspace = provider.root / project
    provider._remote_compose = None
    provider._workspace_created = False
    provider._resources = AsyncMock()
    provider._compose = AsyncMock(
        return_value=ExecResult(stdout=json.dumps(document), stderr="", return_code=0)
    )
    provider._shell = AsyncMock()
    provider.record = lambda *args, **kwargs: None
    provider.evidence = tmp_path / "remote.jsonl"

    await provider._prepare_remote()

    provider._compose.assert_awaited_once_with(
        ["config", "--format", "json"], rendered=False
    )
    rendered = json.loads(provider._remote_compose.read_text())
    assert rendered["services"]["main"]["entrypoint"][2] == (
        'code=$$?; printf "%s" "$$code"'
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("timeout", [None, 3600])
async def test_exec_preserves_trial_timeout_instead_of_transport_default(
    monkeypatch, timeout
):
    import harbor_remote_docker.environment as module

    run = AsyncMock(return_value=ExecResult(stdout="done", stderr="", return_code=0))
    monkeypatch.setattr(module, "run", run)
    provider = object.__new__(RemoteDockerEnvironment)
    provider.endpoint = "ssh://docker-host"
    provider.command_timeout = 120
    provider._container = AsyncMock(return_value="abcdef123456")
    provider._platform = SimpleNamespace(
        exec_shell_args=lambda command: ["sh", "-c", command]
    )
    provider._output_callback = lambda: None
    provider._client_env = lambda: {}
    provider.record = lambda *args, **kwargs: None

    await provider._compose_exec(
        "long-running-agent",
        service="main",
        cwd=None,
        env=None,
        timeout_sec=timeout,
        user=None,
    )

    assert run.await_args.kwargs["timeout"] == timeout
    await provider._run(["docker", "info"])
    assert run.await_args.kwargs["timeout"] == 120


@pytest.mark.asyncio
async def test_missing_task_workdir_is_not_reused_after_first_probe_failure(
    monkeypatch,
):
    """A missing task cwd must not break later artifact/verifier commands."""
    import harbor_remote_docker.environment as module

    calls: list[list[str]] = []

    async def fake_run(argv, **kwargs):
        calls.append(argv)
        if len(calls) == 1:
            # The actual test(1) command reports a missing directory silently.
            return ExecResult(stdout="", stderr="", return_code=1)
        return ExecResult(stdout="ok", stderr="", return_code=0)

    monkeypatch.setattr(module, "run", fake_run)
    try:
        provider = object.__new__(RemoteDockerEnvironment)
        provider.endpoint = "ssh://docker-host"
        provider.command_timeout = 30
        provider.task_env_config = SimpleNamespace(workdir="/deleted/workdir")
        provider._task_workdir_unavailable = False
        provider._container = AsyncMock(return_value="abcdef123456")
        provider._platform = SimpleNamespace(
            exec_shell_args=lambda command: ["sh", "-c", command]
        )
        provider._output_callback = lambda: None
        provider._client_env = lambda: {}
        provider.identity = "identity"
        provider.project = "project"
        provider.session_id = "session"
        provider.workspace = Path("/var/tmp/harbor-rsi/project")
        provider.record = lambda *args, **kwargs: None

        first = await provider._compose_exec(
            "test -d /logs/workspace-native",
            service="main",
            cwd="/deleted/workdir",
            env=None,
            timeout_sec=30,
            user="root",
        )
        second = await provider._compose_exec(
            "test -d /logs/workspace-native",
            service="main",
            cwd="/deleted/workdir",
            env=None,
            timeout_sec=30,
            user="root",
        )

        assert first.return_code == 0
        assert second.return_code == 0
        assert "-w" not in calls[-1]
        assert "abcdef123456" in calls[-1]
    finally:
        monkeypatch.undo()


@pytest.mark.asyncio
async def test_resource_identity_mismatch_fails_closed():
    provider = object.__new__(RemoteDockerEnvironment)
    provider.identity = "expected"
    provider.project = "project"
    provider.endpoint = "ssh://docker-host"
    provider.command_timeout = 1
    provider._client_env = lambda: {}
    provider.record = lambda *args, **kwargs: None
    responses = iter(
        [
            ExecResult(stdout="abcdef123456\n", stderr="", return_code=0),
            ExecResult(
                stdout=json.dumps(
                    [
                        {
                            "Config": {
                                "Labels": {
                                    "io.harbor.remote-docker.identity": "other",
                                    "com.docker.compose.project": "project",
                                }
                            }
                        }
                    ]
                ),
                stderr="",
                return_code=0,
            ),
            ExecResult(stdout="", stderr="", return_code=0),
            ExecResult(stdout="", stderr="", return_code=0),
        ]
    )
    provider._run = lambda *args, **kwargs: anext_async(responses)

    with pytest.raises(RemoteDockerError, match="identity mismatch"):
        await provider._resources()


async def anext_async(values):
    return next(values)


def test_controller_loss_writes_orphan_evidence(tmp_path: Path):
    provider = object.__new__(RemoteDockerEnvironment)
    provider.identity = "identity"
    provider.project = "project"
    provider.session_id = "session"
    provider.workspace = Path("/var/tmp/harbor-rsi/project")
    provider.evidence = tmp_path / "remote.jsonl"
    provider.record_controller_loss("supervisor_exit")
    event = json.loads(provider.evidence.read_text())
    assert event["action"] == "controller_loss"
    assert event["resources_may_remain"] is True
