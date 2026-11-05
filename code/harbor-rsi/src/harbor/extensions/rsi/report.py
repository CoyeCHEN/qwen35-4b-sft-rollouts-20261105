"""Read native Campaign evidence against the frozen, attempt-level Trial plan."""

from __future__ import annotations

import hashlib
import json
import math
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

from harbor.models.trial.config import TrialConfig

Record = dict[str, Any]
CLEANUP_PHASES = {"cleanup", "finalize"}
AGENT_FAILURES = {"AgentTimeoutError", "NonZeroAgentExitCodeError"}


def _canonical_config(raw: Record) -> Record:
    # Native run allocates a Job UUID and output directory after preparation.
    # These two fields are checked against the actual Job below, not discarded.
    return TrialConfig.model_validate(raw).model_dump(
        mode="json", exclude={"job_id", "trials_dir"}
    )


def _time(value: Any) -> datetime:
    if not isinstance(value, str):
        raise ValueError("Missing native phase timestamp")
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _finite(value: Any) -> bool:
    return type(value) in (int, float) and math.isfinite(value)


def _verifier_completed(raw: Record) -> tuple[bool, list[str]]:
    verifier = raw.get("verifier_result") or {}
    rewards = verifier.get("rewards")
    reasons = []
    if type(verifier.get("return_code")) is not int or verifier["return_code"] != 0:
        reasons.append("verifier_return_code_not_zero")
    if (
        not isinstance(rewards, dict)
        or not rewards
        or not all(_finite(value) for value in rewards.values())
    ):
        reasons.append("reward_missing_or_nonfinite")
    try:
        phase = raw.get("verifier") or {}
        start, finish = _time(phase.get("started_at")), _time(phase.get("finished_at"))
        if (
            not _time(raw.get("started_at"))
            <= start
            <= finish
            <= _time(raw.get("finished_at"))
        ):
            reasons.append("verifier_timing_out_of_order")
        agent_finish = (raw.get("agent_execution") or {}).get("finished_at")
        if agent_finish and _time(agent_finish) > start:
            reasons.append("verifier_precedes_agent_end")
    except (ValueError, TypeError):
        reasons.append("verifier_timing_missing_or_invalid")
    return not reasons, reasons


def _row(plan: Record, index: int, path: Path | None, raw: Record | None) -> Record:
    agent = plan["agent"]
    row: Record = {
        "plan_index": index,
        "trial_name": plan["trial_name"],
        "model_name": agent.get("model_name") or f"agent:{agent.get('name')}",
        "state": "pending",
        "scoring_status": "UNKNOWN",
        "official_verifier_completed": False,
        "scored": False,
        "rewards": None,
        "scalar_reward": None,
        "agent_outcome": "UNKNOWN",
        "cleanup_errors": [],
        "infrastructure_errors": [],
        "unknown_reasons": ["result_missing"],
        "qualified_success": None,
        "qualification_status": "SEPARATE_RECORDER_AUDIT_REQUIRED",
        "result_path": str(path.resolve()) if path else None,
    }
    if raw is None:
        return row
    exception = raw.get("exception_info") or {}
    error_type, phase = exception.get("exception_type"), raw.get("failure_phase")
    infrastructure = raw.get("infrastructure_errors") or []
    secondary = raw.get("secondary_errors") or []
    completed, reasons = _verifier_completed(raw)
    if any(error.get("phase") not in CLEANUP_PHASES for error in infrastructure):
        reasons.append("non_cleanup_infrastructure_error")
    if any(
        error.get("phase") not in CLEANUP_PHASES
        and (error.get("exception_info") or {}).get("exception_type")
        not in AGENT_FAILURES
        for error in secondary
    ):
        reasons.append("non_agent_secondary_error")
    if (
        error_type
        and phase not in CLEANUP_PHASES
        and not (error_type in AGENT_FAILURES and phase in (None, "agent_execution"))
    ):
        reasons.append("non_agent_execution_exception")
    outcome = "UNKNOWN"
    if error_type == "AgentTimeoutError":
        outcome = "timeout"
    elif error_type == "NonZeroAgentExitCodeError":
        outcome = "nonzero"
    elif not error_type or phase in CLEANUP_PHASES:
        timing = raw.get("agent_execution") or {}
        try:
            if _time(timing.get("started_at")) <= _time(timing.get("finished_at")):
                outcome = "normal_native_return"
        except (ValueError, TypeError):
            pass
    verifier = raw.get("verifier_result") or {}
    rewards = verifier.get("rewards")
    row.update(
        id=raw.get("id"),
        task_name=raw.get("task_name"),
        task_checksum=raw.get("task_checksum"),
        state="terminal" if raw.get("finished_at") else "pending",
        started_at=raw.get("started_at"),
        finished_at=raw.get("finished_at"),
        official_verifier_completed=completed,
        scored=not reasons,
        scoring_status="SCORED" if not reasons else "UNKNOWN",
        rewards=rewards,
        scalar_reward=rewards.get("reward") if isinstance(rewards, dict) else None,
        agent_outcome=outcome,
        exception_info=raw.get("exception_info"),
        failure_phase=phase,
        infrastructure_errors=infrastructure,
        secondary_errors=secondary,
        cleanup_errors=[
            error for error in infrastructure if error.get("phase") in CLEANUP_PHASES
        ],
        cleanup_unconfirmed=any(
            error.get("phase") in CLEANUP_PHASES for error in infrastructure
        )
        or phase in CLEANUP_PHASES,
        unknown_reasons=reasons,
    )
    return row


