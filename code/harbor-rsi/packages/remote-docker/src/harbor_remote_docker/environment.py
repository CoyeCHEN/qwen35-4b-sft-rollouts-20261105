"""SSH staging as an optional Harbor Environment, not a second execution chain."""

import asyncio
import hashlib
import functools
import json
import os
import re
import shlex
import shutil
import tempfile
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from uuid import uuid4
from typing import cast, override

from harbor.environments.base import ExecResult
from harbor.environments.capabilities import EnvironmentCapabilities
from harbor.environments.definition import should_use_prebuilt_docker_image
from harbor.environments.docker.docker import DockerEnvironment
from harbor.models.task.config import TaskOS

from harbor_remote_docker.compose import (
    IDENTITY_LABEL,
    PROJECT_LABEL,
    label_resources,
    load_compose_source,
    validate_compose,
)
from harbor_remote_docker.transport import (
    RemoteDockerError,
    file_hash,
    pack,
    run,
    ssh_target,
    unpack,
)


class _DefaultTimeout:
    pass


_DEFAULT_TIMEOUT = _DefaultTimeout()


async def _local_io(function, *args, **kwargs):
    """Keep filesystem latency off the loop; finish writes before cleanup."""
    operation = asyncio.create_task(asyncio.to_thread(function, *args, **kwargs))
    cancellation: asyncio.CancelledError | None = None
    while not operation.done():
        try:
            await asyncio.shield(operation)
        except asyncio.CancelledError as exc:
            # A filesystem thread keeps running after cancellation. Retain its
            # Task and await acknowledgement through repeated caller cancels.
            cancellation = exc
        except Exception:
            break  # Retrieve the original filesystem failure below.
    result = operation.result()
    if cancellation is not None:
        raise cancellation
    return result


