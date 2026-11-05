"""Install an explicit OpenHarness wheel and execute its unmodified CLI."""

from __future__ import annotations

import asyncio
import hashlib
import json
import shlex
import shutil
import tempfile
from pathlib import Path, PurePosixPath
from typing import Any, ClassVar, Literal, override
from uuid import uuid4

from pydantic import Field, field_validator

from harbor.agents.capabilities import AgentCapabilities
from harbor.agents.installed.base import (
    ApiRateLimitError,
    BaseInstalledAgent,
    NonZeroAgentExitCodeError,
    PackageSpec,
)
from harbor.agents.model_connection import ModelConnectionSpec
from harbor.agents.options import InstalledAgentOptions
from harbor.environments.base import BaseEnvironment
from harbor.extensions.rsi.trajectory import redact_rollout, write_atif_trajectory
from harbor.models.agent.context import AgentContext
from harbor.utils.env import is_env_template, is_sensitive_env_key, resolve_env_vars


class OpenHarnessOptions(InstalledAgentOptions):
    wheel_path: str
    wheel_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    install_env: dict[str, str] = Field(default_factory=dict)
    bootstrap_uv_path: str | None = None
    bootstrap_uv_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    bootstrap_fd_path: str | None = None
    bootstrap_fd_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    cli_contract: Literal["openharness-cli-v1"] = "openharness-cli-v1"
    profile: Literal["native-cli-v1"] = "native-cli-v1"
    max_tokens: int | None = Field(default=None, gt=0)
    context_window: int | None = Field(default=None, gt=32768)
    default_tools: list[str] | None = None
    model_descriptor: dict[str, Any] | None = None
    record_trajectory: bool = False
    thinking: (
        Literal["off", "minimal", "low", "medium", "high", "xhigh", "max"] | None
    ) = None

    @field_validator("install_env")
    @classmethod
    def install_credentials_are_references(cls, values: dict[str, str]):
        for key, value in values.items():
            if is_sensitive_env_key(key) and not is_env_template(value):
                raise ValueError(
                    f"install_env {key} must use an inherited variable reference"
                )
            if "://" in value and "@" in value:
                raise ValueError(
                    "Credential-bearing install_env URLs must use inherited references"
                )
        return values


