"""Recovery plans are pure config candidates and never replay started Trials."""

import errno
import socket
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest

from harbor.extensions.rsi import readiness, recovery
from harbor.models.job.config import JobConfig, RetryConfig
from harbor.models.task.task import Task
from harbor.models.trial.config import AgentConfig, TaskConfig, TrialConfig
from harbor.models.trial.result import AgentInfo, ModelInfo, TimingInfo, TrialResult
from harbor.models.verifier.result import VerifierResult


@pytest.fixture
def campaign(tmp_path, monkeypatch):
    monkeypatch.setattr(readiness, "code_identity", lambda: {"code": "cpu-fixture"})
    tasks = []
    for name in ("a", "b"):
        root = tmp_path / name
        (root / "environment").mkdir(parents=True)
        (root / "tests").mkdir()
        (root / "task.toml").write_text(f'[task]\nname="fixture/{name}"\n')
        (root / "instruction.md").write_text("CPU planning fixture; never execute.\n")
        (root / "environment/Dockerfile").write_text("FROM fixture:no-runtime\n")
        (root / "tests/test.sh").write_text("# CPU fixture only\n")
        tasks.append(TaskConfig(path=root))
    config = JobConfig(
        job_name="source",
        jobs_dir=tmp_path / "jobs",
        n_attempts=2,
        agents=[AgentConfig(name="nop", model_name=f"fixture/m{i}") for i in (0, 1)],
        tasks=tasks,
        retry=RetryConfig(max_retries=0),
    )
    native = [
        TrialConfig(
            task=task,
            agent=agent,
            environment=config.environment,
            verifier=config.verifier,
            trial_name=f"source-{attempt}-{index}-{model}",
            trials_dir=tmp_path / "resolution",
        )
        for attempt in range(2)
        for index, task in enumerate(config.tasks)
        for model, agent in enumerate(config.agents)
    ]
    profiles: dict[str, Any] = {
        f"fixture/{name}": {
            "environment": config.environment.model_dump(mode="json"),
            "verifier": config.verifier.model_dump(mode="json"),
            "agent_env": {"PUBLIC_PROFILE": "same"},
        }
        for name in ("a", "b")
    }
    contracts = {
        f"fixture/{name}": {
            "basis": "CPU fixture with no additional environment checks.",
            "coverage": {
                key: {"reason": "Not needed in CPU fixture.", "not_required": True}
                for key in readiness.CATEGORIES
            },
            "checks": [],
        }
        for name in ("a", "b")
    }
    original = [readiness.execution_dump(trial) for trial in native]
    readiness.apply_profiles(native, profiles)
    frozen = [readiness.execution_dump(trial) for trial in native]
    groups = readiness.trial_groups(frozen)
    prepared: dict[str, Any] = {
        "schema": 2,
        "config": readiness.execution_dump(config),
        "native_trials": original,
        "trials": frozen,
        "profiles": profiles,
        "contracts": contracts,
        "n_trials": len(frozen),
    }
    prepared["identity"] = readiness.prepared_identity(prepared)
    report = {
        "tasks": [
            {
                "task": f"fixture/{'a' if indices[0] < 2 else 'b'}",
                "trial_indices": indices,
                "status": "READY",
                "checks": [{"status": "READY"}],
            }
            for indices in groups
        ]
    }
    lock = tmp_path / "source.lock.json"
    readiness.write_json(
        lock, {"schema": 2, "prepared": prepared, "validation": report, "expires_at": 0}
    )  # Expired readiness is not reused.
    owner = {
        "hostname": socket.gethostname(),
        "pid": 1234,
        "boot_id": str(uuid4()),
        "start_ticks": "10",
    }
    claim = lock.with_suffix(".dispatch.json")
    readiness.write_json(
        claim, {"lock_sha256": readiness.file_sha(lock), "process": owner}
    )
    monkeypatch.setattr(
        readiness, "process_identity", lambda pid: {**owner, "start_ticks": "11"}
    )
    job_dir = config.jobs_dir / config.job_name
    job_dir.mkdir(parents=True)
    job_id = uuid4()
    readiness.write_json(job_dir / "config.json", readiness.execution_dump(config))
    readiness.write_json(
        job_dir / "result.json", {"id": str(job_id), "finished_at": None}
    )

    def finish(index, reward=0.0):
        trial = TrialConfig.model_validate(frozen[index]).model_copy(
            update={"trials_dir": job_dir, "job_id": job_id}, deep=True
        )
        assert trial.task.path is not None
        assert trial.agent.model_name is not None
        directory = job_dir / trial.trial_name
        directory.mkdir()
        now = datetime.now(timezone.utc)
        result = TrialResult(
            task_name=f"fixture/{trial.task.path.name}",
            trial_name=trial.trial_name,
            trial_uri=directory.as_uri(),
            task_id=trial.task.get_task_id(),
            task_checksum=Task(trial.task.path).checksum,
            config=trial,
            agent_info=AgentInfo(
                name="nop",
                version="cpu",
                model_info=ModelInfo(name=trial.agent.model_name),
            ),
            verifier_result=VerifierResult(rewards={"reward": reward}, return_code=0),
            started_at=now,
            finished_at=now,
            agent_execution=TimingInfo(started_at=now, finished_at=now),
            verifier=TimingInfo(started_at=now, finished_at=now),
        )
        readiness.write_json(directory / "config.json", readiness.execution_dump(trial))
        path = directory / "result.json"
        readiness.write_json(path, result.model_dump(mode="json"))
        return path

    return {
        "lock": lock,
        "claim": claim,
        "prepared": prepared,
        "owner": owner,
        "job_dir": job_dir,
        "finish": finish,
        "output": tmp_path / "planned",
    }


