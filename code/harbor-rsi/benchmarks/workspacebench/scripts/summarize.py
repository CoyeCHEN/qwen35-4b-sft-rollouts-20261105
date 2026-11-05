from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
from typing import Any


Json = Any


def read_json(path: Path) -> Json:
    return json.loads(path.read_text(encoding="utf-8"))


def first_judge_file(task_dir: Path, judge_model: str | None) -> Path | None:
    files = sorted(task_dir.glob("rubrics_judge--*.json"))
    if judge_model:
        preferred = task_dir / f"rubrics_judge--{judge_model}.json"
        if preferred.is_file():
            return preferred
    return files[0] if files else None


def int_or_zero(value: Json) -> int:
    return int(value) if isinstance(value, int) and not isinstance(value, bool) else 0


def file_record(path: Path, *, root: Path) -> dict[str, Json] | None:
    if not path.is_file():
        return None
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    rel = path.resolve().relative_to(root.resolve()).as_posix()
    return {
        "path": str(path),
        "relative_path": rel,
        "size_bytes": path.stat().st_size,
        "sha256": h.hexdigest(),
    }


def collect_task_artifacts(
    task_dir: Path, *, judge_model: str | None, run_dir: Path
) -> dict[str, Json]:
    raw = task_dir / "raw"
    names = {
        "agent_json": task_dir / "agent.json",
        "agent_log": task_dir / "agent.log",
        "metadata_json": task_dir / "metadata.json",
        "runner_report": run_dir / "agent_runner_report.json",
        "openharness_jsonl": raw / "openharness_stdout.jsonl",
        "openharness_stderr": raw / "openharness_stderr.log",
        "openharness_stdout": raw / "stdout.txt",
        "openharness_stderr_text": raw / "stderr.txt",
        "openharness_config": raw / "openharness_config.json",
        "openharness_invocation": raw / "openharness_invocation.json",
        "install_stdout": raw / "openharness_install_stdout.txt",
        "install_stderr": raw / "openharness_install_stderr.txt",
        "misplaced_outputs": raw / "misplaced_outputs.json",
    }
    judge_path = first_judge_file(task_dir, judge_model)
    if judge_path is not None:
        names["rubrics_judge"] = judge_path
    dep_files = sorted(task_dir.glob("dependency_graph--*.json"))
    if dep_files:
        names["dependency_graph"] = dep_files[0]
    records = {
        key: rec
        for key, path in names.items()
        if (rec := file_record(path, root=run_dir))
    }
    output_records: list[dict[str, Json]] = []
    output_dir = task_dir / "output"
    if output_dir.is_dir():
        for path in sorted(p for p in output_dir.rglob("*") if p.is_file()):
            rec = file_record(path, root=run_dir)
            if rec:
                output_records.append(rec)
    return {"files": records, "outputs": output_records}


