"""Collecting another native Job must retain prior attempts and their rewards."""

import json
import csv
from pathlib import Path

import pytest

from dirhash import dirhash

from benchmarks.readiness.audit import write_csv, write_json
from benchmarks.readiness.collect_evidence import collect, verifier_evidence
from harbor.publisher.packager import Packager


@pytest.mark.parametrize(
    ("summary", "expected"),
    [
        ({"tests": 3, "passed": 0, "failed": 0, "skipped": 3}, "not_executed"),
        ({"tests": 4, "passed": 0, "failed": 0, "pending": 4}, "not_executed"),
        ({"tests": 0, "passed": 0, "failed": 0, "skipped": 0}, "not_executed"),
        ({"tests": 3, "passed": 0, "failed": 2, "skipped": 1}, "complete"),
        ({"tests": 2, "passed": 2, "failed": 0, "skipped": 0}, "complete"),
    ],
)
def test_readiness_requires_executed_tests_not_only_collected_tests(
    tmp_path: Path, summary: dict, expected: str
) -> None:
    report = tmp_path / "verifier" / "ctrf.json"
    report.parent.mkdir()
    write_json(report, {"results": {"summary": summary}})
    original = report.read_bytes()
    assert verifier_evidence(tmp_path, "tb21") == (expected, summary)
    assert report.read_bytes() == original


@pytest.mark.parametrize("blocked", [False, True])
@pytest.mark.parametrize("corrupt", [None, "source_task_hash", "prepared_task_hash"])
def test_prepared_tasks_require_explicit_hash_verified_source_mapping(
    tmp_path: Path, corrupt: str | None, blocked: bool
) -> None:
    source, prepared = tmp_path / "source", tmp_path / "prepared"
    source.mkdir()
    prepared.mkdir()
    (source / "instruction.md").write_text("Official input\n")
    (prepared / "instruction.md").write_text("Official input\n")
    (prepared / "dependency.txt").write_text("Verifier-only cache\n")
    source_hash = Packager.compute_content_hash(source)[0]
    prepared_hash = Packager.compute_content_hash(prepared)[0]
    output = tmp_path / "output"
    output.mkdir()
    write_csv(
        output / "task-readiness.csv",
        [
            {
                "benchmark": "tb21",
                "task_id": "official-id",
                "task_path": str(source),
                "task_hash": source_hash,
                "level3": "not_run",
                "level2": "blocked_required_egress" if blocked else "not_run",
                "native_trial": "",
                "verifier_execution": "",
                "cleanup_confirmed": False,
                "readiness_status": "BLOCKED" if blocked else "STATIC_READY",
                "judge_complete": "not_required",
            }
        ],
    )
    write_json(output / "preflight-results.json", {"summary": {"tb21": {}}})
    trial = tmp_path / "jobs" / "prepared-job" / "prepared-trial"
    (trial / "verifier").mkdir(parents=True)
    write_json(
        trial / "verifier/ctrf.json",
        {
            "results": {
                "summary": {
                    "tests": 1,
                    "passed": 0,
                    "failed": 1,
                    "skipped": 0,
                }
            }
        },
    )
    write_json(
        trial / "result.json",
        {
            "config": {"task": {"path": str(prepared)}},
            "trial_name": "prepared-trial",
            "task_checksum": dirhash(prepared, "sha256"),
            "started_at": "2026-01-01T00:00:00Z",
            "finished_at": "2026-01-01T00:00:01Z",
            "exception_info": None,
            "infrastructure_errors": [],
            "agent_result": None,
            "verifier_result": {"return_code": 0, "rewards": {"reward": 0}},
        },
    )
    mapping = {
        "source_task": str(source),
        "prepared_task": str(prepared),
        "source_task_hash": source_hash,
        "prepared_task_hash": prepared_hash,
    }
    cleanup = {"prepared-trial": {"confirmed": True}}
    if corrupt:
        mapping[corrupt] = "0" * 64
        with pytest.raises(ValueError, match="[Hh]ash"):
            collect(tmp_path / "jobs", output, cleanup, task_variants=[mapping])
        assert not (output / "evidence/native-trials.json").exists()
        return
    with pytest.raises(KeyError):
        collect(tmp_path / "jobs", output, cleanup)
    collect(tmp_path / "jobs", output, cleanup, task_variants=[mapping])
    row = list(csv.DictReader((output / "task-readiness.csv").open()))[0]
    assert row["task_hash"] == source_hash and row["task_path"] == str(source)
    assert row["execution_task_hash"] == prepared_hash
    assert row["execution_task_path"] == str(prepared)
    assert row["level3"] == "passed"
    assert row["level2"] == ("blocked_required_egress" if blocked else "passed")
    assert row["readiness_status"] == ("BLOCKED" if blocked else "DYNAMIC_READY")
    summary = json.loads((output / "preflight-results.json").read_text())["summary"][
        "tb21"
    ]
    assert summary["new_dynamic_passed"] == (0 if blocked else 1)
    proof = json.loads((output / "evidence/native-trials.json").read_text())[0]
    assert proof["task_id"] == "official-id"
    assert proof["current_packager_hash"] == prepared_hash
    assert proof["source_packager_hash"] == source_hash
    assert proof["execution_variant"] == mapping