def test_plan_only_never_created_preserves_zero_one_and_groups_attempts(campaign):
    zero = campaign["finish"](0, 0.0)
    one = campaign["finish"](1, 1.0)
    third = campaign["finish"](5, 0.0)
    original = {p: p.read_bytes() for p in (zero, one, third)}
    plan = recovery.plan(campaign["lock"], campaign["output"])
    assert plan["n_source_trials"] == 8
    assert plan["n_never_created"] == 5
    assert plan["n_retained_terminal"] == 3
    indices = [i for group in plan["jobs"] for i in group["source_plan_indices"]]
    assert sorted(indices) == [2, 3, 4, 6, 7]
    assert len(indices) == len(set(indices))
    assert len(plan["jobs"]) == 3
    total = 0
    for group in plan["jobs"]:
        config = JobConfig.model_validate(readiness.read(Path(group["config_path"])))
        assert len(config.agents) == 1 and config.job_name != "source"
        assert config.retry.max_retries == 0
        total += len(config.tasks) * config.n_attempts
        profiles = readiness.read(Path(group["profiles_path"]))
        assert all(
            value == campaign["prepared"]["profiles"][key]
            for key, value in profiles.items()
        )
    assert total == 5
    assert all(p.read_bytes() == data for p, data in original.items())
    assert plan["dispatch_performed"] is False
    assert not list(campaign["output"].rglob("*.dispatch.json"))


def test_result_checksum_uses_the_native_algorithm_not_packager(campaign):
    path = campaign["finish"](0)
    raw = readiness.read(path)
    task_path = raw["config"]["task"]["path"]
    packager_digest = campaign["prepared"]["identity"]["tasks"][task_path]
    assert raw["task_checksum"] != packager_digest
    assert (
        recovery.plan(campaign["lock"], campaign["output"])["n_retained_terminal"] == 1
    )


def test_packager_digest_cannot_replace_a_native_result_checksum(campaign):
    path = campaign["finish"](0)
    raw = readiness.read(path)
    task_path = raw["config"]["task"]["path"]
    raw["task_checksum"] = campaign["prepared"]["identity"]["tasks"][task_path]
    readiness.write_json(path, raw)
    with pytest.raises(ValueError, match="invalid Trial"):
        recovery.plan(campaign["lock"], campaign["output"])
    assert not campaign["output"].exists()


