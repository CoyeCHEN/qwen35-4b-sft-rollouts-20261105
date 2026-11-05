"""Merge existing native trial evidence; never execute, retry or change a result."""

import argparse
import csv
import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from dirhash import dirhash

from benchmarks.readiness.audit import write_csv, write_json
from harbor.publisher.packager import Packager


def duration(phase: dict[str, Any] | None) -> float | None:
    if not phase or not phase.get("started_at") or not phase.get("finished_at"):
        return None
    return (
        datetime.fromisoformat(phase["finished_at"])
        - datetime.fromisoformat(phase["started_at"])
    ).total_seconds()


def verifier_evidence(directory: Path, benchmark: str) -> tuple[str, dict[str, Any]]:
    logs = directory / "verifier"
    stdout = (
        (logs / "test-stdout.txt").read_text()
        if (logs / "test-stdout.txt").exists()
        else ""
    )
    ctrf = logs / "ctrf.json"
    if benchmark == "tb21":
        if ctrf.exists():
            report = json.loads(ctrf.read_text())["results"]["summary"]
            # Collected but entirely skipped/pending tests do not establish
            # readiness. Legitimate assertion failures still prove execution.
            executed = report.get("passed", 0) + report.get("failed", 0)
            return (
                "complete" if report["tests"] > 0 and executed > 0 else "not_executed",
                report,
            )
        # Official test.sh can write zero even when uvx never starts pytest.
        if "uvx: command not found" in stdout or "failed to download" in stdout:
            return "dependency_failure", {
                "pytest_executed": False,
                "reason": "official uv 0.9.5 installer could not fetch GitHub release; uvx missing",
            }
        return "unproven", {"pytest_executed": False}
    if benchmark == "clawgym" and (logs / "official_result.json").exists():
        report = json.loads((logs / "official_result.json").read_text())
        return report["score_completeness"], report
    if benchmark.startswith("jobbench") and (logs / "jobbench_result.json").exists():
        report = json.loads((logs / "jobbench_result.json").read_text())
        if report["status"] == "empty_output":
            return "empty_submission_without_judge", report
        rubrics = report.get("rubrics", [])
        complete = (
            report["status"] == "ok"
            and report.get("judge_failures") == 0
            and report.get("total_count", 0) > 0
            and len(rubrics) == report["total_count"]
            and all(
                isinstance(rubric.get("result"), dict)
                and isinstance(rubric["result"].get("passed"), bool)
                for rubric in rubrics
            )
        )
        return "complete" if complete else "unproven", report
    if (
        benchmark == "alfworld"
        and '"started": true' in stdout
        and '"steps_taken": 0' in stdout
    ):
        return "complete", {
            "episode_started": True,
            "steps_taken": 0,
            "official_success_verifier": True,
        }
    return "not_executed", {}