class RemoteDockerEnvironment(DockerEnvironment):
    """Reuse Docker's Compose/resource helpers; isolate transport and cleanup."""

    def __init__(
        self,
        *args,
        endpoint: str | None = None,
        docker_context: str | None = None,
        staging_root: str,
        project_namespace: str = "harbor",
        remote_socket_path: str = "/var/run/docker.sock",
        command_timeout_sec: float = 120,
        transfer_timeout_sec: float = 600,
        cleanup_timeout_sec: float = 120,
        agent_runtime_volume: bool = False,
        verifier_test_volume: bool = False,
        **kwargs,
    ):
        if bool(endpoint) == bool(docker_context):
            raise ValueError("Specify exactly one of endpoint or docker_context")
        if endpoint:
            ssh_target(endpoint)
        if docker_context and (
            docker_context.startswith("-")
            or not re.fullmatch(r"[\w.-]+", docker_context)
        ):
            raise ValueError("Invalid Docker context name")
        root = PurePosixPath(staging_root)
        if (
            not root.is_absolute()
            or ".." in root.parts
            or len(root.parts) < 3
            or str(root) != staging_root
        ):
            raise ValueError(
                "staging_root must be a private normalized absolute directory"
            )
        if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,39}", project_namespace):
            raise ValueError("Invalid project_namespace")
        socket = PurePosixPath(remote_socket_path)
        if (
            not socket.is_absolute()
            or ".." in socket.parts
            or str(socket) != remote_socket_path
            or not re.fullmatch(r"/[A-Za-z0-9_./-]+", remote_socket_path)
        ):
            raise ValueError("remote_socket_path must be a normalized absolute path")
        if any(
            value <= 0
            for value in (
                command_timeout_sec,
                transfer_timeout_sec,
                cleanup_timeout_sec,
            )
        ):
            raise ValueError("Provider timeouts must be positive")
        if kwargs.get("keep_containers"):
            raise ValueError("Use environment.delete=false to retain owned resources")
        self.endpoint, self.docker_context = endpoint, docker_context
        self.identity = uuid4().hex
        self.project = f"{project_namespace}-{self.identity}"
        self.root, self.workspace = root, root / self.project
        self.remote_socket_path = remote_socket_path
        self.command_timeout = command_timeout_sec
        self.transfer_timeout = transfer_timeout_sec
        self.cleanup_timeout = cleanup_timeout_sec
        self._remote_compose: Path | None = None
        self._workspace_created = False
        self._prepared = False
        self._task_workdir_unavailable = False
        self._read_only_services: set[str] = set()
        self._ssh: list[str] = []
        self._agent_runtime_volume_key: str | None = None
        self._verifier_test_volume_key: str | None = None
        self._use_agent_runtime_volume = agent_runtime_volume
        self._use_verifier_test_volume = verifier_test_volume
        if agent_runtime_volume and kwargs.get("agent_runtime_dir"):
            raise ValueError(
                "Choose an existing agent_runtime_dir or agent_runtime_volume"
            )
        super().__init__(*args, **kwargs)
        if self.task_env_config.os != TaskOS.LINUX:
            raise ValueError("Remote Docker supports Linux tasks only")
        self.evidence = (
            self.trial_paths.trial_dir / f"remote-docker-{self.identity}.jsonl"
        )

    @classmethod
    @override
    def preflight(cls) -> None:
        # No remote daemon is required merely to import or construct the provider.
        for executable in ("docker", "ssh"):
            if not shutil.which(executable):
                raise RuntimeError(f"Remote Docker requires the {executable} client")

    @classmethod
    @override
    @functools.cache
    def _egress_control_kernel_support(cls) -> bool:
        return False

    @property
    @override
    def capabilities(self) -> EnvironmentCapabilities:
        return EnvironmentCapabilities(docker_compose=True, mounted=False)

    @override
    def configure_agent_runtime(
        self, *, writable: bool = False, executable: bool = False
    ) -> None:
        """Use existing storage unless an executable volume is explicitly enabled.

        The task's own ``/tmp`` mount may intentionally be ``noexec``. The
        runtime volume is added only when the deployment enables it and an
        agent explicitly requests it. It is labelled with this provider's
        identity, so ordinary tasks retain
        their declared mounts and cleanup remains resource-scoped.
        """
        super().configure_agent_runtime(writable=writable, executable=executable)
        if (writable or executable) and self._use_agent_runtime_volume:
            self._agent_runtime_dir = PurePosixPath("/harbor/agent-runtime")
            self._agent_runtime_volume_key = "agent-runtime"
            self.record(
                "agent_runtime_requested",
                path=str(self._agent_runtime_dir),
                writable=writable,
                executable=executable,
            )

    def record(self, action: str, **details) -> None:
        self.evidence.parent.mkdir(parents=True, exist_ok=True)
        with self.evidence.open("a") as stream:
            stream.write(
                json.dumps(
                    {
                        "identity": self.identity,
                        "project": self.project,
                        "session_id": self.session_id,
                        "workspace": str(self.workspace),
                        "time": datetime.now(timezone.utc).isoformat(),
                        "action": action,
                        **details,
                    }
                )
                + "\n"
            )
        self.evidence.chmod(0o600)

    def record_controller_loss(self, reason: str = "controller_lost") -> None:
        """Persist orphan evidence when a supervisor disappears mid-trial."""
        self.record(
            "controller_loss",
            reason=reason,
            resources_may_remain=True,
            cleanup_required=True,
        )

    @staticmethod
    def _output_tail(value: str | None, limit: int = 2000) -> str:
        value = value or ""
        return value if len(value) <= limit else value[-limit:]

    def _exec_output_tail(self, value: str | None, env: dict[str, str] | None) -> str:
        text = value or ""
        for key, secret in {**os.environ, **(env or {})}.items():
            if secret and re.search(r"key|token|secret|password|credential", key, re.I):
                text = text.replace(secret, "[REDACTED]")
        return self._output_tail(text)

    def _client_env(self) -> dict[str, str]:
        return {
            k: v
            for k, v in os.environ.items()
            if k
            not in (
                "DOCKER_CONTEXT",
                "DOCKER_HOST",
                "DOCKER_TLS_VERIFY",
                "DOCKER_CERT_PATH",
            )
        }

    def _docker(self, *args: str) -> list[str]:
        if self.endpoint is None:
            raise RemoteDockerError("Remote endpoint has not been resolved")
        return ["docker", "--host", self.endpoint, *args]

    async def _run(
        self,
        argv,
        *,
        check=True,
        timeout: float | None | _DefaultTimeout = _DEFAULT_TIMEOUT,
        **kwargs,
    ) -> ExecResult:
        # transport.run captures both streams as strings, including empty output;
        # BaseEnvironment.ExecResult also permits None for unrelated providers.
        try:
            result = await run(
                argv,
                timeout=self.command_timeout
                if isinstance(timeout, _DefaultTimeout)
                else timeout,
                env=kwargs.pop("env", self._client_env()),
                **kwargs,
            )
        except BaseException as exc:
            self.record(
                "operation_interrupted",
                error_type=type(exc).__name__,
                error=str(exc),
                operation=shlex.join(argv),
                resources_may_remain=True,
            )
            raise
        diagnostic = (result.stderr or "").lower()
        if result.return_code == 255 and any(
            marker in diagnostic
            for marker in (
                "connection reset",
                "connection timed out",
                "broken pipe",
                "connection closed",
                "connection refused",
                "kex_exchange_identification",
                "ssh_exchange_identification",
            )
        ):
            self.record(
                "transport_lost",
                operation=shlex.join(argv),
                stderr_tail=self._output_tail(result.stderr),
                stdout_tail=self._output_tail(result.stdout),
                resources_may_remain=True,
            )
            raise RemoteDockerError("SSH transport failed; command was not replayed")
        if check and result.return_code:
            self.record(
                "operation_failed",
                exit_code=result.return_code,
                operation=shlex.join(argv),
                stderr_tail=self._output_tail(result.stderr),
                stdout_tail=self._output_tail(result.stdout),
                resources_may_remain=True,
            )
            raise RemoteDockerError(
                f"Remote operation failed (exit {result.return_code}); "
                f"stderr: {self._output_tail(result.stderr, 500)}; resources retained"
            )
        return result

    async def _shell(self, script: str, **kwargs) -> ExecResult:
        return await self._run([*self._ssh, script], **kwargs)

    def _marker_guard(self) -> str:
        path = shlex.quote(str(self.workspace))
        return f'set -eu; test "$(realpath -- {path})" = {path}; test -O {path}; test "$(cat {path}/.identity)" = {self.identity}; '

    async def _connect(self) -> None:
        if self.endpoint is None:
            result = await self._run(
                ["docker", "context", "inspect", self.docker_context]
            )
            self.endpoint = json.loads(cast(str, result.stdout))[0]["Endpoints"][
                "docker"
            ]["Host"]
        self._ssh = ssh_target(self.endpoint)
        local = await self._run(self._docker("info", "--format", "{{json .}}"))
        remote = await self._shell(
            "docker --host unix://"
            + self.remote_socket_path
            + " info --format '{{json .}}'"
        )
        left, right = (
            json.loads(cast(str, local.stdout)),
            json.loads(cast(str, remote.stdout)),
        )
        if (
            not left.get("ID")
            or left["ID"] != right.get("ID")
            or left.get("OSType") != "linux"
        ):
            raise RemoteDockerError(
                "SSH staging and Docker client must reach the same Linux daemon"
            )
        self.record("connected", endpoint=self.endpoint, daemon_id=left["ID"])

    async def _compose(self, command, *, rendered=True, **kwargs):
        paths = (
            [self._remote_compose]
            if rendered and self._remote_compose
            else super()._docker_compose_paths
        )
        argv = self._docker(
            "compose",
            "--project-name",
            self.project,
            "--project-directory",
            str(self.environment_dir.resolve()),
        )
        for path in paths:
            argv.extend(["-f", str(path)])
        argv.extend(command)
        env = self._compose_env_vars(include_os_env=True)
        for key in (
            "DOCKER_CONTEXT",
            "DOCKER_HOST",
            "DOCKER_TLS_VERIFY",
            "DOCKER_CERT_PATH",
        ):
            env.pop(key, None)
        return await self._run(argv, env=env, **kwargs)

    @override
    async def _run_docker_compose_command(
        self, command, check=True, timeout_sec=None, stdin_data=None, on_output=None
    ):
        return await self._compose(
            command,
            check=check,
            timeout=timeout_sec,
            data=stdin_data,
            on_output=on_output,
        )

    async def _prepare_remote(self) -> None:
        for candidate in [
            self._environment_docker_compose_path,
            *self.extra_docker_compose_paths,
        ]:
            if candidate.exists():
                source = load_compose_source(candidate.read_text())
                if source.get("include") or any(
                    s.get("extends") for s in source.get("services", {}).values()
                ):
                    raise ValueError("Remote Docker include/extends are not supported")
        # Compose resolves paths and variables and preserves escaped shell
        # dollars in its canonical output. Do not reinterpret them here.
        rendered = await self._compose(["config", "--format", "json"], rendered=False)
        document = json.loads(rendered.stdout)
        self._read_only_services = {
            name
            for name, service in document.get("services", {}).items()
            if isinstance(service, dict) and service.get("read_only") is True
        }
        runtime_volume_key = getattr(self, "_agent_runtime_volume_key", None)
        if runtime_volume_key is not None:
            runtime_target = str(self._agent_runtime_dir)
            main = document["services"]["main"]
            if any(
                isinstance(mount, dict) and mount.get("target") == runtime_target
                for mount in main.get("volumes", [])
            ):
                raise RemoteDockerError(
                    f"Task already declares the agent runtime target {runtime_target}"
                )
            main.setdefault("volumes", []).append(
                {
                    "type": "volume",
                    "source": runtime_volume_key,
                    "target": runtime_target,
                }
            )
            document.setdefault("volumes", {})[runtime_volume_key] = {}
            self.record(
                "agent_runtime_volume_added",
                volume=runtime_volume_key,
                target=runtime_target,
            )
        if getattr(self, "_use_verifier_test_volume", False):
            verifier_target = "/tests"
            main = document["services"]["main"]
            if any(
                isinstance(mount, dict) and mount.get("target") == verifier_target
                for mount in main.get("volumes", [])
            ):
                raise RemoteDockerError(
                    f"Task already declares the verifier test target {verifier_target}"
                )
            self._verifier_test_volume_key = "verifier-tests"
            main.setdefault("volumes", []).append(
                {
                    "type": "volume",
                    "source": self._verifier_test_volume_key,
                    "target": verifier_target,
                }
            )
            document.setdefault("volumes", {})[self._verifier_test_volume_key] = {}
            self.record(
                "verifier_test_volume_added",
                volume=self._verifier_test_volume_key,
                target=verifier_target,
            )
        roots = [
            self.environment_dir.resolve(),
            *[p.parent.resolve() for p in self.extra_docker_compose_paths],
        ]
        binds = validate_compose(document, self.project, roots)
        await self._resources(require_empty=True)
        root, workspace = shlex.quote(str(self.root)), shlex.quote(str(self.workspace))
        self.record("create_requested", endpoint=self.endpoint)
        await self._shell(
            f'set -eu; umask 077; mkdir -p -- {root}; test "$(realpath -- {root})" = {root}; test -O {root}; test "$(stat -c %a -- {root})" = 700; mkdir -- {workspace}; printf %s {self.identity} > {workspace}/.identity'
        )
        self._workspace_created = True
        for index, (source, mounts) in enumerate(binds.items()):
            destination = self.workspace / f"bind-{index}"
            with tempfile.TemporaryDirectory(prefix="harbor-stage-") as temporary:
                archive = Path(temporary) / "input.tar"
                await _local_io(pack, source, archive)
                await self._send_archive(archive, "stage.tar")
                remote_archive = shlex.quote(str(self.workspace / "stage.tar"))
                dest = shlex.quote(str(destination))
                await self._shell(
                    self._marker_guard()
                    + f"mkdir -- {dest}; tar --no-same-owner -xpf {remote_archive} -C {dest}; rm -- {remote_archive}",
                    timeout=self.transfer_timeout,
                )
            for mount in mounts:
                mount["source"] = str(destination / "input")
                mount.setdefault("bind", {})["create_host_path"] = False
        label_resources(document, self.identity)
        self._remote_compose = self.evidence.with_suffix(".compose.json")
        self._remote_compose.touch(mode=0o600, exist_ok=False)
        self._remote_compose.write_text(json.dumps(document))
        self._prepared = True
        self.record("prepared", compose_file=str(self._remote_compose))

    @override
    async def start(self, force_build: bool) -> None:
        if self._prepared or self._workspace_created:
            raise RemoteDockerError("Start is single-use; refusing duplicate dispatch")
        # Trial mount specs are local log hints. Remote logs use ArtifactHandler's
        # existing non-mounted download path, not mirrored writable host binds.
        self._resources_compose_path = self._write_resources_compose_file()
        self._env_compose_path = self._write_env_compose_file()
        self._use_prebuilt = should_use_prebuilt_docker_image(
            self.environment_dir,
            docker_image=self.task_env_config.docker_image,
            force_build=force_build,
        )
        await self._connect()
        try:
            await self._prepare_remote()
            if not self._use_prebuilt:
                lock = self._image_build_locks.setdefault(
                    f"{self.endpoint}:{self.environment_id}", asyncio.Lock()
                )
                async with lock:
                    await self._compose(
                        ["build"], timeout=self.task_env_config.build_timeout_sec
                    )
            await self._compose(
                ["up", "--detach", "--wait"],
                timeout=self.task_env_config.build_timeout_sec,
            )
            await self._resources()
            writable_targets = self._mount_targets(writable_only=True)
            if self._agent_runtime_volume_key is not None:
                writable_targets.append(str(self._agent_runtime_dir))
            await self.ensure_dirs(writable_targets)
            await self._upload_environment_dir_after_start()
            self.record("started")
        except BaseException as exc:
            self.record(
                "start_failed", error_type=type(exc).__name__, resources_may_remain=True
            )
            raise

    async def _resources(self, *, require_empty=False) -> dict[str, list[str]]:
        resources = {}
        for kind, args in (
            ("container", ["ps", "-aq"]),
            ("network", ["network", "ls", "-q"]),
            ("volume", ["volume", "ls", "-q"]),
        ):
            result = await self._run(
                self._docker(*args, "--filter", f"label={PROJECT_LABEL}={self.project}")
            )
            identifiers = cast(str, result.stdout).split()
            resources[kind] = identifiers
            if require_empty and identifiers:
                raise RemoteDockerError("Project already exists; refusing to adopt it")
            if identifiers:
                if any(
                    not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_.-]*", i)
                    for i in identifiers
                ):
                    raise RemoteDockerError("Invalid resource identifier")
                details = json.loads(
                    cast(
                        str,
                        (
                            await self._run(self._docker(kind, "inspect", *identifiers))
                        ).stdout,
                    )
                )
                if len(details) != len(identifiers):
                    raise RemoteDockerError("Incomplete resource inspection")
                for detail in details:
                    labels = (
                        detail.get("Config", {}) if kind == "container" else detail
                    ).get("Labels") or {}
                    if (
                        labels.get(IDENTITY_LABEL) != self.identity
                        or labels.get(PROJECT_LABEL) != self.project
                    ):
                        raise RemoteDockerError(
                            "Resource identity mismatch; resources retained"
                        )
        return resources

    async def _container(self, service: str) -> str:
        result = await self._compose(["ps", "--all", "-q", service])
        identifier = result.stdout.strip()
        if not re.fullmatch(r"[a-f0-9]{12,64}", identifier):
            raise RemoteDockerError("Expected exactly one service container")
        detail = json.loads(
            cast(
                str,
                (
                    await self._run(self._docker("container", "inspect", identifier))
                ).stdout,
            )
        )[0]
        labels = detail.get("Config", {}).get("Labels") or {}
        if (
            labels.get(IDENTITY_LABEL) != self.identity
            or labels.get(PROJECT_LABEL) != self.project
            or labels.get("com.docker.compose.service") != service
        ):
            raise RemoteDockerError("Container identity mismatch")
        return identifier

    @override
    async def _compose_exec(self, command, *, service, cwd, env, timeout_sec, user):
        started = asyncio.get_running_loop().time()
        container = await self._container(service)
        effective_cwd = cwd
        task_workdir = str(
            getattr(getattr(self, "task_env_config", None), "workdir", "") or ""
        )
        if (
            service == "main"
            and effective_cwd
            and task_workdir
            and str(effective_cwd) == task_workdir
        ):
            if getattr(self, "_task_workdir_unavailable", False):
                # Once the task workdir has disappeared, every later command
                # must omit ``-w`` as well. Reusing the stale cwd makes
                # Docker reject otherwise valid artifact and verifier calls.
                effective_cwd = None
            else:
                probe_timeout = min(timeout_sec or self.command_timeout, 30)
                try:
                    probe = await self._run(
                        self._docker("exec", container, "test", "-d", task_workdir),
                        check=False,
                        timeout=probe_timeout,
                    )
                except TimeoutError as exc:
                    # This preflight has its own short budget. A bare timeout
                    # would be mistaken for the caller's native phase deadline,
                    # even though its requested command was never dispatched.
                    raise RemoteDockerError(
                        f"Task workdir probe timed out after {probe_timeout} seconds "
                        "before command dispatch"
                    ) from exc
                # A false `test -d` is silent. Docker/SSH can also return 1,
                # with diagnostics, without establishing the directory state.
                # Do not change cwd or dispatch a command after that failure.
                if probe.return_code not in (0, 1) or (
                    probe.return_code == 1 and (probe.stdout or probe.stderr)
                ):
                    raise RemoteDockerError(
                        f"Task workdir probe failed (exit {probe.return_code}); "
                        "directory state was not established; "
                        f"stderr: {self._exec_output_tail(probe.stderr, None)}; "
                        f"stdout: {self._exec_output_tail(probe.stdout, None)}"
                    )
                if probe.return_code == 1:
                    self._task_workdir_unavailable = True
                    self.record(
                        "task_workdir_unavailable",
                        path=task_workdir,
                        operation="exec",
                    )
                    effective_cwd = None
        with tempfile.TemporaryDirectory(prefix="harbor-exec-") as temporary:
            argv = self._docker("exec")
            if env:
                for key, value in env.items():
                    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key) or any(
                        c in value for c in "\r\n\x00"
                    ):
                        raise ValueError(
                            "Remote exec env requires single-line POSIX values"
                        )
                path = Path(temporary) / "env"
                path.touch(mode=0o600)
                path.write_text(
                    "".join(f"{key}={value}\n" for key, value in env.items())
                )
                argv.extend(["--env-file", str(path)])
            if effective_cwd:
                argv.extend(["-w", effective_cwd])
            if user is not None:
                argv.extend(["-u", str(user)])
            argv.extend(
                [
                    container,
                    *(
                        self._platform.exec_shell_args(command)
                        if service == "main"
                        else ["sh", "-c", command]
                    ),
                ]
            )
            result = await self._run(
                argv,
                check=False,
                timeout=timeout_sec,
                on_output=self._output_callback(),
            )
            self.record(
                "exec_completed",
                command_sha256=hashlib.sha256(command.encode()).hexdigest(),
                service=service,
                container=container,
                requested_cwd=cwd,
                cwd=effective_cwd,
                user=user,
                exit_code=result.return_code,
                stderr_tail=self._exec_output_tail(result.stderr, env),
                stdout_tail=self._exec_output_tail(result.stdout, env)
                if result.return_code
                else "",
                stdout_bytes=len((result.stdout or "").encode()),
                stderr_bytes=len((result.stderr or "").encode()),
                duration_ms=round((asyncio.get_running_loop().time() - started) * 1000),
            )
            return result

    async def _send_archive(self, archive: Path, name: str) -> None:
        remote = shlex.quote(str(self.workspace / name))
        await self._shell(
            self._marker_guard() + f"umask 077; cat > {remote}",
            source=archive,
            timeout=self.transfer_timeout,
        )
        result = await self._shell(self._marker_guard() + f"sha256sum -- {remote}")
        digest = await _local_io(file_hash, archive)
        if cast(str, result.stdout).split()[0] != digest:
            raise RemoteDockerError("File transfer SHA-256 mismatch")
        self.record("uploaded_archive", sha256=digest, bytes=archive.stat().st_size)

    async def _copy_archive_to_container(
        self,
        archive: Path,
        container: str,
        destination: str,
        remote: str,
        *,
        service: str = "main",
    ) -> None:
        tar_command = (
            self._marker_guard()
            + f"docker --host unix://{self.remote_socket_path} exec -i -u root -w / "
            f"{shlex.quote(container)} tar -xpf - -C {shlex.quote(destination)}"
        )
        if service in getattr(self, "_read_only_services", set()):
            await self._shell(
                tar_command, source=archive, timeout=self.transfer_timeout
            )
            return
        command = (
            self._marker_guard()
            + f"docker --host unix://{self.remote_socket_path} cp - "
            f"{shlex.quote(container + ':' + destination)} < {remote}"
        )
        try:
            await self._shell(command, timeout=self.transfer_timeout)
        except RemoteDockerError as exc:
            if "container rootfs is marked read-only" not in str(exc).lower():
                raise
            # Docker's daemon-side cp cannot write a read-only rootfs even
            # when the destination is a writable tmpfs. Stream the archive
            # through exec instead; the container process writes to the
            # declared mount and tar preserves the archive's file semantics.
            self.record(
                "transfer_fallback",
                reason="docker_cp_read_only_rootfs",
                container=container,
                destination=destination,
            )
            await self._shell(
                tar_command,
                source=archive,
                timeout=self.transfer_timeout,
            )

    async def _copy_archive_from_container(
        self, container: str, source: str, remote: str, *, service: str = "main"
    ) -> None:
        if source.endswith("/."):
            path = PurePosixPath(source[:-2] or "/")
            command = (
                f"umask 077; docker --host unix://{self.remote_socket_path} exec -u root -w / "
                f"{shlex.quote(container)} tar -cpf - -C "
                f"{shlex.quote(str(path))} . > {remote}"
            )
        else:
            path = PurePosixPath(source)
            command = (
                f"umask 077; docker --host unix://{self.remote_socket_path} exec -u root -w / "
                f"{shlex.quote(container)} tar -cpf - -C "
                f"{shlex.quote(str(path.parent))} {shlex.quote(path.name)} > {remote}"
            )
        if service in self._read_only_services:
            await self._shell(
                self._marker_guard() + command, timeout=self.transfer_timeout
            )
            return
        try:
            await self._shell(
                self._marker_guard()
                + f"umask 077; docker --host unix://{self.remote_socket_path} cp "
                f"{shlex.quote(container + ':' + source)} - > {remote}",
                timeout=self.transfer_timeout,
            )
        except RemoteDockerError as exc:
            if "container rootfs is marked read-only" not in str(exc).lower():
                raise
            self.record(
                "transfer_fallback",
                reason="docker_cp_read_only_rootfs",
                container=container,
                source=source,
            )
            await self._shell(
                self._marker_guard() + command, timeout=self.transfer_timeout
            )

    async def _transfer(
        self, source, target, *, upload: bool, directory: bool, service="main"
    ) -> None:
        container = await self._container(service)
        name = f"transfer-{uuid4().hex}.tar"
        remote = shlex.quote(str(self.workspace / name))
        with tempfile.TemporaryDirectory(prefix="harbor-transfer-") as temporary:
            archive = Path(temporary) / "transfer.tar"
            if upload:
                source = Path(source)
                target = PurePosixPath(target)
                if not target.is_absolute() or ".." in target.parts:
                    raise ValueError(
                        "Transfer destination must be an absolute container path"
                    )
                verifier_volume_target = (
                    directory
                    and str(target) == "/tests"
                    and getattr(self, "_use_verifier_test_volume", False)
                )
                if not directory and not verifier_volume_target:
                    check = await self.service_exec(
                        f"test -d {shlex.quote(str(target))}",
                        service=service,
                        user="root",
                        cwd="/",
                    )
                    if check.return_code == 0:
                        target /= source.name
                destination = target if directory else target.parent
                if not verifier_volume_target:
                    result = await self.service_exec(
                        f"mkdir -p -- {shlex.quote(str(destination))}",
                        service=service,
                        user="root",
                        cwd="/",
                    )
                    if result.return_code:
                        self.record(
                            "transfer_destination_failed",
                            target=str(destination),
                            return_code=result.return_code,
                            stderr=self._output_tail(result.stderr),
                        )
                        raise RemoteDockerError(
                            "Cannot create container transfer destination"
                        )
                await _local_io(
                    pack, source, archive, contents=directory, name=target.name
                )
                await self._send_archive(archive, name)
                await self._copy_archive_to_container(
                    archive, container, str(destination), remote, service=service
                )
            else:
                remote_source = str(source).rstrip("/") + ("/." if directory else "")
                await self._copy_archive_from_container(
                    container, remote_source, remote, service=service
                )
                digest = cast(
                    str,
                    (
                        await self._shell(
                            self._marker_guard() + f"sha256sum -- {remote}"
                        )
                    ).stdout,
                ).split()[0]
                await self._shell(
                    self._marker_guard() + f"cat -- {remote}",
                    target=archive,
                    timeout=self.transfer_timeout,
                )
                if await _local_io(file_hash, archive) != digest:
                    raise RemoteDockerError("File transfer SHA-256 mismatch")
                extraction = Path(temporary) / "extracted"
                extraction.mkdir()
                await _local_io(unpack, archive, extraction)
                target = Path(target)
                await _local_io(
                    self._publish_download, extraction, target, directory=directory
                )
                self.record(
                    "downloaded_archive", sha256=digest, bytes=archive.stat().st_size
                )
            await self._shell(self._marker_guard() + f"rm -- {remote}")

    @staticmethod
    def _publish_download(extraction: Path, target: Path, *, directory: bool):
        if (
            target.is_symlink()
            or any(p.is_symlink() for p in target.parents)
            or (target.is_dir() and any(p.is_symlink() for p in target.rglob("*")))
        ):
            raise RemoteDockerError("Refusing local symlink destination")
        if directory:
            shutil.copytree(extraction, target, dirs_exist_ok=True, symlinks=True)
        else:
            members = list(extraction.iterdir())
            if len(members) != 1 or not members[0].is_file() or members[0].is_symlink():
                raise RemoteDockerError("Expected one regular file in transfer")
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(members[0], target)

    @override
    async def upload_file(self, source_path, target_path):
        await self._transfer(source_path, target_path, upload=True, directory=False)

    @override
    async def upload_dir(self, source_dir, target_dir):
        await self._transfer(source_dir, target_dir, upload=True, directory=True)

    @override
    async def download_file(self, source_path, target_path):
        await self._transfer(source_path, target_path, upload=False, directory=False)

    @override
    async def download_dir(self, source_dir, target_dir):
        await self._transfer(source_dir, target_dir, upload=False, directory=True)

    @override
    async def service_download_file(self, source_path, target_path, *, service=None):
        await self._transfer(
            source_path,
            target_path,
            upload=False,
            directory=False,
            service=service or "main",
        )

    @override
    async def service_download_dir(self, source_dir, target_dir, *, service=None):
        await self._transfer(
            source_dir,
            target_dir,
            upload=False,
            directory=True,
            service=service or "main",
        )

    @override
    async def stop_service(self, service):
        container = await self._container(service)
        await self._run(self._docker("stop", container))

    @override
    async def prepare_logs_for_host(self):
        # docker cp produces client-owned files. No recursive container chown.
        return

    @contextmanager
    def _cleanup_phase(self, phase: str, **identity):
        started = time.monotonic()
        self.record("cleanup_phase_started", phase=phase, **identity)
        try:
            yield
        except BaseException as exc:
            self.record(
                "cleanup_phase_finished",
                phase=phase,
                elapsed_sec=time.monotonic() - started,
                outcome="UNKNOWN",
                error_type=type(exc).__name__,
                **identity,
            )
            raise
        else:
            self.record(
                "cleanup_phase_finished",
                phase=phase,
                elapsed_sec=time.monotonic() - started,
                outcome="ACKNOWLEDGED",
                **identity,
            )

    @override
    async def stop(self, delete: bool):
        try:
            if not self._ssh:
                return
            self.record("cleanup_started", timeout_sec=self.cleanup_timeout)
            async with asyncio.timeout(self.cleanup_timeout):
                with self._cleanup_phase("discover_resources"):
                    resources = await self._resources()
                if not delete:
                    for container in resources["container"]:
                        with self._cleanup_phase(
                            "stop_container", resource_id=container
                        ):
                            await self._run(self._docker("stop", container))
                    self.record("retained", resources=resources)
                    return
                # Remove exact verified IDs; never remove shared images or prune.
                for kind, identifiers in resources.items():
                    for identifier in identifiers:
                        with self._cleanup_phase(
                            "remove_resource", kind=kind, resource_id=identifier
                        ):
                            await self._run(
                                self._docker(
                                    kind,
                                    "rm",
                                    *(["--force"] if kind == "container" else []),
                                    identifier,
                                )
                            )
                with self._cleanup_phase("confirm_resources_absent"):
                    if any((await self._resources()).values()):
                        raise RemoteDockerError(
                            "Resource cleanup could not be confirmed"
                        )
                if self._workspace_created:
                    workspace = shlex.quote(str(self.workspace))
                    with self._cleanup_phase("remove_workspace"):
                        await self._shell(
                            self._marker_guard()
                            + f"rm -rf -- {workspace}; test ! -e {workspace}"
                        )
                    self._workspace_created = False
                self.record("cleaned")
        except BaseException as exc:
            self.record(
                "cleanup_pending",
                error_type=type(exc).__name__,
                resources_may_remain=True,
            )
            raise
        finally:
            self._cleanup_resources_compose_file()
            self._cleanup_env_compose_file()

    @override
    async def attach(self):
        raise NotImplementedError(
            "Interactive attach is not supported by Remote Docker"
        )
