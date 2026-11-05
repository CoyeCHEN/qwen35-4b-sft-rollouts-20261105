#!/usr/bin/env python3
"""Harbor verifier shim for JobBench.

Runs the *unmodified* official JobBench judge (``vendor/judge.py``, pinned
commit recorded in ``vendor/PROVENANCE.md``) against the agent's deliverable
directory, then translates its report into Harbor's reward contract.

Harbor contract (see ``harbor/verifier/verifier.py``):
  * write ``/logs/verifier/reward.json`` — a JSON object, all values finite
    numbers — or ``/logs/verifier/reward.txt`` — a single parseable float.
  * ``reward.json`` wins when both exist.
  * the file must be (re)written on every code path, and must never be empty.

Extra reports are written for humans/debugging; Harbor ignores them:
  * ``jobbench_result.json`` — status + per-rubric detail
  * ``judge.json``           — the judge's own details report, verbatim
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

VERIFIER_DIR = Path("/logs/verifier")

# The judge's own words when it could not reach the model provider. These are
# *infrastructure* failures, not the agent answering badly, so they are counted
# separately — otherwise an API outage silently looks like a weak model.
_INFRA_PREFIXES = ("Failed after", "Failed to get", "Failed to parse")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir", type=Path, required=True, help="Directory holding the agent's deliverables."
    )
    parser.add_argument("--rubrics", type=Path, required=True)
    parser.add_argument(
        "--judge", type=Path, required=True, help="Path to the unmodified official judge.py."
    )
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--profession", required=True)
    parser.add_argument(
        "--evaluated-model", required=True, help="Name of the model that produced the deliverables."
    )
    parser.add_argument(
        "--judge-model", required=True, help="Model used to grade. Distinct from --evaluated-model."
    )
    parser.add_argument("--max-workers", default=os.environ.get("JOBBENCH_JUDGE_WORKERS", "3"))
    parser.add_argument("--max-retries", default="3")
    parser.add_argument("--timeout-per-rubric", default="300")
    return parser.parse_args()


def load_rubric_items(path: Path) -> list[dict]:
    """The judge accepts either key; upstream has used both."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    items = payload.get("rubrics") or payload.get("evaluation_rubrics")
    if not isinstance(items, list):
        raise TypeError(f"no rubric list in {path} (keys: {sorted(payload)})")
    return items


def has_submission(path: Path) -> bool:
    """True when the agent produced at least one real file.

    ``.keep`` placeholders exist so the output dir survives tarballing; they are
    not submissions.
    """
    if not path.is_dir():
        return False
    return any(
        item.is_file() and item.name not in {".keep", ".gitkeep"} for item in path.rglob("*")
    )


def count_infra_failures(details: dict) -> int:
    """How many rubrics failed for infrastructure reasons rather than substance.

    Empty output is deliberately *not* an infrastructure failure: the agent
    simply submitted nothing, which is a legitimate (bad) score. Counting it
    here would make "the model produced nothing" indistinguishable from "the
    judge API was down".
    """
    if details.get("error"):
        return 1

    rubrics = details.get("rubrics") or []

    # Nothing was attempted, so there is no shortfall to measure.
    if not rubrics:
        return 0

    failures = 0
    for item in rubrics:
        reasoning = str((item.get("result") or {}).get("overall_reasoning", ""))
        if reasoning.startswith(_INFRA_PREFIXES):
            failures += 1

    # The judge reports how many rubrics it *should* have produced. A shortfall
    # means some rubric died mid-flight.
    expected = details.get("total_count")
    if isinstance(expected, int) and len(rubrics) < expected:
        failures += expected - len(rubrics)

    return failures


def normalize(details: dict) -> float:
    """JobBench's weighted score, scaled to 0..1.

    Note the judge *also* emits a `normalized_score` inside its scorecard, but
    that one is per-run and rounded to 4dp; recomputing from the totals keeps
    this shim independent of judge internals.
    """
    max_score = float(details.get("max_score", 0) or 0)
    total_score = float(details.get("total_score", 0) or 0)
    return total_score / max_score if max_score > 0 else 0.0