def collect(
    jobs: Path,
    output: Path,
    cleanup: dict[str, Any],
    job_names: set[str] | None = None,
    task_variants: list[dict[str, Any]] | None = None,
) -> None:
    rows = list(csv.DictReader((output / "task-readiness.csv").open()))
    by_path = {str(Path(row["task_path"]).resolve()): row for row in rows}
    variants = {}
    for variant in task_variants or []:
        prepared_path = str(Path(variant["prepared_task"]).resolve())
        source_path = str(Path(variant["source_task"]).resolve())
        if prepared_path in variants or prepared_path in by_path:
            raise ValueError("Ambiguous prepared task mapping")
        row = by_path[source_path]
        if (
            variant["source_task_hash"] != row["task_hash"]
            or Packager.compute_content_hash(Path(source_path))[0] != row["task_hash"]
        ):
            raise ValueError("Prepared task source hash mismatch")
        variants[prepared_path] = variant
    evidence = []
    for path in sorted(jobs.glob("*/*/result.json")):
        if job_names is not None and path.parent.parent.name not in job_names:
            continue
        result = json.loads(path.read_text())
        if not result.get("finished_at"):
            continue
        task_path = result["config"]["task"]["path"]
        resolved_path = str(Path(task_path).resolve())
        variant = variants.get(resolved_path)
        row = by_path[
            str(Path(variant["source_task"]).resolve()) if variant else resolved_path
        ]
        execution_hash = row["task_hash"]
        if variant:
            execution_hash = Packager.compute_content_hash(Path(task_path))[0]
            if execution_hash != variant["prepared_task_hash"]:
                raise ValueError("Prepared execution task hash mismatch")
        status, proof = verifier_evidence(path.parent, row["benchmark"])
        verifier = result["verifier_result"]
        clean = cleanup.get(
            result["trial_name"],
            {"confirmed": False, "reason": "not independently checked"},
        )
        current_checksum = dirhash(task_path, "sha256")
        valid = (
            current_checksum == result["task_checksum"]
            and not result["exception_info"]
            and not result["infrastructure_errors"]
            and verifier
            and verifier["return_code"] == 0
            and verifier.get("rewards")
            and clean["confirmed"]
        )
        level3 = (
            "passed"
            if valid and status == "complete"
            else "partial_no_judge"
            if valid and status == "empty_submission_without_judge"
            else "unverified_cleanup"
            if not clean["confirmed"]
            and clean.get("reason") == "not independently checked"
            and not result["exception_info"]
            and not result["infrastructure_errors"]
            else "failed"
        )
        files = [
            {
                "path": str(p.relative_to(path.parent)),
                "sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
                "bytes": p.stat().st_size,
            }
            for p in sorted(path.parent.rglob("*"))
            if p.is_file()
            and p.relative_to(path.parent).parts[0] in {"verifier", "artifacts"}
        ]
        evidence.append(
            {
                "benchmark": row["benchmark"],
                "task_id": row["task_id"],
                "trial_name": result["trial_name"],
                "job": path.parent.parent.name,
                "native_result_path": str(path),
                "native_result_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "native_task_checksum": result["task_checksum"],
                "current_native_checksum": current_checksum,
                "native_checksum_matches": current_checksum == result["task_checksum"],
                "current_packager_hash": execution_hash,
                "source_packager_hash": row["task_hash"],
                "execution_variant": variant,
                "started_at": result["started_at"],
                "finished_at": result["finished_at"],
                "phases_seconds": {
                    name: duration(result.get(name))
                    for name in [
                        "environment_setup",
                        "agent_setup",
                        "agent_execution",
                        "verifier",
                    ]
                },
                "total_seconds": duration(result),
                "exception_info": result["exception_info"],
                "infrastructure_errors": result["infrastructure_errors"],
                "verifier_result": verifier,
                "verifier_proof": proof,
                "verifier_completeness": status,
                "agent_metadata": (result.get("agent_result") or {}).get("metadata"),
                "cleanup": clean,
                "level3": level3,
                "files": files,
            }
        )
        # Preserve failed attempts in evidence; a later successful repair may
        # update current readiness but cannot erase the original attempt.
        if row["level3"] != "passed":
            # A fixture can execute the verifier without exercising a required
            # Agent network/asset prerequisite. Keep that independent gate.
            prerequisite_blocked = row["readiness_status"] == "BLOCKED"
            row.update(
                level3=level3,
                level2=row["level2"]
                if prerequisite_blocked
                else "passed"
                if valid
                else "failed_or_unproven",
                native_trial=result["trial_name"],
                verifier_execution=status,
                cleanup_confirmed=clean["confirmed"],
            )
            if level3 == "passed":
                if not prerequisite_blocked:
                    row["readiness_status"] = "DYNAMIC_READY"
                row["execution_task_path"] = resolved_path
                row["execution_task_hash"] = execution_hash
                row["judge_complete"] = (
                    "complete"
                    if row["benchmark"].startswith("jobbench")
                    or proof.get("score_mode") == "hybrid"
                    else "not_required"
                )
    write_csv(output / "task-readiness.csv", rows)
    evidence_path = output / "evidence" / "native-trials.json"
    previous = json.loads(evidence_path.read_text()) if evidence_path.exists() else []
    merged = {
        (item["native_result_path"], item["native_result_sha256"]): item
        for item in [*previous, *evidence]
    }
    evidence = list(merged.values())
    write_json(evidence_path, evidence)
    preflight = json.loads((output / "preflight-results.json").read_text())
    for benchmark, summary in preflight["summary"].items():
        matching = [r for r in rows if r["benchmark"] == benchmark]
        summary.update(
            new_dynamic_passed=sum(
                r["level3"] == "passed"
                and r["level2"] == "passed"
                and r["readiness_status"] == "DYNAMIC_READY"
                for r in matching
            ),
            native_verifier_gate_passed=sum(r["level3"] == "passed" for r in matching),
            new_partial_no_judge=sum(
                r["level3"] == "partial_no_judge" for r in matching
            ),
            new_failed_readiness=sum(r["level3"] == "failed" for r in matching),
        )
    preflight["scope"] = (
        "Native parsed/static tasks plus separately recorded native readiness trials; "
        "Agent and Judge request provenance are recorded independently"
    )
    preflight["native_attempts"] = len(evidence)
    preflight["native_result_zero_does_not_imply_readiness"] = True
    write_json(output / "preflight-results.json", preflight)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--jobs", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--cleanup", required=True, type=Path)
    parser.add_argument("--job-name", action="append")
    parser.add_argument(
        "--task-variants",
        type=Path,
        help="Explicit hash-verified source/prepared task mapping JSON (tasks list)",
    )
    args = parser.parse_args()
    collect(
        args.jobs,
        args.output,
        json.loads(args.cleanup.read_text()),
        set(args.job_name) if args.job_name else None,
        json.loads(args.task_variants.read_text())["tasks"]
        if args.task_variants
        else None,
    )


if __name__ == "__main__":
    main()
