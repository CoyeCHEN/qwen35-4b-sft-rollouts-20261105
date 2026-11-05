"""Explicit environment gates for RSI campaigns; execution stays in native Harbor.

No agent.run(), oracle, verifier scoring or reward synthesis occurs in preparation.
Checks are trusted, reviewed configuration, not commands inferred from instructions.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import importlib
import importlib.metadata
import json
import logging
import math
import os
import re
import socket
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from harbor.extensions.rsi.provenance import code_identity, digest_json, write_json
from harbor.extensions.rsi.report import summarize
from harbor.job import Job
from harbor.models.job.config import JobConfig
from harbor.models.task.config import NetworkMode
from harbor.models.task.task import Task
from harbor.models.trial.config import EnvironmentConfig, TrialConfig, VerifierConfig
from harbor.publisher.packager import Packager
from harbor.trial.hooks import TrialEvent, TrialHookEvent
from harbor.trial.trial import Trial
from harbor.utils.env import is_env_template, is_sensitive_env_key, resolve_env_vars
from harbor.verifier.verifier import Verifier

Record = dict[str, Any]

CATEGORIES = {"runtime", "network", "assets", "verifier", "agent"}


class Check(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(pattern=r"^[a-zA-Z0-9_-]+$")
    category: Literal["runtime", "network", "assets", "verifier", "agent"]
    phase: Literal["agent", "verifier"] = "agent"
    command: str = Field(min_length=1)
    timeout_sec: float = Field(gt=0, le=1800)
    network: bool = False


class Coverage(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: str = Field(min_length=8)
    checks: list[str] = Field(default_factory=list)
    not_required: bool = False

    @model_validator(mode="after")
    def explicit_scope(self):
        if bool(self.checks) == self.not_required:
            raise ValueError("Specify checks OR a justified not_required")
        return self


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid")
    basis: str = Field(min_length=8)
    coverage: dict[str, Coverage]
    checks: list[Check] = Field(default_factory=list)
    inputs: list[Path] = Field(default_factory=list)

    @model_validator(mode="after")
    def references(self):
        if set(self.coverage) != CATEGORIES:
            raise ValueError("Review runtime/network/assets/verifier/agent explicitly")
        by_id = {check.id: check for check in self.checks}
        if len(by_id) != len(self.checks):
            raise ValueError("Duplicate check id")
        for category, coverage in self.coverage.items():
            if any(
                i not in by_id or by_id[i].category != category for i in coverage.checks
            ):
                raise ValueError("Coverage must reference checks in its own category")
        return self


def read(path: Path) -> Any:
    return json.loads(path.read_text())


def execution_dump(model: JobConfig | TrialConfig) -> Record:
    # Native redacted dumps are display artifacts, not replay configuration.
    # In particular GIT_CONFIG_KEY_0 is public configuration, not a credential.
    data = model.model_dump(mode="json", context={"redact_sensitive_env": False})
    # EnvironmentConfig/VerifierConfig in this Harbor release do not honor the
    # serializer context. Restore these already-validated mappings explicitly.
    data["environment"]["env"] = dict(model.environment.env)
    data["verifier"]["env"] = dict(model.verifier.env)
    if isinstance(model, TrialConfig):
        data["agent"]["env"] = dict(model.agent.env)
    else:
        for original, serialized in zip(model.agents, data["agents"], strict=True):
            serialized["env"] = dict(original.env)
    return data


def check_env_references(trials: list[TrialConfig]) -> None:
    secret_key = re.compile(
        r"(?:^|_)(?:API_KEY|ACCESS_KEY_ID|TOKEN|SECRET|PASSWORD|CREDENTIALS?|AUTH)(?:$|_)|_KEY$",
        re.I,
    )
    for trial in trials:
        for mapping in (
            trial.environment.env,
            trial.agent.env,
            trial.verifier.env,
            trial.agent.kwargs.get("install_env", {}),
        ):
            for key, value in mapping.items():
                if secret_key.search(key) and not is_env_template(value):
                    raise ValueError(
                        f"Sensitive environment {key} must use an inherited variable reference"
                    )
                if re.search(r"https?://[^/\s]+@", value):
                    raise ValueError(
                        f"Credential-bearing environment {key} must use an inherited variable reference"
                    )


def file_sha(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def scrub(value: Any) -> Any:
    """Persist no inherited secrets, URL userinfo or signed download queries."""
    if isinstance(value, dict):
        return {
            k: "<redacted>" if is_sensitive_env_key(k) else scrub(v)
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [scrub(v) for v in value]
    if isinstance(value, str):
        for key, secret in os.environ.items():
            if is_sensitive_env_key(key) and len(secret) >= 8:
                value = value.replace(secret, "<redacted>")
        value = re.sub(r"(https?://)[^/\s@]+@", r"\1<redacted>@", value)
        value = re.sub(
            r"(?im)((?:proxy-)?authorization:)[^\r\n]+", r"\1 <redacted>", value
        )
        return re.sub(r"(https?://[^\s?'\"]+)\?[^\s'\"]+", r"\1?<redacted>", value)
    return value


def apply_profiles(trials: list[TrialConfig], profiles: Record) -> None:
    """Same replacement semantics as the teacher campaign, before any checks."""
    names = {Task(t.task.get_local_path()).name for t in trials}
    if profiles and set(profiles) != names:
        raise ValueError("Profiles must cover exactly the selected task set")
    for trial in trials:
        profile = profiles.get(Task(trial.task.get_local_path()).name)
        if profile is not None:
            if set(profile) - {
                "environment",
                "verifier",
                "agent_env",
                "agent_timeout_sec",
            }:
                raise ValueError("Unsupported task profile fields")
            timeout = profile.get("agent_timeout_sec")
            if "agent_timeout_sec" in profile and (
                type(timeout) not in (int, float)
                or not math.isfinite(timeout)
                or timeout <= 0
            ):
                raise ValueError("agent_timeout_sec must be finite and positive")
            trial.environment = EnvironmentConfig.model_validate(profile["environment"])
            trial.verifier = VerifierConfig.model_validate(profile["verifier"])
            trial.agent = trial.agent.model_copy(deep=True)
            trial.agent.env.update(profile["agent_env"])
            if "agent_timeout_sec" in profile:
                trial.agent.override_timeout_sec = float(timeout)


def compose_variables(text: str) -> set[str]:
    # Compose accepts $NAME and ${NAME}; $$ escapes interpolation.
    return {
        a or b
        for a, b in re.findall(
            r"\$\{([A-Za-z_][A-Za-z_0-9]*)[^}]*\}|\$([A-Za-z_][A-Za-z_0-9]*)",
            text.replace("$$", ""),
        )
    }


def compose_input_files(path: Path) -> list[Path]:
    # BaseLoader inspects structure without executing YAML tags (including !reset).
    document = yaml.load(path.read_text(), Loader=yaml.BaseLoader) or {}
    sources = []
    if document.get("include") or any(
        v.get("extends") for v in document.get("services", {}).values()
    ):
        raise ValueError("Campaign freeze requires flattened Compose include/extends")
    for service in document.get("services", {}).values():
        entries = service.get("env_file", [])
        if isinstance(entries, (str, dict)):
            entries = [entries]
        sources.extend(e["path"] if isinstance(e, dict) else e for e in entries)
    for kind in ("configs", "secrets"):
        sources.extend(
            v["file"] for v in document.get(kind, {}).values() if v.get("file")
        )
    if any("$" in source for source in sources):
        raise ValueError("Use literal paths for frozen Compose input files")
    return [(path.parent / source).resolve() for source in sources]


def identity(trials: list[Record], contracts: Record) -> Record:
    """Hash execution inputs, including overlays, wheels and declared cache manifests."""
    files: dict[str, str] = {}
    tasks = {}
    providers = {}
    compose_vars = {
        "DOCKER_HOST",
        "DOCKER_CONTEXT",
        "DOCKER_TLS_VERIFY",
        "DOCKER_CERT_PATH",
    }
    for raw in trials:
        trial = TrialConfig.model_validate(raw)
        task_path = trial.task.get_local_path()
        task = Task(task_path)
        for mapping in (
            trial.environment.env,
            trial.agent.env,
            trial.agent.kwargs.get("install_env", {}),
            trial.verifier.env,
            task.config.environment.env,
            task.config.verifier.env,
        ):
            for key, value in mapping.items():
                compose_vars.update(re.findall(r"\$\{([A-Za-z_][A-Za-z_0-9]*)", value))
        provider = trial.environment.import_path
        if provider and provider not in providers and supported(trial):
            module = importlib.import_module(provider.split(":")[0])
            if module.__file__ is None:
                raise ValueError("Provider must expose source provenance")
            root = Path(module.__file__).parent
            providers[provider] = digest_json(
                {
                    str(p.relative_to(root)): file_sha(p)
                    for p in sorted(root.rglob("*.py"))
                }
            )
        tasks[str(task_path)] = Packager.compute_content_hash(task_path)[0]
        paths = list(trial.environment.extra_docker_compose)
        paths += [
            Path(p)
            for p in trial.agent.kwargs.values()
            if isinstance(p, str) and Path(p).is_absolute() and Path(p).is_file()
        ]
        paths += trial.extra_instruction_paths
        contract = contracts.get(Task(task_path).name)
        if contract:
            paths += Contract.model_validate(contract).inputs
        compose_paths = [
            *trial.environment.extra_docker_compose,
            *(task_path / "environment").glob("*compose*.y*ml"),
        ]
        for compose_path in compose_paths:
            paths += compose_input_files(Path(compose_path))
        for path in paths:
            path = Path(path)
            if not path.is_file():
                raise ValueError(
                    f"Input must be an existing file (declare a manifest for directories): {path}"
                )
            files[str(path)] = file_sha(path)
            if path in trial.environment.extra_docker_compose:
                compose_vars.update(compose_variables(path.read_text()))
        for path in (task_path / "environment").glob("*compose*.y*ml"):
            compose_vars.update(compose_variables(path.read_text()))
    artifacts = {}
    for distribution in ("harbor", "harbor-remote-docker"):
        try:
            dist = importlib.metadata.distribution(distribution)
            provenance = json.loads(dist.read_text("direct_url.json") or "{}")
            artifacts[distribution] = {
                "version": dist.version,
                "wheel_sha256": provenance.get("archive_info", {})
                .get("hashes", {})
                .get("sha256"),
            }
        except importlib.metadata.PackageNotFoundError:
            artifacts[distribution] = None
    return {
        "tasks": tasks,
        "files": files,
        "trials_sha256": digest_json(trials),
        "contracts_sha256": digest_json(contracts),
        "code": code_identity(),
        "providers": providers,
        "installed_artifacts": artifacts,
        "compose_environment_sha256": digest_json(
            {k: os.environ.get(k) for k in sorted(compose_vars)}
        ),
    }


async def command(argv: list[str]) -> str:
    process = await asyncio.create_subprocess_exec(
        *argv, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    try:
        stdout, stderr = await asyncio.wait_for(process.communicate(), 45)
    except TimeoutError:
        process.kill()
        await process.wait()
        raise
    if process.returncode:
        raise RuntimeError(scrub(stderr.decode(errors="replace")[-2000:]))
    return stdout.decode()


async def docker(env, *args: str):
    argv = env._docker(*args) if hasattr(env, "_docker") else env._engine_cmd(*args)
    return await command(argv)


async def compose(env, args):
    if hasattr(env, "_compose"):
        return await env._compose(args)
    return await env._run_docker_compose_command(args, timeout_sec=45)


async def attestation(env) -> Record:
    rendered = (
        read(env._remote_compose)
        if getattr(env, "_remote_compose", None)
        else json.loads((await compose(env, ["config", "--format", "json"])).stdout)
    )
    services = {}
    for name in rendered["services"]:
        cid = (await compose(env, ["ps", "-q", name])).stdout.strip()
        if not cid:
            raise RuntimeError(f"Service did not start: {name}")
        detail = json.loads(await docker(env, "inspect", cid))[0]
        image = json.loads(await docker(env, "image", "inspect", detail["Image"]))[0]
        services[name] = {
            "image_id": detail["Image"],
            "repo_digests": image.get("RepoDigests", []),
            "resources": {
                k: detail["HostConfig"].get(k)
                for k in ("NanoCpus", "Memory", "StorageOpt")
            },
            "mounts": [
                {k: m.get(k) for k in ("Destination", "RW", "Type")}
                for m in detail.get("Mounts", [])
            ],
        }
    canonical = json.loads(json.dumps(rendered))
    for name, service in canonical["services"].items():
        service["image"] = services[name]["image_id"]
        service["pull_policy"] = "never"
        service.pop("build", None)
    semantic = json.dumps(canonical, sort_keys=True)
    replacements = {
        str(env.trial_paths.trial_dir): "<trial-output>",
        env.session_id: "<session>",
        rendered["name"]: "<project>",
    }
    for attr in ("workspace", "project", "identity"):
        if getattr(env, attr, None):
            replacements[str(getattr(env, attr))] = f"<{attr}>"
    for old, new in sorted(replacements.items(), key=lambda pair: -len(pair[0])):
        semantic = semantic.replace(old, new)
    return {
        "daemon_id": (await docker(env, "info", "--format", "{{.ID}}")).strip(),
        "services": services,
        "compose": scrub(rendered),
        "compose_raw_sha256": digest_json(rendered),
        "compose_effective_sha256": hashlib.sha256(semantic.encode()).hexdigest(),
    }


def supported(config: TrialConfig) -> bool:
    return (
        config.environment.import_path == "harbor_remote_docker:RemoteDockerEnvironment"
        or (
            config.environment.import_path is None
            and config.environment.type == "docker"
        )
    )


def status(checks: list[Record]) -> str:
    if any(c["status"] == "BLOCKED" for c in checks):
        return "BLOCKED"
    return (
        "UNVERIFIED"
        if not checks or any(c["status"] == "UNVERIFIED" for c in checks)
        else "READY"
    )


async def execute(env, check: Check, phase_env: Record) -> Record:
    started = time.time()
    try:
        result = await env.exec(
            check.command,
            env=resolve_env_vars(phase_env),
            timeout_sec=check.timeout_sec,
        )
        return {
            "id": check.id,
            "started_at": started,
            "category": check.category,
            "phase": check.phase,
            "status": "READY" if result.return_code == 0 else "BLOCKED",
            "exit_code": result.return_code,
            "seconds": time.time() - started,
            "stdout": scrub(result.stdout),
            "stderr": scrub(result.stderr),
        }
    except Exception as error:
        return {
            "id": check.id,
            "started_at": started,
            "category": check.category,
            "phase": check.phase,
            "status": "BLOCKED",
            "seconds": time.time() - started,
            "error": scrub(str(error)),
            "error_type": type(error).__name__,
        }


async def inspect_task(
    raw: Record,
    contract_data: Record | None,
    directory: Path,
    *,
    prepare: bool,
    skip_agent: bool = False,
) -> Record:
    cfg = TrialConfig.model_validate(raw)
    name = Task(cfg.task.get_local_path()).name
    row: Record = {
        "task": name,
        "checks": [],
        "agent_run_called": False,
        "started_at": time.time(),
    }
    if not supported(cfg):
        return {
            **row,
            "status": "UNVERIFIED",
            "reason": "Only Docker/Remote Docker validated by this gate",
        }
    if (
        cfg.environment.override_gpus
        or Task(cfg.task.get_local_path()).config.environment.gpus
    ):
        return {
            **row,
            "status": "UNVERIFIED",
            "reason": "This CPU-only validation does not allocate GPUs",
        }
    trial = None
    try:
        cfg.trials_dir = directory
        cfg.trial_name = cfg.generate_trial_name()
        trial = await Trial.create(cfg)
        row["evidence_path"] = str(trial.paths.trial_dir)
        env = trial.agent_environment
        await asyncio.wait_for(
            env.start(force_build=cfg.environment.force_build),
            trial._environment_build_timeout_sec,
        )
        row["attestation"] = await attestation(env)
        row["checks"].append({"id": "container-start", "status": "READY"})
        if prepare:
            row["status"] = "PREPARED"
            return row
        main = row["attestation"]["services"]["main"]["resources"]
        expected_cpu = (
            cfg.environment.override_cpus or trial.task.config.environment.cpus
        )
        expected_memory = (
            cfg.environment.override_memory_mb
            or trial.task.config.environment.memory_mb
        )
        resources_ok = (
            expected_cpu is None or main["NanoCpus"] == expected_cpu * 10**9
        ) and (expected_memory is None or main["Memory"] == expected_memory * 1024**2)
        row["checks"].append(
            {
                "id": "cpu-memory",
                "status": "READY" if resources_ok else "BLOCKED",
                "actual": main,
            }
        )
        row["checks"].append(
            await execute(
                env,
                Check(
                    id="workspace",
                    category="runtime",
                    command="pwd -P; test -d . && test -w . && test -d /logs/agent && command -v sh",
                    timeout_sec=15,
                ),
                {},
            )
        )
        storage_mb = (
            cfg.environment.override_storage_mb
            or trial.task.config.environment.storage_mb
        )
        storage_probe = (
            "harbor_storage_probe=$(df -Pk .) || exit $?; "
            f"printf '%s\\n' \"$harbor_storage_probe\" | awk 'NR==2 {{print; if ($4 < {storage_mb * 1024}) exit 1}}'"
            if storage_mb is not None
            else "df -Pk ."
        )
        row["checks"].append(
            await execute(
                env,
                Check(
                    id="storage-capacity",
                    category="runtime",
                    command=storage_probe,
                    timeout_sec=15,
                ),
                {},
            )
        )
        row["storage_scope"] = (
            "Available capacity checked; no claim that Docker enforces a per-container disk quota"
        )
        contract = Contract.model_validate(contract_data) if contract_data else None
        if contract is None:
            row["checks"].append(
                {
                    "id": "declared-contract",
                    "status": "UNVERIFIED",
                    "reason": "Task dependency/network/assets/verifier contract has not been reviewed",
                }
            )
        plan = trial._network_plan()
        if plan.verifier_env_baseline is not None or trial.task.has_steps:
            row["checks"].append(
                {
                    "id": "workload-shape",
                    "status": "UNVERIFIED",
                    "reason": "Separate verifier/multistep requires its own native validation fixture",
                }
            )
        if skip_agent:
            row["checks"].append(
                {
                    "id": "agent-setup",
                    "status": "UNVERIFIED",
                    "reason": "Explicit audit-only --skip-agent-setup; never eligible for freeze",
                }
            )
        else:
            try:
                with env.scoped_exec_env(trial.agent.extra_env):
                    await asyncio.wait_for(
                        trial.agent.setup(env),
                        trial._agent_setup_timeout_sec,
                    )
                row["checks"].append({"id": "agent-setup", "status": "READY"})
            except Exception as error:
                row["checks"].append(
                    {
                        "id": "agent-setup",
                        "status": "BLOCKED",
                        "error": scrub(str(error)),
                    }
                )

        for phase, policy in (
            ("agent", plan.agent_phase),
            ("verifier", plan.verifier_phase),
        ):
            phase_env = (
                trial.agent.extra_env
                if phase == "agent"
                else {**trial.task.config.verifier.env, **cfg.verifier.env}
            )
            if phase == "verifier" and plan.verifier_env_baseline is not None:
                continue
            async with trial._phase_network_policy(
                env, baseline_policy=plan.agent_env_baseline, phase_policy=policy
            ):
                if phase == "verifier" and not trial.task.has_steps:
                    verifier = Verifier(trial.task, trial.paths, env)
                    sources, _, _ = verifier._resolve_tests()
                    for source in sources:
                        trial.task.paths.validate_input_tree(source)
                        await env.upload_dir(source, "/tests")
                    row["checks"].append(
                        await execute(
                            env,
                            Check(
                                id="verifier-script",
                                category="verifier",
                                phase="verifier",
                                command="test -r /tests/test.sh && bash -n /tests/test.sh",
                                timeout_sec=15,
                            ),
                            phase_env,
                        )
                    )
                if contract:
                    for check in contract.checks:
                        if check.phase != phase:
                            continue
                        if skip_agent and check.category == "agent":
                            row["checks"].append(
                                {
                                    "id": check.id,
                                    "status": "UNVERIFIED",
                                    "reason": "Agent setup explicitly skipped; dependent tool check not executed",
                                }
                            )
                            continue
                        if (
                            check.network
                            and policy.network_mode == NetworkMode.NO_NETWORK
                        ):
                            row["checks"].append(
                                {
                                    "id": check.id,
                                    "status": "BLOCKED",
                                    "reason": "Network probe conflicts with NO_NETWORK; not executed",
                                }
                            )
                            continue
                        row["checks"].append(await execute(env, check, phase_env))
        row["status"] = status(row["checks"])
    except Exception as error:
        row["checks"].append(
            {
                "id": "environment",
                "status": "BLOCKED",
                "error_type": type(error).__name__,
                "error": scrub(str(error)),
            }
        )
        row["status"] = "BLOCKED"
    finally:
        if trial is not None:
            try:
                # Native Docker delete=True invokes compose --rmi local. Prepared
                # images must survive validation; Remote Docker already retains images.
                await trial.agent_environment.stop(
                    delete=cfg.environment.import_path is not None
                )
                if cfg.environment.import_path is None and row.get("attestation"):
                    project = row["attestation"]["compose"]["name"]
                    remaining = await docker(
                        trial.agent_environment,
                        "ps",
                        "-aq",
                        "--filter",
                        f"label=com.docker.compose.project={project}",
                    )
                    if remaining.strip():
                        raise RuntimeError(
                            "Native Docker cleanup left owned containers"
                        )
            except Exception as error:
                row["checks"].append(
                    {
                        "id": "cleanup",
                        "status": "BLOCKED",
                        "error_type": type(error).__name__,
                        "error": scrub(str(error)),
                    }
                )
                row["status"] = "BLOCKED"
            trial._close_logger_handler()
    return row


async def checked_map(items, operation):
    """At most two disposable CPU environments; no new scheduling semantics."""
    limit = asyncio.Semaphore(2)

    async def one(item):
        async with limit:
            row = await operation(item)
            print(
                json.dumps({"task": row["task"], "status": row["status"]}), flush=True
            )
            return row

    async with asyncio.TaskGroup() as group:
        tasks = [group.create_task(one(item)) for item in items]
    return [task.result() for task in tasks]


def trial_spec(raw: Record) -> Record:
    """Replay-affecting native fields, excluding generated output identities."""
    data = execution_dump(TrialConfig.model_validate(raw))
    return {
        k: v for k, v in data.items() if k not in {"trial_name", "trials_dir", "job_id"}
    }


def trial_groups(trials: list[Record]) -> list[list[int]]:
    """Validate each distinct task/agent/environment once, not every attempt."""
    groups: dict[str, list[int]] = {}
    for index, raw in enumerate(trials):
        groups.setdefault(digest_json(trial_spec(raw)), []).append(index)
    return list(groups.values())


async def prepare(
    config_path: Path, profiles_path: Path | None, contracts_path: Path, output: Path
) -> Record:
    config = JobConfig.model_validate(read(config_path))
    if config.install_only or config.is_regrade or config.n_attempts < 1:
        raise ValueError("Campaign requires ordinary tasks and at least one attempt")
    if config.verifier.disable:
        raise ValueError("Formal Campaign requires the official verifier")
    profiles = read(profiles_path) if profiles_path else {}
    contracts = read(contracts_path)
    for contract in contracts.values():
        Contract.model_validate(contract)
    output.mkdir(parents=True, exist_ok=False)
    config_for_plan = config.model_copy(
        update={"jobs_dir": output / "resolution", "job_name": "resolve"}, deep=True
    )
    job = await Job.create(config_for_plan)
    trials = job._remaining_trial_configs
    native = [execution_dump(t) for t in trials]
    check_env_references(trials)
    apply_profiles(trials, profiles)
    check_env_references(trials)
    for trial in trials:
        if trial.verifier.disable:
            raise ValueError("Formal Campaign requires the official verifier")
        if supported(trial) and trial.environment.import_path is None:
            trial.environment = trial.environment.model_copy(update={"delete": False})
    # Native Harbor resolves tasks, then multiplies agents and attempts. Keep
    # the task axis unique rather than multiplying it again when reconstructing.
    selected = job._task_configs
    names = [Task(t.get_local_path()).name for t in selected]
    if len(names) != len(set(names)) or set(contracts) - set(names):
        raise ValueError("Duplicate tasks or contracts outside selected task set")
    config.tasks = selected
    config.datasets = []
    groups = trial_groups([execution_dump(t) for t in trials])

    async def prepare_one(indices):
        row = await inspect_task(
            execution_dump(trials[indices[0]]), None, output / "prepare", prepare=True
        )
        row["trial_indices"] = indices
        return row

    rows = await checked_map(groups, prepare_one)
    for index, row in enumerate(rows):
        if row["status"] == "PREPARED":
            overlay = output / f"images-{index}.yaml"
            text = "services:\n"
            for service, detail in row["attestation"]["services"].items():
                text += f"  {service}:\n    image: {detail['image_id']}\n    pull_policy: never\n"
                if row["attestation"]["compose"]["services"][service].get("build"):
                    text += "    build: !reset null\n"
            overlay.write_text(text)
            for trial_index in row["trial_indices"]:
                trial = trials[trial_index]
                trial.environment = trial.environment.model_copy(deep=True)
                trial.environment.extra_docker_compose.append(overlay)
                trial.environment.force_build = False
    frozen = [execution_dump(t) for t in trials]
    write_json(output / "prepare-results.json", rows)
    manifest = {
        "schema": 2,
        "created_at": time.time(),
        "config": execution_dump(config),
        "native_trials": native,
        "trials": frozen,
        "profiles": profiles,
        "contracts": contracts,
        "preparation": rows,
        "n_tasks": len(selected),
        "n_trials": len(trials),
        "n_validation_groups": len(groups),
    }
    manifest["identity"] = prepared_identity(manifest)
    write_json(output / "prepared.json", manifest)
    return manifest


def prepared_identity(prepared: Record) -> Record:
    return {
        **identity(prepared["trials"], prepared["contracts"]),
        "native_plan_sha256": digest_json(
            {key: prepared[key] for key in ("config", "native_trials", "profiles")}
        ),
    }


def check_identity(prepared: Record) -> None:
    if prepared_identity(prepared) != prepared["identity"]:
        raise ValueError("Prepared inputs changed: repeat prepare/validate")


async def validate(
    prepared_path: Path,
    output: Path,
    *,
    skip_agent: bool = False,
    previous_path: Path | None = None,
) -> Record:
    prepared = read(prepared_path)
    check_identity(prepared)
    reusable = {}
    previous_sha = None
    if previous_path is not None:
        previous = read(previous_path)
        previous_sha = file_sha(previous_path)
        if (
            previous["prepared_sha256"] != file_sha(prepared_path)
            or previous["identity"] != prepared["identity"]
            or [r["trial_indices"] for r in previous["tasks"]]
            != trial_groups(prepared["trials"])
        ):
            raise ValueError("Previous validation belongs to a different native plan")
        reusable = {
            tuple(row["trial_indices"]): row
            for row in previous["tasks"]
            if row["status"] == "READY" and status(row["checks"]) == "READY"
        }
    output.mkdir(parents=True, exist_ok=False)

    async def validate_one(item):
        before = item
        indices = before["trial_indices"]
        if tuple(indices) in reusable:
            # Keep original check timestamps: reuse cannot renew readiness TTL.
            return {
                **reusable[tuple(indices)],
                "reused_from": str(previous_path),
                "reused_report_sha256": previous_sha,
            }
        raw = prepared["trials"][indices[0]]
        name = Task(TrialConfig.model_validate(raw).task.get_local_path()).name
        if before["status"] != "PREPARED":
            row = {
                "task": name,
                "status": before["status"],
                "checks": before["checks"],
                "reason": "Preparation not successful",
            }
        else:
            row = await inspect_task(
                raw,
                prepared["contracts"].get(name),
                output / "trials",
                prepare=False,
                skip_agent=skip_agent,
            )
            if row.get("attestation"):
                for key in ("daemon_id", "services", "compose_effective_sha256"):
                    if row["attestation"][key] != before["attestation"][key]:
                        row["checks"].append(
                            {
                                "id": "prepared-runtime-identity",
                                "status": "BLOCKED",
                                "reason": f"Changed {key}",
                            }
                        )
                        row["status"] = "BLOCKED"
        row["trial_indices"] = indices
        return row

    rows = await checked_map(prepared["preparation"], validate_one)
    write_json(output / "results.json", rows)
    report = {
        "schema": 2,
        "n_tasks": prepared["n_tasks"],
        "n_trials": len(prepared["trials"]),
        "n_validation_groups": len(rows),
        "validated_at": min(r.get("started_at", time.time()) for r in rows),
        "finished_at": time.time(),
        "prepared_path": str(prepared_path),
        "prepared_sha256": file_sha(prepared_path),
        "identity": prepared["identity"],
        "tasks": rows,
        "counts": Record(Counter(r["status"] for r in rows)),
        "contract_coverage": {
            "reviewed": len(prepared["contracts"]),
            "total": prepared["n_tasks"],
        },
        "agent_run_called": False,
    }
    check_identity(prepared)
    write_json(output / "validation.json", report)
    return report


def require_ready(prepared: Record, report: Record) -> None:
    expected = trial_groups(prepared["trials"])
    rows = report["tasks"]
    if not expected or [r.get("trial_indices") for r in rows] != expected:
        raise ValueError(
            "Validation must cover every planned task/agent/attempt exactly once"
        )
    for row, indices in zip(rows, expected, strict=True):
        cfg = TrialConfig.model_validate(prepared["trials"][indices[0]])
        if row["task"] != Task(cfg.task.get_local_path()).name:
            raise ValueError("Validation task identity changed")
        if row["status"] != "READY" or status(row["checks"]) != "READY":
            raise ValueError("BLOCKED/UNVERIFIED tasks: formal dispatch prohibited")


def freeze(validation_path: Path, output: Path, valid_for_sec: float) -> Record:
    if not 0 < valid_for_sec <= 86400:
        raise ValueError("Readiness validity must be within (0, 86400]")
    report = read(validation_path)
    prepared_path = Path(report["prepared_path"])
    prepared = read(prepared_path)
    if file_sha(prepared_path) != report["prepared_sha256"]:
        raise ValueError("Prepared manifest changed")
    check_identity(prepared)
    require_ready(prepared, report)
    artifacts = prepared["identity"].get("installed_artifacts", {})
    required = ["harbor"]
    if prepared["identity"].get("providers"):
        required.append("harbor-remote-docker")
    if any(not (artifacts.get(name) or {}).get("wheel_sha256") for name in required):
        raise ValueError(
            "Installed wheel origin SHA is UNVERIFIED; install explicit local wheels"
        )
    lock = {
        "schema": 2,
        "prepared": prepared,
        "validation": report,
        "expires_at": report["validated_at"] + valid_for_sec,
    }
    if output.exists():
        raise FileExistsError(output)
    write_json(output, lock)
    return lock


async def run(lock_path: Path) -> Any:
    lock = read(lock_path)
    prepared, report = lock["prepared"], lock["validation"]
    if time.time() > lock["expires_at"]:
        raise ValueError("Readiness expired; repeat validation")
    require_ready(prepared, report)
    check_identity(prepared)
    # Replacing the daemon behind an unchanged endpoint must invalidate readiness.
    seen = set()
    for row in report["tasks"]:
        cfg = TrialConfig.model_validate(prepared["trials"][row["trial_indices"][0]])
        kwargs = cfg.environment.kwargs
        prefix = ["docker"]
        if kwargs.get("endpoint"):
            prefix += ["--host", kwargs["endpoint"]]
        elif kwargs.get("docker_context"):
            prefix += ["--context", kwargs["docker_context"]]
        key = tuple(prefix)
        if key not in seen:
            daemon = await command([*prefix, "info", "--format", "{{.ID}}"])
            if daemon.strip() != row["attestation"]["daemon_id"]:
                raise ValueError(
                    "Docker daemon changed or unavailable; repeat validation"
                )
            seen.add(key)
        images = [
            service["image_id"] for service in row["attestation"]["services"].values()
        ]
        await command([*prefix, "image", "inspect", "--format", "{{.Id}}", *images])
    config = JobConfig.model_validate(prepared["config"])
    if (config.jobs_dir / config.job_name).exists():
        raise FileExistsError("Refusing existing formal Job")
    # Claim before creating a Job; a failed launch is never silently retried.
    with lock_path.with_suffix(".dispatch.json").open("x") as stream:
        json.dump(
            {
                "time": time.time(),
                "lock_sha256": file_sha(lock_path),
                "process": process_identity(os.getpid()),
            },
            stream,
        )
    job = await Job.create(config)
    actual = job._remaining_trial_configs
    if len(actual) != len(prepared["trials"]):
        raise ValueError("Native task resolution changed")
    for trial, raw, original in zip(
        actual, prepared["trials"], prepared["native_trials"], strict=True
    ):
        if trial_spec(execution_dump(trial)) != trial_spec(original):
            raise ValueError("Native task/agent/attempt configuration changed")
        frozen = TrialConfig.model_validate(raw)
        trial.trial_name = frozen.trial_name
        trial.environment = frozen.environment
        trial.verifier = frozen.verifier
        trial.agent = frozen.agent
    events_path = lock_path.with_suffix(".events.jsonl")
    with events_path.open("x") as events:

        async def observe(event: TrialHookEvent):
            # Public native hooks run after queue permit acquisition. This is
            # an observation journal, never an alternative lifecycle/queue.
            row = {
                "event": event.event.value,
                "timestamp": event.timestamp.isoformat(),
                "observed_at": time.time(),
                "trial_name": event.trial_name,
                "trial_id": str(event.trial_id),
                "task_name": event.task_name,
                "model_name": event.config.agent.model_name,
            }
            try:
                events.write(json.dumps(row) + "\n")
                events.flush()
            except OSError as error:
                logging.getLogger(__name__).error(
                    "Campaign event observation unavailable: %s", error
                )

        for event in TrialEvent:
            job.add_hook(event, observe)
        return await job.run()


def process_identity(pid: int) -> Record:
    """Local Linux identity; never mistake a recycled PID for this dispatcher."""
    return {
        "hostname": socket.gethostname(),
        "pid": pid,
        "boot_id": Path("/proc/sys/kernel/random/boot_id").read_text().strip(),
        "start_ticks": Path(f"/proc/{pid}/stat")
        .read_text()
        .rsplit(")", 1)[1]
        .split()[19],
    }


def campaign_status(lock_path: Path) -> Record:
    """Read-only progress; no model, Docker query or inference of missing rewards."""
    lock = read(lock_path)
    prepared = lock["prepared"]
    config = JobConfig.model_validate(prepared["config"])
    result = summarize(config.jobs_dir / config.job_name, prepared["trials"])
    claim_path = lock_path.with_suffix(".dispatch.json")
    process_state = "not_dispatched"
    if claim_path.exists():
        owner = read(claim_path)["process"]
        process_state = "UNKNOWN_other_host"
        if owner["hostname"] == socket.gethostname():
            try:
                process_state = (
                    "running"
                    if process_identity(owner["pid"]) == owner
                    else "not_running"
                )
            except FileNotFoundError:
                process_state = "not_running"
            except OSError:
                process_state = "UNKNOWN_process_access"
    events_path = lock_path.with_suffix(".events.jsonl")
    phases, active = {}, {}
    event_error = None
    planned_names = {t["trial_name"] for t in prepared["trials"]}
    if events_path.exists():
        try:
            for line in events_path.read_text().splitlines():
                event = json.loads(line)
                name = event["trial_name"]
                if name not in planned_names:
                    raise ValueError("Unexpected native event identity")
                TrialEvent(event["event"])
                phases[name] = event
                if event["event"] == "agent-start":
                    active[name] = event
                elif event["event"] in ("agent-end", "end"):
                    active.pop(name, None)
        except (OSError, ValueError, KeyError, TypeError) as error:
            event_error = type(error).__name__
    else:
        event_error = "native_event_journal_unavailable"
    return {
        **result,
        "dispatch_process_state": process_state,
        "native_event_observation": {
            "error": event_error,
            "agent_phase_active": len(active) if event_error is None else None,
            "agent_phase_trials": list(active.values())
            if event_error is None
            else None,
            "latest_trial_events": list(phases.values())
            if event_error is None
            else None,
            "model_generation_count_not_inferred": True,
        },
        "lock_sha256": file_sha(lock_path),
    }


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    p = sub.add_parser("prepare")
    p.add_argument("--config", type=Path, required=True)
    p.add_argument("--profiles", type=Path)
    p.add_argument("--contracts", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p = sub.add_parser("validate")
    p.add_argument("--prepared", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--skip-agent-setup", action="store_true")
    p.add_argument("--previous", type=Path)
    p = sub.add_parser("freeze")
    p.add_argument("--validation", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--valid-for-sec", type=float, default=3600)
    p = sub.add_parser("run")
    p.add_argument("--lock", type=Path, required=True)
    p = sub.add_parser("status")
    p.add_argument("--lock", type=Path, required=True)
    p.add_argument("--output", type=Path)
    p = sub.add_parser("recover")
    p.add_argument("--lock", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    os.umask(0o077)
    if args.action == "prepare":
        result = asyncio.run(
            prepare(
                args.config.resolve(),
                args.profiles.resolve() if args.profiles else None,
                args.contracts.resolve(),
                args.output.resolve(),
            )
        )
        failed = any(r["status"] != "PREPARED" for r in result["preparation"])
    elif args.action == "validate":
        result = asyncio.run(
            validate(
                args.prepared.resolve(),
                args.output.resolve(),
                skip_agent=args.skip_agent_setup,
                previous_path=args.previous.resolve() if args.previous else None,
            )
        )
        failed = any(r["status"] != "READY" for r in result["tasks"])
    elif args.action == "freeze":
        if not 0 < args.valid_for_sec <= 86400:
            parser.error("valid-for-sec must be within (0, 86400]")
        freeze(args.validation.resolve(), args.output.resolve(), args.valid_for_sec)
        failed = False
    elif args.action == "run":
        asyncio.run(run(args.lock.resolve()))
        failed = False
    elif args.action == "status":
        result = campaign_status(args.lock.resolve())
        if args.output:
            write_json(args.output.resolve(), result)
        print(json.dumps(result))
        failed = False
    else:
        from harbor.extensions.rsi.recovery import plan

        result = plan(args.lock.absolute(), args.output.absolute())
        print(json.dumps(result))
        failed = False
    sys.exit(2 if failed else 0)


if __name__ == "__main__":
    main()