def write_outputs(
    *,
    verifier_dir: Path,
    details: dict,
    status: str,
    args: argparse.Namespace,
) -> float:
    verifier_dir.mkdir(parents=True, exist_ok=True)

    normalized = normalize(details)
    passed = int(details.get("passed_count", 0) or 0)
    total = int(details.get("total_count", 0) or 0)
    infra = count_infra_failures(details)

    # `reward` is the key Harbor reads. The rest are carried along as extra
    # metrics so per-metric aggregation still works downstream.
    rewards = {
        "reward": normalized,
        "jobbench_total_score": float(details.get("total_score", 0) or 0),
        "jobbench_max_score": float(details.get("max_score", 0) or 0),
        "jobbench_rubrics_passed": passed,
        "jobbench_rubrics_total": total,
        "jobbench_judge_failures": infra,
        f"jobbench_task::{args.task_id}": normalized,
    }
    (verifier_dir / "reward.json").write_text(
        json.dumps(rewards, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    # reward.txt is redundant while reward.json exists, but keeping both makes
    # the directory self-describing if someone deletes one.
    (verifier_dir / "reward.txt").write_text(f"{normalized:.12g}\n", encoding="utf-8")

    report = {
        "task_id": args.task_id,
        "profession": args.profession,
        "status": status,
        "evaluated_model": args.evaluated_model,
        "judge_model": args.judge_model,
        "total_score": details.get("total_score", 0),
        "max_score": details.get("max_score", 0),
        "normalized_score": normalized,
        "passed_count": passed,
        "total_count": total,
        "judge_failures": infra,
        "rubrics": details.get("rubrics", []),
    }
    (verifier_dir / "jobbench_result.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return normalized


def main() -> int:
    args = parse_args()
    items = load_rubric_items(args.rubrics)
    VERIFIER_DIR.mkdir(parents=True, exist_ok=True)

    details_path = VERIFIER_DIR / "judge.json"

    # Empty submission: do not spend judge calls on nothing, and do not let the
    # judge's own error handling decide the score.
    if not has_submission(args.output_dir):
        details = {
            "evaluated_model": args.evaluated_model,
            "judge_model": args.judge_model,
            "total_score": 0,
            "max_score": sum(float(i.get("weight", 0)) for i in items),
            "passed_count": 0,
            "total_count": len(items),
            "rubrics": [],
        }
        details_path.write_text(json.dumps(details, indent=2) + "\n", encoding="utf-8")
        write_outputs(verifier_dir=VERIFIER_DIR, details=details, status="empty_output", args=args)
        return 0

    detail_dir = VERIFIER_DIR / "judge_details"
    detail_prefix = args.task_id.replace("/", "__")

    command = [
        sys.executable,
        str(args.judge),
        "--output-dir",
        str(args.output_dir),
        "--rubrics-file",
        str(args.rubrics),
        "--details-file",
        str(details_path),
        "--judge-model",
        args.judge_model,
        "--max-workers",
        str(args.max_workers),
        "--max-retries",
        str(args.max_retries),
        "--timeout-per-rubric",
        str(args.timeout_per_rubric),
        "--evaluated-model",
        args.evaluated_model,
        "--detail-log-dir",
        str(detail_dir),
        "--detail-log-prefix",
        detail_prefix,
    ]

    # Credentials come from the environment (set via task.toml [verifier.env]),
    # never from argv — argv shows up in `ps`.
    proc = subprocess.run(command, env=os.environ.copy(), check=False)

    if proc.returncode != 0 or not details_path.is_file():
        # Fail loudly but still leave a valid reward file, so Harbor records a
        # scored trial instead of an opaque crash.
        details = {
            "evaluated_model": args.evaluated_model,
            "judge_model": args.judge_model,
            "error": f"judge exited {proc.returncode}",
            "total_score": 0,
            "max_score": sum(float(i.get("weight", 0)) for i in items),
            "passed_count": 0,
            "total_count": len(items),
            "rubrics": [],
        }
        details_path.write_text(json.dumps(details, indent=2) + "\n", encoding="utf-8")
        write_outputs(verifier_dir=VERIFIER_DIR, details=details, status="judge_failed", args=args)
        return 1

    details = json.loads(details_path.read_text(encoding="utf-8"))
    status = "judge_failed" if count_infra_failures(details) else "ok"
    write_outputs(verifier_dir=VERIFIER_DIR, details=details, status=status, args=args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
