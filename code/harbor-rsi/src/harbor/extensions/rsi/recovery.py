"""Plan new native Jobs for proven never-created Trials; never resume execution."""

from __future__ import annotations

import errno
import socket
from collections import defaultdict
from copy import deepcopy
from pathlib import Path
from typing import Any
from uuid import UUID

from harbor.extensions.rsi import readiness
from harbor.extensions.rsi.provenance import digest_json, write_json
from harbor.extensions.rsi.report import summarize
from harbor.models.job.config import JobConfig
from harbor.models.task.task import Task
from harbor.models.trial.config import AgentConfig, TrialConfig
from harbor.models.trial.result import TrialResult

Record = dict[str, Any]


def _name(value: Any) -> str:
    if (
        not isinstance(value, str)
        or value in ("", ".", "..")
        or Path(value).name != value
        or any(character in value for character in "\\\r\n\0")
    ):
        raise ValueError("Invalid native Job or Trial directory identity")
    return value


def _retired_dispatch(source: Path) -> tuple[Record, Path]:
    claim_path = source.with_suffix(".dispatch.json")
    if claim_path.is_symlink():
        raise ValueError("Dispatcher evidence must not be a symlink")
    claim = readiness.read(claim_path)
    if claim.get("lock_sha256") != readiness.file_sha(source):
        raise ValueError("Dispatcher claim does not match the source lock")
    owner = claim.get("process")
    fields = {"hostname", "pid", "boot_id", "start_ticks"}
    if (
        not isinstance(owner, dict)
        or set(owner) != fields
        or type(owner["pid"]) is not int
        or not 0 < owner["pid"] < 2**31
        or not isinstance(owner["start_ticks"], str)
        or not owner["start_ticks"].isdigit()
        or int(owner["start_ticks"]) <= 0
        or not isinstance(owner["boot_id"], str)
    ):
        raise ValueError("Missing or invalid dispatcher process identity")
    UUID(owner["boot_id"])
    if owner["hostname"] != socket.gethostname():
        raise ValueError("UNKNOWN dispatcher identity on another host")
    try:
        current = readiness.process_identity(owner["pid"])
    except FileNotFoundError as error:
        if (
            error.errno != errno.ENOENT
            or error.filename != f"/proc/{owner['pid']}/stat"
        ):
            raise ValueError("UNKNOWN dispatcher process access") from error
    except OSError as error:
        raise ValueError("UNKNOWN dispatcher process access") from error
    else:
        if current == owner:
            raise ValueError("Source dispatcher is still active")
        if (
            not isinstance(current, dict)
            or set(current) != fields
            or current["hostname"] != owner["hostname"]
            or current["pid"] != owner["pid"]
            or not isinstance(current["start_ticks"], str)
            or not current["start_ticks"].isdigit()
        ):
            raise ValueError("UNKNOWN dispatcher process identity")
        UUID(current["boot_id"])
    return claim, claim_path


