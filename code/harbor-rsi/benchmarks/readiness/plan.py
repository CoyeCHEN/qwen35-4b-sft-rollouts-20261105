"""Export native configs and a deterministic, unexecuted paid sampling proposal."""

import argparse
import csv
import hashlib
from pathlib import Path
from statistics import mean
from typing import Any

from benchmarks.readiness.audit import COUNTS, job_config, write_json
from harbor.models.job.config import JobConfig
from harbor.models.task.task import Task

SEED = "20261014"
WHEEL_SHA256 = "09c874a34f985266548292ee17acc234f30cda4b850d0b492df2c55cd4656f1f"


def agent(wheel: Path) -> dict[str, Any]:
    return {
        "import_path": "harbor.agents.installed.open_harness:OpenHarnessAgent",
        "model_name": "deepseek/deepseek-flash",
        "kwargs": {
            "wheel_path": str(wheel),
            "wheel_sha256": WHEEL_SHA256,
            "profile": "native-cli-v1",
            "max_tokens": 65536,
            "thinking": "high",
        },
        "env": {"DEEPSEEK_API_KEY": "${DEEPSEEK_API_KEY}"},
    }


def paid_config(benchmark: str, directory: Path, wheel: Path) -> dict[str, Any]:
    config = job_config(benchmark, directory)
    config["job_name"] = f"full-evaluation-{benchmark}"
    config["jobs_dir"] = "jobs/full-evaluation"
    config["agents"] = [agent(wheel)]
    if benchmark.startswith("jobbench"):
        config["verifier"] = {
            "env": {
                "JOBBENCH_EVALUATED_MODEL": "deepseek-flash",
                "JUDGE_MODEL": "deepseek-flash",
                "JUDGE_API_KEY": "${DEEPSEEK_API_KEY}",
                "JUDGE_API_BASE": "https://api.deepseek.com/v1",
            }
        }
    if benchmark == "clawgym":
        config["verifier"] = {
            "env": {
                "CLAWGYM_JUDGE_API_KEY": "${DEEPSEEK_API_KEY}",
                "CLAWGYM_JUDGE_BASE_URL": "https://api.deepseek.com/v1",
                "CLAWGYM_JUDGE_MODEL": "deepseek-flash",
            }
        }
    JobConfig.model_validate(config)
    return config


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--wheel", required=True, type=Path)
    args = parser.parse_args()
    if hashlib.sha256(args.wheel.read_bytes()).hexdigest() != WHEEL_SHA256:
        raise ValueError("The proposed installed-agent wheel is not the frozen wheel")
    rows = list(csv.DictReader((args.output / "full-task-manifest.csv").open()))
    previous = list(
        csv.DictReader(
            (
                Path(__file__).resolve().parents[2]
                / "artifacts/benchmark-reports/final-4x10/cases.csv"
            ).open()
        )
    )
    proposals = []
    for benchmark in COUNTS:
        subset = [r for r in rows if r["benchmark"] == benchmark]
        directory = Path(subset[0]["task_path"]).parent
        config = paid_config(benchmark, directory, args.wheel)
        write_json(
            args.output
            / "full-job-configs"
            / f"{benchmark}-open-harness-pending-readiness.json",
            config,
        )
    for benchmark in ["alfworld", "clawgym", "tb21", "jobbench"]:
        candidates = [
            r
            for r in rows
            if (
                r["benchmark"] == benchmark
                or benchmark == "jobbench"
                and r["benchmark"].startswith("jobbench-")
            )
            and r["prior_run"] == "none"
        ]
        ranked = sorted(
            candidates,
            key=lambda r: hashlib.sha256(f"{SEED}|{r['task_id']}".encode()).hexdigest(),
        )
        selected = []
        groups: dict[str, list[dict[str, str]]] = {}
        for r in ranked:
            task = Task(Path(r["task_path"]))
            group = (
                str(task.config.metadata["alfworld_task_type"])
                if benchmark == "alfworld"
                else r["verifier"]
                if benchmark == "clawgym"
                else r["benchmark"]
                if benchmark == "jobbench"
                else "large-memory"
                if (task.config.environment.memory_mb or 0) >= 8192
                else str(task.config.metadata.get("category", "other"))
            )
            groups.setdefault(group, []).append(r)
        if benchmark == "tb21":
            selected.extend(
                r for r in ranked if r["source_task"] == "hf-model-inference"
            )
        if benchmark == "clawgym":
            selected.extend(r for r in ranked if "task-000131-" in r["task_id"])
        if benchmark == "jobbench":
            selected = groups["jobbench-main"][:5] + groups["jobbench-easy"][:5]
        else:
            for members in groups.values():
                if len(selected) < 10 and members[0] not in selected:
                    selected.append(members[0])
            selected.extend(r for r in ranked if r not in selected)
            selected = selected[:10]
        assert len(selected) == 10
        costs = [
            float(r["estimated_cost_usd"])
            for r in previous
            if r["benchmark"] == benchmark and r["estimated_cost_usd"]
        ]
        proposals.append(
            {
                "benchmark": benchmark,
                "count": 10,
                "selection_seed": SEED,
                "rule": "source-category stratification then SHA256(seed|task_id) rank; no readiness/reward-based replacement; JobBench 5 main + 5 easy; TB includes hf-model-inference; Claw includes YAML checker",
                "groups_available": {
                    name: len(members) for name, members in groups.items()
                },
                "tasks": [
                    {
                        k: r[k]
                        for k in [
                            "benchmark",
                            "task_id",
                            "task_hash",
                            "source_revision",
                            "task_path",
                        ]
                    }
                    for r in selected
                ],
                "historical_agent_cost_estimate_usd": 10 * mean(costs)
                if costs
                else None,
                "historical_agent_cost_observed_10x_max_usd": 10 * max(costs)
                if costs
                else None,
                "cost_limit_guarantee": False,
                "judge_sandbox_network_storage_cost": "unknown; authorization and provider quote required",
            }
        )
    write_json(
        args.output / "additional-40-sample-proposal-superseded.json",
        {
            "authorized": False,
            "status": "Original additional-40 proposal; superseded by user's later explicit full-551 authorization. This proposal was never executed.",
            "executed": False,
            "model_judge_calls": 0,
            "source_manifest_sha256": hashlib.sha256(
                (args.output / "full-task-manifest.csv").read_bytes()
            ).hexdigest(),
            "configuration": "same frozen OpenHarness wheel and previous high/65536 settings; freeze Harbor/Provider wheel identities after PR merge and before any paid execution",
            "proposals": proposals,
        },
    )


if __name__ == "__main__":
    main()