def summarize(job_dir: Path, planned: list[Record]) -> Record:
    """Preserve fixed denominators, raw rewards and the separate Recorder boundary."""
    job_dir = job_dir.resolve()
    plans: dict[str, Record] = {}
    for raw in planned:
        name = raw.get("trial_name")
        if not isinstance(name, str) or not name or Path(name).name != name:
            raise ValueError(
                "Every frozen TrialConfig needs an explicit unique trial_name"
            )
        if name in plans:
            raise ValueError(f"Duplicate planned trial_name: {name}")
        plans[name] = _canonical_config(raw)
    job_path = job_dir / "result.json"
    job = json.loads(job_path.read_text()) if job_path.is_file() else {}
    problems: list[str] = []
    results: list[tuple[Path, Record]] = []
    unreadable: set[str] = set()
    for path in sorted(job_dir.glob("*/result.json")):
        try:
            value = json.loads(path.read_text())
            if not isinstance(value, dict) or not isinstance(
                value.get("trial_name"), str
            ):
                raise ValueError("Invalid native Result identity")
            results.append((path, value))
        except (ValueError, OSError):
            unreadable.add(path.parent.name)
            problems.append(f"Unreadable Result: {path.parent.name}")
    counts = Counter(raw["trial_name"] for _, raw in results)
    ids = Counter(str(raw.get("id")) for _, raw in results if raw.get("id"))
    matched: dict[str, tuple[Path, Record]] = {}
    rejected: dict[str, list[str]] = {}
    for path, raw in results:
        name = raw["trial_name"]
        if name not in plans:
            problems.append(f"Unexpected Result: {path.parent.name}")
            continue
        matched[name] = (path, raw)
        reasons = []
        if name != path.parent.name or counts[name] != 1:
            reasons.append("duplicate_or_misplaced_trial_name")
        if not raw.get("id") or ids[str(raw["id"])] != 1:
            reasons.append("missing_or_duplicate_trial_uuid")
        try:
            actual = raw["config"]
            if _canonical_config(actual) != plans[name]:
                reasons.append("execution_config_drift")
            if Path(actual["trials_dir"]).resolve() != job_dir:
                reasons.append("runtime_trials_dir_mismatch")
            if not job.get("id") or actual.get("job_id") != job["id"]:
                reasons.append("runtime_job_id_mismatch")
        except (ValueError, TypeError, KeyError):
            reasons.append("invalid_result_config")
        if reasons:
            rejected.setdefault(name, []).extend(reasons)
            problems.append(f"Rejected Result identity: {name}")
    rows = []
    for index, (name, plan) in enumerate(plans.items()):
        path, raw = matched.get(name, (None, None))
        row = _row(plan, index, path, raw)
        if path:
            row["result_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
            row["runtime_job_id"] = (raw or {}).get("config", {}).get("job_id")
        if name in rejected or name in unreadable:
            row.update(
                state="UNKNOWN",
                scored=False,
                scoring_status="UNKNOWN",
                unknown_reasons=rejected.get(name, ["unreadable_result"]),
            )
        rows.append(row)
    models = {}
    for model in dict.fromkeys(row["model_name"] for row in rows):
        selected = [row for row in rows if row["model_name"] == model]
        scored = [row for row in selected if row["scored"]]
        scalar = [row for row in scored if _finite(row["scalar_reward"])]
        success = sum(row["scalar_reward"] == 1 for row in scalar) if scalar else None
        models[model] = {
            "expected": len(selected),
            "terminal_results": sum(row["state"] == "terminal" for row in selected),
            "official_verifier_completed": sum(
                row["official_verifier_completed"] for row in selected
            ),
            "scored": len(scored),
            "UNKNOWN": len(selected) - len(scored),
            "scalar_scored": len(scalar),
            "scalar_scored_coverage": len(scalar) / len(selected),
            "confirmed_reward1": success,
            "confirmed_reward1_rate_fixed_denominator": (
                success / len(selected) if success is not None else None
            ),
            "scored_coverage": len(scored) / len(selected),
            "agent_outcomes": dict(Counter(row["agent_outcome"] for row in selected)),
        }
    complete = (
        bool(rows)
        and not problems
        and all(row["scored"] for row in rows)
        and bool(job.get("finished_at"))
    )
    return {
        "schema_version": 1,
        "kind": "native_campaign_report",
        "job_dir": str(job_dir),
        "job_id": job.get("id"),
        "job_finished_at": job.get("finished_at"),
        "run_status": "completed"
        if complete
        else "failed"
        if problems
        else "partial"
        if any(row["scored"] for row in rows)
        else "pending",
        "identity_integrity_passed": not problems,
        "n_expected": len(rows),
        "n_finished": sum(row["state"] == "terminal" for row in rows),
        "n_scored": sum(row["scored"] for row in rows),
        "n_UNKNOWN": sum(not row["scored"] for row in rows),
        "models": models,
        "trials": rows,
        "problems": problems,
        "qualified_success_not_inferred": True,
    }