def _terminal_ledger(job_dir: Path, prepared: Record) -> tuple[list[Record], list[int]]:
    frozen = prepared["trials"]
    names = [_name(raw.get("trial_name")) for raw in frozen]
    if len(names) != len(set(names)):
        raise ValueError("Duplicate frozen Trial names")
    if job_dir.is_symlink():
        raise ValueError("Source Job must not be a symlink")
    if job_dir.exists():
        for path in job_dir.iterdir():
            if path.is_symlink() or (path.is_dir() and path.name not in names):
                raise ValueError("Unexpected source Job directory or symlink")
    report = summarize(job_dir, frozen)
    if not report["identity_integrity_passed"]:
        raise ValueError("Source native Result identity is invalid")
    ledger, pending = [], []
    required = {
        "finished_at",
        "failure_phase",
        "infrastructure_errors",
        "secondary_errors",
    }
    for index, (raw, row) in enumerate(zip(frozen, report["trials"], strict=True)):
        directory = job_dir / names[index]
        if not directory.exists():
            pending.append(index)
            ledger.append(
                {
                    "source_plan_index": index,
                    "trial_name": names[index],
                    "state": "never_created",
                }
            )
            continue
        path = directory / "result.json"
        if (
            not directory.is_dir()
            or any(
                (directory / name).is_symlink()
                for name in ("config.json", "lock.json", "result.json")
            )
            or not path.is_file()
        ):
            raise ValueError(f"BLOCKED incomplete Trial directory: {names[index]}")
        result_raw = readiness.read(path)
        result = TrialResult.model_validate(result_raw)
        planned = TrialConfig.model_validate(raw)
        task = Task(planned.task.get_local_path())
        if (
            not required.issubset(result_raw)
            or result.finished_at is None
            or row["state"] != "terminal"
            or result.task_name != task.name
            or result.task_id != planned.task.get_task_id()
            # Native Result uses Task.checksum (dirhash), not the Packager
            # digest independently checked by readiness.check_identity.
            or result.task_checksum != task.checksum
        ):
            raise ValueError(f"BLOCKED incomplete or invalid Trial: {names[index]}")
        if row.get("cleanup_unconfirmed") is not False:
            raise ValueError(f"BLOCKED unconfirmed cleanup: {names[index]}")
        ledger.append(
            {
                "source_plan_index": index,
                "trial_name": names[index],
                "state": "retained_terminal",
                "trial_id": str(result.id),
                "result_path": str(path),
                "result_sha256": readiness.file_sha(path),
                "finished_at": result_raw["finished_at"],
                "official_rewards": result_raw.get("verifier_result"),
                "scoring_status": row["scoring_status"],
            }
        )
    return ledger, pending


def _groups(prepared: Record, indices: list[int], source_sha: str) -> list[Record]:
    original = JobConfig.model_validate(prepared["config"])
    if (
        original.install_only
        or original.is_regrade
        or original.user_agent is not None
        or original.retry.max_retries != 0
    ):
        raise ValueError("Unsupported Campaign recovery configuration")
    profiles, contracts = prepared["profiles"], prepared["contracts"]
    agents: dict[str, Record] = {}
    remaining: dict[str, dict[str, list[int]]] = defaultdict(lambda: defaultdict(list))
    task_rows: dict[str, Record] = {}
    for index in indices:
        raw = prepared["trials"][index]
        trial = TrialConfig.model_validate(raw)
        name = Task(trial.task.get_local_path()).name
        if name not in contracts or (profiles and name not in profiles):
            raise ValueError("Incomplete frozen profiles or contracts")
        if name in task_rows and task_rows[name] != raw["task"]:
            raise ValueError("Unsupported multiple sources for one Task name")
        task_rows[name] = raw["task"]
        key = digest_json(raw["agent"])
        agents[key] = raw["agent"]
        remaining[key][name].append(index)
    groups = []
    for agent_key, tasks in remaining.items():
        counts: dict[int, list[str]] = defaultdict(list)
        for name, source_indices in tasks.items():
            counts[len(source_indices)].append(name)
        for attempts, names in counts.items():
            number = len(groups) + 1
            config = original.model_copy(deep=True)
            config.job_name = (
                f"{original.job_name}-unstarted-{source_sha[:12]}-{number}"
            )
            config.tasks = [
                TrialConfig.model_validate(prepared["trials"][tasks[name][0]]).task
                for name in names
            ]
            config.datasets = []
            config.agents = [AgentConfig.model_validate(agents[agent_key])]
            config.n_attempts = attempts
            config.retry.max_retries = 0
            destination = config.jobs_dir / config.job_name
            if destination.exists() or destination.is_symlink():
                raise FileExistsError("Continuation native Job already exists")
            groups.append(
                {
                    "directory": f"job-{number:03d}",
                    "config": readiness.execution_dump(config),
                    "profiles": {name: deepcopy(profiles[name]) for name in names}
                    if profiles
                    else {},
                    "contracts": {name: deepcopy(contracts[name]) for name in names},
                    "source_plan_indices": [
                        tasks[name][attempt]
                        for attempt in range(attempts)
                        for name in names
                    ],
                }
            )
    return groups