def summarize(run_dir: Path, *, judge_model: str | None) -> dict[str, Json]:
    task_rows: list[dict[str, Json]] = []
    trajectory_rows: list[dict[str, Json]] = []
    totals: dict[str, Json] = {
        "tasks": 0,
        "agent_passed": 0,
        "agent_failed": 0,
        "agent_error": 0,
        "agent_timeout": 0,
        "rubrics_total": 0,
        "rubrics_passed": 0,
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
    }
    for task_dir in sorted(
        [p for p in run_dir.iterdir() if p.is_dir()], key=lambda p: p.name
    ):
        agent_path = task_dir / "agent.json"
        metadata_path = task_dir / "metadata.json"
        if not agent_path.is_file() or not metadata_path.is_file():
            continue
        totals["tasks"] += 1
        agent = read_json(agent_path)
        meta = read_json(metadata_path)
        status = str(agent.get("status") or "unknown")
        if status in {"passed", "failed", "error", "timeout"}:
            totals[f"agent_{status}"] += 1
        usage = ((agent.get("trace") or {}).get("llm") or {}).get("usageTotal")
        if not isinstance(usage, dict):
            usage = {}
        prompt_tokens = int_or_zero(agent.get("promptTokens")) or int_or_zero(
            usage.get("prompt_tokens")
        )
        completion_tokens = int_or_zero(agent.get("completionTokens")) or int_or_zero(
            usage.get("completion_tokens")
        )
        total_tokens = int_or_zero(agent.get("totalTokens")) or int_or_zero(
            usage.get("total_tokens")
        )
        totals["prompt_tokens"] += prompt_tokens
        totals["completion_tokens"] += completion_tokens
        totals["total_tokens"] += total_tokens

        judge_path = first_judge_file(task_dir, judge_model)
        rubrics_total = 0
        rubrics_passed = 0
        judge_error = None
        if judge_path is not None:
            judge = read_json(judge_path)
            summary = (
                judge.get("summary") if isinstance(judge.get("summary"), dict) else {}
            )
            rubrics_total = int_or_zero(summary.get("total"))
            rubrics_passed = int_or_zero(summary.get("passed"))
            judge_obj = (
                judge.get("judge") if isinstance(judge.get("judge"), dict) else {}
            )
            if isinstance(judge_obj.get("error"), str):
                judge_error = judge_obj["error"]
        totals["rubrics_total"] += rubrics_total
        totals["rubrics_passed"] += rubrics_passed
        task_id = str(meta.get("id") or task_dir.name)
        artifacts = collect_task_artifacts(
            task_dir, judge_model=judge_model, run_dir=run_dir
        )
        trace_files = artifacts["files"]
        outputs = artifacts["outputs"]
        row = {
            "task_id": task_id,
            "language": meta.get("language"),
            "persona": meta.get("persona"),
            "job": meta.get("job"),
            "difficulty": meta.get("task_diff"),
            "agent_status": status,
            "runner_status": agent.get("runnerStatus"),
            "rubrics_passed": rubrics_passed,
            "rubrics_total": rubrics_total,
            "rubric_pass_rate": (rubrics_passed / rubrics_total)
            if rubrics_total
            else None,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
            "duration_ms": agent.get("durationMs"),
            "turns": agent.get("turns"),
            "output_count": len(outputs),
            "output_bytes": sum(int(x.get("size_bytes") or 0) for x in outputs),
            "agent_json": trace_files.get("agent_json", {}).get("relative_path"),
            "openharness_jsonl": trace_files.get("openharness_jsonl", {}).get(
                "relative_path"
            ),
            "openharness_jsonl_sha256": trace_files.get("openharness_jsonl", {}).get(
                "sha256"
            ),
            "judge_file": str(judge_path) if judge_path else None,
            "judge_file_sha256": trace_files.get("rubrics_judge", {}).get("sha256"),
            "judge_error": judge_error,
        }
        task_rows.append(row)
        trajectory_rows.append(
            {
                "task_id": task_id,
                "task_dir": str(task_dir),
                "artifacts": artifacts,
            }
        )
    totals["rubric_pass_rate"] = (
        totals["rubrics_passed"] / totals["rubrics_total"]
        if totals["rubrics_total"]
        else None
    )
    return {
        "run_dir": str(run_dir),
        "summary": totals,
        "tasks": task_rows,
        "trajectory_index": trajectory_rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--judge-model")
    parser.add_argument("--tasks-csv")
    parser.add_argument("--trajectory-index")
    args = parser.parse_args()
    run_dir = Path(args.run_dir).resolve()
    data = summarize(run_dir, judge_model=args.judge_model)
    out = Path(args.out).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    csv_path = (
        Path(args.tasks_csv).resolve() if args.tasks_csv else out.with_name("tasks.csv")
    )
    index_path = (
        Path(args.trajectory_index).resolve()
        if args.trajectory_index
        else out.with_name("trajectory-index.json")
    )
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    index_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = sorted({k for row in data["tasks"] for k in row.keys()})
    with csv_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(data["tasks"])
    index_path.write_text(
        json.dumps(
            {
                "run_dir": data["run_dir"],
                "summary": data["summary"],
                "tasks": data["trajectory_index"],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(json.dumps(data["summary"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
