"""Attempt identities and official scoring remain distinct from process health."""

import copy
import hashlib
import json
from uuid import uuid4

import pytest

from harbor.extensions.rsi.report import summarize
from harbor.models.trial.config import TrialConfig


@pytest.fixture
def campaign(tmp_path):
    job_dir = tmp_path / "native-job"
    job_dir.mkdir()
    job_id = str(uuid4())
    (job_dir / "result.json").write_text(
        json.dumps({"id": job_id, "finished_at": "2026-11-04T00:10:00Z"})
    )
    plans = [
        TrialConfig.model_validate(
            {
                "task": {"path": tmp_path / "same-task"},
                "trial_name": f"model-{model}-attempt-{attempt}",
                "trials_dir": tmp_path / "prepared-output",
                "job_id": uuid4(),
                "agent": {
                    "name": "nop",
                    "model_name": model,
                    "override_timeout_sec": 10800,
                    "kwargs": {"context": 262144},
                },
                "environment": {"type": "docker"},
            }
        ).model_dump(mode="json")
        for model in ("M0", "M1")
        for attempt in (1, 2, 3)
    ]

    def write(index=0, reward=1, **changes):
        config = copy.deepcopy(plans[index])
        config.update(job_id=job_id, trials_dir=str(job_dir))
        result = {
            "id": str(uuid4()),
            "trial_name": config["trial_name"],
            "task_name": "same-task",
            "task_checksum": "unchanged-official-task",
            "config": config,
            "started_at": "2026-11-04T00:00:00Z",
            "finished_at": "2026-11-04T00:03:00Z",
            "agent_execution": {
                "started_at": "2026-11-04T00:01:00Z",
                "finished_at": "2026-11-04T00:02:00Z",
            },
            "verifier": {
                "started_at": "2026-11-04T00:02:01Z",
                "finished_at": "2026-11-04T00:02:59Z",
            },
            "verifier_result": {"return_code": 0, "rewards": {"reward": reward}},
            "exception_info": None,
            "infrastructure_errors": [],
        }
        result.update(changes)
        path = job_dir / plans[index]["trial_name"] / "result.json"
        path.parent.mkdir(exist_ok=True)
        path.write_text(json.dumps(result))
        return path, result

    return job_dir, plans, write


def test_same_task_two_models_three_attempts_is_six_unique_trials(campaign):
    job_dir, plans, write = campaign
    for index in range(6):
        write(index, reward=int(index % 3 == 0))
    original = {
        str(p): hashlib.sha256(p.read_bytes()).digest()
        for p in job_dir.rglob("*")
        if p.is_file()
    }
    report = summarize(job_dir, plans)
    assert report["run_status"] == "completed"
    assert report["n_expected"] == report["n_scored"] == 6
    for model in ("M0", "M1"):
        assert report["models"][model]["expected"] == 3
        assert (
            report["models"][model]["confirmed_reward1_rate_fixed_denominator"] == 1 / 3
        )
    assert all(row["qualified_success"] is None for row in report["trials"])
    assert original == {
        str(p): hashlib.sha256(p.read_bytes()).digest()
        for p in job_dir.rglob("*")
        if p.is_file()
    }


def test_missing_result_keeps_fixed_denominator_and_unknown(campaign):
    job_dir, plans, write = campaign
    write()
    report = summarize(job_dir, plans)
    assert report["n_scored"] == 1 and report["n_UNKNOWN"] == 5
    assert report["models"]["M0"]["confirmed_reward1_rate_fixed_denominator"] == 1 / 3
    assert report["trials"][1]["state"] == "pending"
    assert report["trials"][1]["scalar_reward"] is None
    assert report["models"]["M1"]["confirmed_reward1"] is None


@pytest.mark.parametrize(
    "error,outcome",
    [("AgentTimeoutError", "timeout"), ("NonZeroAgentExitCodeError", "nonzero")],
)
def test_agent_failure_does_not_erase_completed_official_score(
    campaign, error, outcome
):
    job_dir, plans, write = campaign
    write(
        reward=0,
        exception_info={"exception_type": error},
        failure_phase="agent_execution",
    )
    row = summarize(job_dir, plans)["trials"][0]
    assert row["scored"] and row["rewards"] == {"reward": 0}
    assert row["agent_outcome"] == outcome