def plan(source_lock: Path, output: Path) -> Record:
    """Write only fresh config candidates; the normal four stages remain required."""
    source_lock = source_lock.absolute()
    output = output.absolute()
    if output.exists() or output.is_symlink():
        raise FileExistsError(output)
    if source_lock.is_symlink():
        raise ValueError("Source lock must not be a symlink")
    output = output.resolve()
    source_sha = readiness.file_sha(source_lock)
    lock = readiness.read(source_lock)
    prepared = lock["prepared"]
    if (
        lock.get("schema") != 2
        or prepared.get("schema") != 2
        or not isinstance(prepared.get("profiles"), dict)
        or not prepared.get("trials")
        or len(prepared.get("native_trials", [])) != len(prepared["trials"])
        or prepared.get("n_trials") != len(prepared["trials"])
    ):
        raise ValueError("Recovery requires the current process-bound Campaign schema")
    readiness.check_identity(prepared)
    readiness.require_ready(prepared, lock["validation"])
    claim, claim_path = _retired_dispatch(source_lock)
    config = JobConfig.model_validate(prepared["config"])
    _name(config.job_name)
    if not config.jobs_dir.is_absolute():
        raise ValueError("Source Job directory must be absolute")
    job_dir = config.jobs_dir / config.job_name
    protected = [
        job_dir.resolve(),
        *(
            t.task.get_local_path().resolve()
            for t in map(TrialConfig.model_validate, prepared["trials"])
        ),
    ]
    if any(output.is_relative_to(path) for path in protected):
        raise ValueError("Recovery output must be outside source Job and Task trees")
    ledger, pending = _terminal_ledger(job_dir, prepared)
    groups = _groups(prepared, pending, source_sha)
    source_files = {
        str(source_lock): source_sha,
        str(claim_path): readiness.file_sha(claim_path),
    }
    for path in (job_dir / "config.json", job_dir / "result.json"):
        if path.exists():
            source_files[str(path)] = readiness.file_sha(path)
    source_files.update(
        {
            row["result_path"]: row["result_sha256"]
            for row in ledger
            if "result_path" in row
        }
    )
    # Recheck before claiming an output directory. No source evidence is changed.
    _retired_dispatch(source_lock)
    if _terminal_ledger(job_dir, prepared) != (ledger, pending) or any(
        readiness.file_sha(Path(path)) != expected
        for path, expected in source_files.items()
    ):
        raise ValueError("Source evidence changed during recovery planning")
    output.mkdir(parents=True, mode=0o700, exist_ok=False)
    outputs = []
    for group in groups:
        directory = output / group["directory"]
        directory.mkdir(mode=0o700)
        for name in ("config", "profiles", "contracts"):
            write_json(directory / f"{name}.json", group[name])
        outputs.append(
            {
                "job_name": group["config"]["job_name"],
                "source_plan_indices": group["source_plan_indices"],
                "config_path": str(directory / "config.json"),
                "profiles_path": str(directory / "profiles.json"),
                "contracts_path": str(directory / "contracts.json"),
                "files_sha256": {
                    name: readiness.file_sha(directory / f"{name}.json")
                    for name in ("config", "profiles", "contracts")
                },
            }
        )
    result = {
        "kind": "native_campaign_unstarted_config_plan",
        "requires_fresh_prepare_validate_freeze": True,
        "source_lock": str(source_lock),
        "source_files_sha256": source_files,
        "retired_dispatcher": claim["process"],
        "source_trials": ledger,
        "n_source_trials": len(ledger),
        "n_never_created": len(pending),
        "n_retained_terminal": len(ledger) - len(pending),
        "jobs": outputs,
        "new_trial_identity_policy": "New native Job and Trial identities; source UUIDs are not reused.",
        "dispatch_performed": False,
    }
    write_json(output / "plan.json", result)
    return result