@pytest.mark.parametrize(
    "mutation", ["incomplete", "unfinished", "cleanup", "identity", "old_result"]
)
def test_started_or_unknown_evidence_blocks_all_planning(campaign, mutation):
    name = campaign["prepared"]["trials"][0]["trial_name"]
    if mutation == "incomplete":
        directory = campaign["job_dir"] / name
        directory.mkdir()
        (directory / "Recorder.original").write_text("Keep incomplete evidence.")
    else:
        path = campaign["finish"](0)
        result = readiness.read(path)
        if mutation == "unfinished":
            result["finished_at"] = None
        elif mutation == "cleanup":
            result["infrastructure_errors"] = [
                {
                    "phase": "cleanup",
                    "exception_info": {
                        "exception_type": "TimeoutError",
                        "exception_message": "unconfirmed",
                        "exception_traceback": "",
                        "occurred_at": datetime.now(timezone.utc).isoformat(),
                    },
                }
            ]
        elif mutation == "identity":
            result["config"]["agent"]["model_name"] = "fixture/other"
        else:
            del result["failure_phase"]
        readiness.write_json(path, result)
    before = {p: p.read_bytes() for p in campaign["job_dir"].rglob("*") if p.is_file()}
    with pytest.raises(ValueError):
        recovery.plan(campaign["lock"], campaign["output"])
    assert not campaign["output"].exists()
    assert all(p.read_bytes() == data for p, data in before.items())


@pytest.mark.parametrize(
    "state", ["alive", "foreign", "permission", "missing_identity", "wrong_lock"]
)
def test_dispatcher_must_be_proven_retired(campaign, monkeypatch, state):
    claim = readiness.read(campaign["claim"])
    if state == "alive":
        monkeypatch.setattr(
            readiness, "process_identity", lambda pid: campaign["owner"]
        )
    elif state == "foreign":
        claim["process"]["hostname"] = "another-node"
    elif state == "permission":

        def denied(pid):
            raise PermissionError("No process access")

        monkeypatch.setattr(readiness, "process_identity", denied)
    elif state == "missing_identity":
        del claim["process"]
    else:
        claim["lock_sha256"] = "0" * 64
    readiness.write_json(campaign["claim"], claim)
    with pytest.raises(ValueError):
        recovery.plan(campaign["lock"], campaign["output"])
    assert not campaign["output"].exists()


def test_existing_output_and_atomic_directory_race_are_never_overwritten(
    campaign, monkeypatch
):
    output = campaign["output"]
    output.mkdir()
    sentinel = output / "existing.json"
    sentinel.write_text("existing")
    with pytest.raises(FileExistsError):
        recovery.plan(campaign["lock"], output)
    assert sentinel.read_text() == "existing"
    fresh = output.with_name("raced")
    original = Path.mkdir

    def competing_mkdir(path, *args, **kwargs):
        if path == fresh:
            original(path)
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "mkdir", competing_mkdir)
    with pytest.raises(FileExistsError):
        recovery.plan(campaign["lock"], fresh)
    assert not list(fresh.iterdir())


def test_source_drift_is_rejected(campaign):
    lock = readiness.read(campaign["lock"])
    lock["prepared"]["profiles"]["fixture/a"]["agent_env"]["PUBLIC_PROFILE"] = "changed"
    readiness.write_json(campaign["lock"], lock)
    with pytest.raises(ValueError, match="Prepared inputs changed"):
        recovery.plan(campaign["lock"], campaign["output"])
    assert not campaign["output"].exists()


def test_terminal_attempt_without_reward_is_retained_without_retry(campaign):
    path = campaign["finish"](0)
    result = readiness.read(path)
    result["verifier_result"] = None
    result["verifier"] = None
    readiness.write_json(path, result)
    before = path.read_bytes()
    plan = recovery.plan(campaign["lock"], campaign["output"])
    assert plan["n_retained_terminal"] == 1
    assert plan["n_never_created"] == 7
    assert plan["source_trials"][0]["scoring_status"] == "UNKNOWN"
    assert all(0 not in group["source_plan_indices"] for group in plan["jobs"])
    assert path.read_bytes() == before


def test_missing_pid_is_retired_only_for_the_exact_proc_stat(campaign, monkeypatch):
    def gone(pid):
        raise FileNotFoundError(errno.ENOENT, "Process exited", f"/proc/{pid}/stat")

    monkeypatch.setattr(readiness, "process_identity", gone)
    assert recovery.plan(campaign["lock"], campaign["output"])["n_never_created"] == 8


@pytest.mark.parametrize("inside", ["job", "task"])
def test_output_cannot_change_source_job_or_official_task(campaign, inside):
    parent = (
        campaign["job_dir"]
        if inside == "job"
        else Path(campaign["prepared"]["trials"][0]["task"]["path"])
    )
    output = parent / "new-recovery"
    with pytest.raises(ValueError, match="outside source Job and Task"):
        recovery.plan(campaign["lock"], output)
    assert not output.exists()