@pytest.mark.parametrize(
    ("status", "failures", "count", "rubrics", "expected"),
    [
        ("ok", 0, 1, [{"result": {"passed": False}}], "complete"),
        ("empty_output", 0, 0, [], "empty_submission_without_judge"),
        ("ok", 1, 1, [{"result": {}}], "unproven"),
        ("ok", 0, 0, [], "unproven"),
        ("ok", 0, 2, [{"result": {}}], "unproven"),
        ("ok", 0, 1, [{"result": None}], "unproven"),
        ("ok", 0, 1, [{"result": {}}], "unproven"),
        ("judge_error", 0, 1, [{"result": {}}], "unproven"),
    ],
)
def test_judge_readiness_requires_all_rubric_results(
    tmp_path: Path,
    status: str,
    failures: int,
    count: int,
    rubrics: list,
    expected: str,
) -> None:
    verifier = tmp_path / "verifier"
    verifier.mkdir()
    report = {
        "status": status,
        "judge_failures": failures,
        "total_count": count,
        "rubrics": rubrics,
    }
    write_json(verifier / "jobbench_result.json", report)
    assert verifier_evidence(tmp_path, "jobbench-main") == (expected, report)


def test_incremental_collection_preserves_prior_attempts_and_bounds_selection(
    tmp_path: Path,
) -> None:
    task = tmp_path / "task"
    task.mkdir()
    (task / "instruction.md").write_text("Readiness fixture\n")
    output = tmp_path / "output"
    output.mkdir()
    (output / "evidence").mkdir()
    write_csv(
        output / "task-readiness.csv",
        [
            {
                "benchmark": "alfworld",
                "task_id": "fixture",
                "task_path": str(task),
                "task_hash": "fixture-content-hash",
                "level3": "not_run",
                "level2": "not_run",
                "native_trial": "",
                "verifier_execution": "",
                "cleanup_confirmed": False,
                "readiness_status": "STATIC_READY",
                "judge_complete": "not_required",
            }
        ],
    )
    write_json(output / "preflight-results.json", {"summary": {"alfworld": {}}})
    jobs = tmp_path / "jobs"
    for job, reward in [("original", 0), ("repair", 1)]:
        trial = jobs / job / job
        (trial / "verifier").mkdir(parents=True)
        (trial / "verifier/test-stdout.txt").write_text(
            '{"started": true, "steps_taken": 0}\n'
        )
        write_json(
            trial / "result.json",
            {
                "config": {"task": {"path": str(task)}},
                "trial_name": job,
                "task_checksum": dirhash(task, "sha256"),
                "started_at": "2026-01-01T00:00:00Z",
                "finished_at": "2026-01-01T00:00:01Z",
                "exception_info": None,
                "infrastructure_errors": [],
                "agent_result": None,
                "verifier_result": {"return_code": 0, "rewards": {"reward": reward}},
            },
        )
    cleanup = {job: {"confirmed": True} for job in ["original", "repair"]}
    collect(jobs, output, cleanup, {"original"})
    evidence_path = output / "evidence/native-trials.json"
    original = json.loads(evidence_path.read_text())[0]
    assert original["job"] == "original"
    assert original["verifier_result"]["rewards"]["reward"] == 0
    collect(jobs, output, cleanup, {"repair"})
    evidence = json.loads(evidence_path.read_text())
    assert len(evidence) == 2 and evidence[0] == original
    assert evidence[1]["verifier_result"]["rewards"]["reward"] == 1
    collect(jobs, output, cleanup, {"repair"})
    assert json.loads(evidence_path.read_text()) == evidence
    assert (
        json.loads((output / "preflight-results.json").read_text())["native_attempts"]
        == 2
    )