def test_cleanup_failure_is_separate_from_valid_verifier_reward(campaign):
    job_dir, plans, write = campaign
    cleanup = {"phase": "cleanup", "exception_info": {"exception_type": "TimeoutError"}}
    write(
        infrastructure_errors=[cleanup],
        exception_info=cleanup["exception_info"],
        failure_phase="cleanup",
    )
    row = summarize(job_dir, plans)["trials"][0]
    assert row["scored"] and row["official_verifier_completed"]
    assert row["cleanup_errors"] == [cleanup] and row["cleanup_unconfirmed"]
    assert row["agent_outcome"] == "normal_native_return"
    assert row["qualified_success"] is None


@pytest.mark.parametrize(
    "phase", ["environment_setup", "verification", "agent_lifecycle"]
)
def test_infrastructure_failure_cannot_be_model_zero(campaign, phase):
    job_dir, plans, write = campaign
    write(
        reward=0,
        infrastructure_errors=[
            {"phase": phase, "exception_info": {"exception_type": "RuntimeError"}}
        ],
    )
    row = summarize(job_dir, plans)["trials"][0]
    assert not row["scored"] and row["scoring_status"] == "UNKNOWN"
    assert row["rewards"] == {"reward": 0}


@pytest.mark.parametrize(
    "changes",
    [
        {"verifier_result": {"return_code": 1, "rewards": {"reward": 0}}},
        {"verifier_result": {"return_code": 0, "rewards": None}},
        {"verifier_result": {"return_code": 0, "rewards": {"reward": float("nan")}}},
        {
            "verifier": {
                "started_at": "2026-11-04T00:04:00Z",
                "finished_at": "2026-11-04T00:04:01Z",
            }
        },
        {"verifier": None},
        {"finished_at": None},
    ],
)
def test_incomplete_or_invalid_verifier_evidence_is_unknown(campaign, changes):
    job_dir, plans, write = campaign
    write(**changes)
    row = summarize(job_dir, plans)["trials"][0]
    assert not row["official_verifier_completed"] and not row["scored"]


def test_non_scalar_rewards_have_no_invented_formula(campaign):
    job_dir, plans, write = campaign
    write(verifier_result={"return_code": 0, "rewards": {"correct": 3, "total": 7}})
    report = summarize(job_dir, plans)
    row = report["trials"][0]
    assert row["scored"] and row["rewards"] == {"correct": 3, "total": 7}
    assert row["scalar_reward"] is None
    assert report["models"]["M0"]["confirmed_reward1"] is None
    assert report["models"]["M0"]["scalar_scored"] == 0


@pytest.mark.parametrize(
    "field", ["budget", "task", "verifier", "environment", "job_id", "trials_dir"]
)
def test_execution_identity_and_native_job_bindings_are_strict(campaign, field):
    job_dir, plans, write = campaign
    path, raw = write()
    config = raw["config"]
    if field == "budget":
        config["agent"]["override_timeout_sec"] = 1
    elif field == "task":
        config["task"]["path"] = "/different-task"
    elif field == "verifier":
        config["verifier"]["override_timeout_sec"] = 1
    elif field == "environment":
        config["environment"]["override_memory_mb"] = 1
    elif field == "job_id":
        config["job_id"] = str(uuid4())
    else:
        config["trials_dir"] = "/other-job"
    path.write_text(json.dumps(raw))
    report = summarize(job_dir, plans)
    assert not report["identity_integrity_passed"]
    assert report["run_status"] == "failed" and report["n_scored"] == 0
    assert report["trials"][0]["rewards"] == {"reward": 1}


def test_unexpected_and_duplicate_results_are_not_accepted(campaign):
    job_dir, plans, write = campaign
    _, raw = write()
    other = job_dir / "duplicate"
    other.mkdir()
    (other / "result.json").write_text(json.dumps(raw))
    report = summarize(job_dir, plans)
    assert not report["identity_integrity_passed"] and report["n_scored"] == 0
    raw["trial_name"] = "unexpected"
    (other / "result.json").write_text(json.dumps(raw))
    assert any(
        "Unexpected Result" in error for error in summarize(job_dir, plans)["problems"]
    )


def test_duplicate_planned_names_are_rejected(campaign):
    job_dir, plans, _ = campaign
    with pytest.raises(ValueError, match="Duplicate planned"):
        summarize(job_dir, [plans[0], plans[0]])


def test_unreadable_result_is_not_a_zero(campaign):
    job_dir, plans, write = campaign
    path, _ = write()
    path.write_text("incomplete native JSON")
    row = summarize(job_dir, plans)["trials"][0]
    assert row["scoring_status"] == "UNKNOWN" and row["scalar_reward"] is None