class OpenHarnessAgent(BaseInstalledAgent):
    SYSTEM_PACKAGES: ClassVar[dict[str, PackageSpec]] = {
        **BaseInstalledAgent.SYSTEM_PACKAGES,
        **{
            f"python3{minor}": PackageSpec(
                commands=(),
                packages={
                    "apt-get": (f"python3.{minor}-venv",),
                    "dnf": (f"python3.{minor}",),
                    "yum": (f"python3.{minor}",),
                    "apk": ("python3", "py3-virtualenv"),
                },
                always_install=True,
            )
            for minor in (12, 13)
        },
    }
    capabilities = AgentCapabilities(atif=True, native_config=True)
    managed_process_lifecycle = True
    MODEL_CONNECTION = ModelConnectionSpec(passthrough=True)
    options_model = OpenHarnessOptions
    options: OpenHarnessOptions
    _OUTPUT_FILENAME = "open-harness.stdout.jsonl"
    _REMOTE_VENV = "/tmp/harbor-open-harness-venv"
    _REMOTE_CLI = _REMOTE_VENV + "/bin/open-harness"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._instruction = ""
        self._runtime_dir = "/tmp"
        self._remote_venv = self._REMOTE_VENV
        self._remote_cli = self._REMOTE_CLI

    @staticmethod
    @override
    def name() -> str:
        return "open-harness"

    @override
    def runtime_requirements(self) -> dict[str, bool]:
        """OpenHarness needs writable storage that permits executable code."""
        return {"writable": True, "executable": True}

    @classmethod
    @override
    def preflight(cls, kwargs=None, env=None) -> None:
        options = cls.parse_options(kwargs, env)
        if not isinstance(options, OpenHarnessOptions):
            raise ValueError("OpenHarness options are required")
        if bool(options.bootstrap_fd_path) != bool(options.bootstrap_fd_sha256):
            raise ValueError(
                "bootstrap_fd_path and bootstrap_fd_sha256 must be supplied together"
            )
        if options.wheel_sha256 is None:
            raise ValueError("An explicit Harness wheel SHA256 is required")
        if options.bootstrap_fd_path:
            fd = Path(options.bootstrap_fd_path).expanduser().resolve()
            if (
                not fd.is_file()
                or hashlib.sha256(fd.read_bytes()).hexdigest()
                != options.bootstrap_fd_sha256
            ):
                raise ValueError("Bootstrap fd SHA256 does not match")
        wheel = Path(options.wheel_path).expanduser().resolve()
        if not wheel.is_file() or wheel.suffix != ".whl":
            raise ValueError("wheel_path must identify an existing .whl file")
        if (
            options.wheel_sha256
            and hashlib.sha256(wheel.read_bytes()).hexdigest() != options.wheel_sha256
        ):
            raise ValueError("Harness wheel SHA256 does not match")
        if options.context_window and not options.model_descriptor:
            raise ValueError(
                "Native context_window overrides require an explicit full model_descriptor"
            )

    @override
    def get_version_command(self) -> str:
        return f"{shlex.quote(self._remote_cli)} --version"

    def _configure_runtime_paths(self, environment: BaseEnvironment) -> None:
        configured = getattr(environment, "agent_runtime_dir", None)
        root = str(configured) if configured else "/tmp"
        if not root.startswith("/") or "\n" in root or "\x00" in root:
            raise RuntimeError(f"Invalid agent runtime directory: {root!r}")
        root = root.rstrip("/") or "/"
        self._runtime_dir = root
        self._remote_venv = f"{root}/harbor-open-harness-venv"
        self._remote_cli = f"{self._remote_venv}/bin/open-harness"

    async def _ensure_runtime_directory(self, environment: BaseEnvironment) -> None:
        """Fail before wheel installation when the runtime mount is noexec."""
        root = shlex.quote(self._runtime_dir)
        probe = shlex.quote(f"{self._runtime_dir}/.harbor-exec-probe-{uuid4().hex}")
        command = (
            f"set -eu; mkdir -p -- {root}; "
            f"probe={probe}; trap 'rm -f -- \"$probe\"' EXIT; "
            "printf '#!/bin/sh\\nexit 0\\n' >\"$probe\"; "
            'chmod 700 "$probe"; "$probe"'
        )
        try:
            await self.exec_as_agent(environment, command)
        except NonZeroAgentExitCodeError as exc:
            raise RuntimeError(
                "OpenHarness requires a writable executable agent runtime directory; "
                f"provider path {self._runtime_dir!r} rejected execution"
            ) from exc

    @override
    async def install(self, environment: BaseEnvironment) -> None:
        if self.options.install_env:
            # Reuse Harbor's nested, task-local exec scope. Installation settings
            # must not constrain task commands or the official verifier.
            with environment.scoped_exec_env(
                resolve_env_vars(self.options.install_env)
            ):
                await self._install_cli(environment)
        else:
            await self._install_cli(environment)

    async def _install_cli(self, environment: BaseEnvironment) -> None:
        self.preflight(self.options.model_dump())
        wheel = Path(self.options.wheel_path).expanduser().resolve()
        digest = hashlib.sha256(wheel.read_bytes()).hexdigest()
        await self.ensure_system_dependencies(environment, ("coreutils",))
        await self._ensure_search_dependencies(environment)
        self._configure_runtime_paths(environment)
        # Science task images can expose an older distro ``python3`` (notably
        # R images), while the current OpenHarness wheel requires Python >=3.11.
        interpreter_probe = await environment.exec(
            "for candidate in python3.13 python3.12 python3.11 python3; do "
            'if command -v "$candidate" >/dev/null 2>&1 && '
            "\"$candidate\" -c 'import sys; raise SystemExit(sys.version_info < (3, 11))' "
            ">/dev/null 2>&1; then printf '%s' \"$candidate\"; exit 0; fi; "
            "done; exit 1"
        )
        if (
            interpreter_probe.return_code
            or not (interpreter_probe.stdout or "").strip()
        ):
            bootstrap = await self._install_with_managed_python(environment, wheel)
            self._write_install_artifact(digest, bootstrap=bootstrap)
            return
        python_bin = (interpreter_probe.stdout or "").strip() or "python3.11"
        # Debian images can expose ``venv --help`` while omitting ensurepip;
        # that command only fails when the venv is actually created. Probe the
        # module required by venv so the package helper installs python3-venv
        # before uploading the wheel.
        probe = await environment.exec(
            f"{shlex.quote(python_bin)} -c 'import ensurepip' >/dev/null 2>&1"
        )
        if probe.return_code:
            interpreter = PurePosixPath(python_bin).name
            dependency = (
                "python_venv"
                if interpreter == "python3"
                else interpreter.replace(".", "")
            )
            await self.ensure_system_dependencies(environment, (dependency,))
            probe = await environment.exec(
                f"{shlex.quote(python_bin)} -c 'import ensurepip' >/dev/null 2>&1"
            )
            if probe.return_code:
                raise RuntimeError(f"{python_bin} is missing ensurepip")
        await self._ensure_runtime_directory(environment)
        remote = f"{self._runtime_dir}/{wheel.name}"
        await environment.upload_file(wheel, remote)
        await self.exec_as_agent(
            environment,
            command=(
                f"{shlex.quote(python_bin)} -m venv --clear {shlex.quote(self._remote_venv)} && "
                f"{shlex.quote(self._remote_venv + '/bin/python')} -m pip install --disable-pip-version-check "
                f"--no-input {shlex.quote(remote)} && {self.get_version_command()}"
            ),
            env={
                "TMPDIR": self._runtime_dir,
                "PIP_CACHE_DIR": f"{self._runtime_dir}/pip-cache",
            },
        )
        self.lifecycle_interpreter = f"{self._remote_venv}/bin/python"
        self._write_install_artifact(
            digest, interpreter=python_bin, runtime_dir=self._runtime_dir
        )

    async def _ensure_search_dependencies(self, environment: BaseEnvironment) -> None:
        # Host-prepared, hashed static fd avoids obsolete distro packages without
        # changing find's ignore semantics or downloading inside the task.
        if self.options.bootstrap_fd_path:
            fd = Path(self.options.bootstrap_fd_path).expanduser().resolve()
            digest = hashlib.sha256(fd.read_bytes()).hexdigest()
            if digest != self.options.bootstrap_fd_sha256:
                raise ValueError("Bootstrap fd SHA256 does not match")
            await self.ensure_system_dependencies(environment, ("ripgrep",))
            remote = "/tmp/harbor-open-harness-fd-" + digest
            await environment.upload_file(fd, remote)
            await self.exec_as_root(
                environment,
                command=(
                    f"printf '%s  %s\n' {shlex.quote(digest)} {shlex.quote(remote)} | sha256sum -c - && "
                    f"install -m 755 {shlex.quote(remote)} /usr/local/bin/fd && rm -- {shlex.quote(remote)}"
                ),
            )
        probe = "command -v rg && (command -v fd || command -v fdfind)"
        search = await environment.exec(command=probe, user="root")
        if search.return_code:
            await self.ensure_system_dependencies(environment, ("ripgrep", "fd"))
        # Missing package managers must not silently leave advertised tools broken.
        await self.exec_as_root(
            environment,
            command=(
                f"set -eu; {probe}; "
                "search_probe_dir=$(mktemp -d); "
                "trap 'rm -rf -- \"$search_probe_dir\"' EXIT; "
                "search_fd=$(command -v fd || command -v fdfind); "
                '"$search_fd" --no-require-git --max-results 1 --glob "*" "$search_probe_dir"'
            ),
        )

    async def _install_with_managed_python(
        self, environment: BaseEnvironment, wheel: Path
    ) -> dict[str, Any]:
        # Old task distributions may expose only Python 3.9 and no compatible
        # package. Keep their system runtime intact and bootstrap the CLI in
        # its private provider-selected runtime directory using a hashed host
        # uv artifact.
        uv_path = self.options.bootstrap_uv_path or shutil.which("uv")
        if not uv_path:
            raise RuntimeError(
                "Task has no Python >=3.11; bootstrap_uv_path or a host uv binary is required"
            )
        uv = Path(uv_path).expanduser().resolve()
        if not uv.is_file():
            raise ValueError("bootstrap_uv_path must identify an existing uv binary")
        digest = hashlib.sha256(uv.read_bytes()).hexdigest()
        if (
            self.options.bootstrap_uv_sha256
            and digest != self.options.bootstrap_uv_sha256
        ):
            raise ValueError("Bootstrap uv SHA256 does not match")
        await self._ensure_runtime_directory(environment)
        remote_uv = f"{self._runtime_dir}/harbor-open-harness-uv"
        remote_wheel = f"{self._runtime_dir}/{wheel.name}"
        await environment.upload_file(uv, remote_uv)
        await environment.upload_file(wheel, remote_wheel)
        await self.exec_as_agent(
            environment,
            command=(
                f"chmod 755 {shlex.quote(remote_uv)} && {shlex.quote(remote_uv)} --version && "
                f"{shlex.quote(remote_uv)} venv --clear --managed-python --python 3.12.12 {shlex.quote(self._remote_venv)} && "
                f"{shlex.quote(remote_uv)} pip install --python {shlex.quote(self._remote_venv + '/bin/python')} "
                f"{shlex.quote(remote_wheel)} && {self.get_version_command()}"
            ),
            env={
                "TMPDIR": self._runtime_dir,
                "UV_PYTHON_INSTALL_DIR": f"{self._runtime_dir}/python",
                "UV_CACHE_DIR": f"{self._runtime_dir}/uv-cache",
            },
        )
        self.lifecycle_interpreter = f"{self._remote_venv}/bin/python"
        return {
            "uv_path": str(uv),
            "uv_sha256": digest,
            "managed_python_version": "3.12.12",
            "system_python_unchanged": True,
            "runtime_dir": self._runtime_dir,
        }

    @override
    def _classify_exec_error(
        self, command: str, result: Any
    ) -> NonZeroAgentExitCodeError:
        """Classify only structured OpenHarness terminal errors.

        Tool output is intentionally free text and may mention third-party
        HTTP 429s.  Scanning the complete JSONL stream would misclassify those
        messages as model-provider rate limits.  Provider errors are emitted
        as structured ``error`` events; otherwise preserve the generic CLI
        failure and its original output.
        """
        events: list[dict[str, Any]] = []
        for line in (result.stdout or "").splitlines():
            try:
                event = json.loads(line)
            except (TypeError, json.JSONDecodeError):
                continue
            if isinstance(event, dict):
                events.append(event)

        structured_errors: list[str] = []
        for event in events:
            if event.get("type") != "error":
                continue
            value = event.get("message") or event.get("error")
            if isinstance(value, dict):
                value = value.get("message") or value.get("code") or value
            if value is not None:
                structured_errors.append(str(value))

        detail = (
            f"Command failed (exit {result.return_code}): "
            f"{self._redact_command(command)}\n"
            f"stdout: {self._truncate_output(result.stdout)}\n"
            f"stderr: {self._truncate_output(result.stderr)}"
        )
        if any(
            "rate_limit" in value.lower()
            or "rate limit" in value.lower()
            or "too many requests" in value.lower()
            or "http 429" in value.lower()
            for value in structured_errors
        ):
            return ApiRateLimitError(detail)
        if structured_errors:
            return super()._classify_exec_error_text(
                command, result, "\n".join(structured_errors)
            )
        if events:
            return NonZeroAgentExitCodeError(detail)
        return super()._classify_exec_error(command, result)

    def _write_install_artifact(self, digest: str, **runtime: Any) -> None:
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        (self.logs_dir / "artifact.json").write_text(
            json.dumps(
                {
                    "wheel_sha256": digest,
                    "cli_contract": self.options.cli_contract,
                    "profile": self.options.profile,
                    **runtime,
                },
                indent=2,
            )
            + "\n"
        )

    def harness_config(self) -> dict[str, Any]:
        source = self.config_source
        config = json.loads(source.read_text()) if isinstance(source, Path) else source
        if config is not None and not isinstance(config, dict):
            raise ValueError("OpenHarness native config must be a JSON object")
        config = config or {}
        provider, separator, model_id = (self.model_name or "").partition("/")
        if not provider or not separator or not model_id:
            raise ValueError("This CLI contract requires provider/<model>")
        access = self.model_connection
        endpoint = (access.base_url or "https://api.deepseek.com").rstrip("/")
        if endpoint.endswith("/chat/completions"):
            endpoint = endpoint.removesuffix("/chat/completions")
        native_model = config.get("model")
        if isinstance(native_model, str) and native_model != model_id:
            raise ValueError("Native config model must match the requested model")
        descriptor = self.options.model_descriptor
        if descriptor is None and isinstance(native_model, dict):
            descriptor = native_model
        if descriptor is not None:
            required = {
                "id",
                "api",
                "provider",
                "baseUrl",
                "contextWindow",
                "maxTokens",
                "cost",
                "input",
                "reasoning",
            }
            if (
                not required.issubset(descriptor)
                or descriptor["id"] != model_id
                or descriptor["provider"] != provider
            ):
                raise ValueError(
                    "model_descriptor must be complete and match the requested model"
                )
            if any(
                "key" in str(k).lower() or "token" == str(k).lower() for k in descriptor
            ):
                raise ValueError("Model credentials belong in the environment")
            descriptor = dict(descriptor)
        elif provider != "deepseek" or endpoint not in (
            "https://api.deepseek.com",
            "https://api.deepseek.com/v1",
        ):
            raise ValueError(
                "A custom endpoint requires an explicit model_descriptor in native profile"
            )
        if descriptor and self.options.context_window:
            descriptor["contextWindow"] = self.options.context_window
        config["model"] = descriptor or model_id
        if self.options.default_tools is not None:
            config["tools"] = self.options.default_tools
        if self.options.thinking is not None:
            config["thinkingLevel"] = self.options.thinking
        if self.options.max_tokens is not None:
            config["requestOptions"] = {
                **config.get("requestOptions", {}),
                "maxTokens": self.options.max_tokens,
            }
        return config

    async def _completion(
        self, environment: BaseEnvironment, remote: str, identity: str
    ) -> None:
        with tempfile.TemporaryDirectory(prefix="harbor-completion-") as directory:
            local = Path(directory) / "completion.json"
            while True:
                # Native runners may clean the task workdir as soon as the
                # completion marker is written. Keep lifecycle polling in the
                # provider-owned runtime mount instead of reopening that cwd.
                result = await environment.exec(
                    f"test -f {shlex.quote(remote)}", cwd=self._runtime_dir
                )
                if result.return_code == 0:
                    await environment.download_file(remote, local)
                    data = json.loads(local.read_text())
                    if (
                        data.get("identity") != identity
                        or type(data.get("exit_code")) is not int
                    ):
                        raise RuntimeError(
                            "Invalid or stale OpenHarness completion marker"
                        )
                    if data["exit_code"]:
                        raise NonZeroAgentExitCodeError(
                            f"OpenHarness exited with {data['exit_code']}"
                        )
                    return
                await asyncio.sleep(0.25)

    @override
    async def run(
        self, instruction: str, environment: BaseEnvironment, context: AgentContext
    ) -> None:
        self._instruction = instruction
        config = self.harness_config()
        access = self.model_connection
        if not access.api_key:
            provider = access.provider or "the configured model provider"
            raise ValueError(f"An API key is required for {provider}")
        location = await self.exec_as_agent(environment, "pwd -P")
        cwd = (location.stdout or "").removesuffix("\n")
        if not PurePosixPath(cwd).is_absolute():
            raise RuntimeError("Task working directory is not absolute")
        identity = uuid4().hex
        runtime_dir = self._runtime_dir.rstrip("/") or "/"
        remote_dir = f"{runtime_dir}/harbor-open-harness-{identity}"
        await self.exec_as_agent(environment, f"mkdir -m 700 {shlex.quote(remote_dir)}")
        await self._upload_config_text(
            environment,
            content=json.dumps(config),
            remote_path=remote_dir + "/config.json",
            filename="config.json",
        )
        with tempfile.TemporaryDirectory(prefix="harbor-instruction-") as directory:
            path = Path(directory) / "instruction.txt"
            path.write_text(instruction, encoding="utf-8")
            await environment.upload_file(path, remote_dir + "/instruction.txt")
        logs = self.environment_logs_dir.as_posix()
        marker = logs + "/open-harness.complete.json"
        argv = [
            self._remote_cli,
            "--cwd",
            cwd,
            "--print",
            "--mode",
            "json",
            "--config",
            remote_dir + "/config.json",
            "--prompt-file",
            remote_dir + "/instruction.txt",
        ]
        if self.options.record_trajectory:
            argv += [
                "--trajectory-dir",
                (self.environment_logs_dir / "openharness-rollout").as_posix(),
            ]
        stdout, stderr = (
            logs + "/" + self._OUTPUT_FILENAME,
            logs + "/open-harness.stderr.log",
        )
        command = (
            f"mkdir -p {shlex.quote(logs)}; rm -f {shlex.quote(marker)}; "
            f"status=0; {shlex.join(argv)} >{shlex.quote(stdout)} 2>{shlex.quote(stderr)} || status=$?; "
            f'printf \'{{"identity":"{identity}","exit_code":%s}}\\n\' "$status" >{shlex.quote(marker + ".tmp")}; '
            f"mv {shlex.quote(marker + '.tmp')} {shlex.quote(marker)}; "
            # Native logs are downloaded by Harbor after the agent phase.
            # Replaying an entire streaming JSONL transcript here can keep a
            # completed CLI inside the native deadline on a slow transport.
            f'if [ "$status" -ne 0 ]; then '
            f"tail -c 4096 {shlex.quote(stdout)}; "
            f"tail -c 4096 {shlex.quote(stderr)} >&2; fi; "
            f'exit "$status"'
        )
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        (self.logs_dir / "effective-config.json").write_text(
            json.dumps(config, indent=2) + "\n"
        )
        await self.exec_as_agent(
            environment,
            command=command,
            cwd=cwd,
            env={
                **self.extra_env,
                **access.env,
                "PYTHONUNBUFFERED": "1",
            },
        )
        await self._completion(environment, marker, identity)

    @override
    def redact_logs(self, secrets: set[str]) -> None:
        if secrets:
            root = self.logs_dir / "openharness-rollout"
            for manifest in root.rglob("manifest.json"):
                if (manifest.parent / "events.jsonl").is_file():
                    redact_rollout(manifest.parent, secrets)

    @override
    def populate_context_post_run(self, context: AgentContext) -> None:
        super().populate_context_post_run(context)
        # Transform this adapter's newly collected native traces before Harbor's
        # generic text scrubber can invalidate content-addressed references.
        env = resolve_env_vars({**self.extra_env, **self.model_connection.env})
        secrets = {v for k, v in env.items() if v and is_sensitive_env_key(k)}
        self.redact_logs(secrets)
        output = self.logs_dir / self._OUTPUT_FILENAME
        if output.is_file():
            write_atif_trajectory(
                output,
                self.logs_dir / "trajectory.json",
                instruction=self._instruction,
                model_name=self.model_name,
                agent_version=self.version() or "unknown",
            )
