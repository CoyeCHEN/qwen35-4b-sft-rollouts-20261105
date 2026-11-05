"""Twelve registered auxiliary diagnostics, separate from native Task Trials."""

import importlib

base = importlib.import_module("reliability-cold-serving18-r4")
R, C, D = base.R, base.C, base.D
SOURCE = D / "p2-aux-real-generation-source-r1"
PLAN_SHA = "17379509e4e50d09e48380a8ac8f78c8bc9d78a5fc2ecab402a349c77152e796"
WORKER_SHA = "98d0441ba82a62d23a342c5fe7d09ce941b4592b47da6049fd6ac4736e608213"
REGISTRATION_SHA = "7f28f7e5cc4e2c8d309df1bfa4a0d4bdd79364ae9b06a6fd353d5a64a54f154a"


def advance(owner, state, launch):
    if base.read(C / "NATIVE_ADVANCE_OWNER.json") != owner:
        raise RuntimeError("Auxiliary diagnostics require the unique controller")
    if not (R / "checks/NATIVE_ADVANCE_R46_HANDOFF_COMPLETED.json").exists():
        state["auxiliary_summary_diagnostics"] = dict(
            status="WAITING_CONTROLLED_HANDOFF"
        )
        return
    worker, plan = (
        SOURCE / "run_auxiliary_summary_canary_r1.py",
        SOURCE / "AUXILIARY_SUMMARY_12_CASE_PLAN_R1.json",
    )
    registration = SOURCE / "ROOT_REGISTRATION_R1.json"
    if (
        base.sha(worker) != WORKER_SHA
        or base.sha(plan) != PLAN_SHA
        or base.sha(registration) != REGISTRATION_SHA
    ):
        raise RuntimeError("Finite auxiliary diagnostic source or registration changed")
    args = [
        "--plan",
        str(plan),
        "--plan-sha256",
        PLAN_SHA,
        "--worker-sha256",
        WORKER_SHA,
        "--root-registration",
        str(registration),
        "--root-registration-sha256",
        REGISTRATION_SHA,
        "--execute-registered",
    ]
    state["auxiliary_summary_diagnostics"] = launch(
        "qwen35-reliability-auxiliary-summary-12case-20261103-r1.service",
        str(worker),
        args,
        D / "AUXILIARY_SUMMARY_LAUNCH_ADMISSION_R1.json",
        owner,
        dict(
            plan_path=str(plan),
            plan_sha256=PLAN_SHA,
            logical_cases=12,
            maximum_generation_attempts=64,
            output_budget_per_case=16384,
            max_active_requests=2,
            total_wall_seconds=1800,
            task_dispatches=0,
            verifier_calls=0,
            main_output_budget=81920,
        ),
        native_python=R / "env/harbor-reliability-r1/bin/python",
    )
    output = D / "p2-auxiliary-summary-canary-16k-r1"
    progress = output / "PROGRESS_R1.json"
    result = output / "AUXILIARY_SUMMARY_CANARY_RESULT_R1.json"
    if progress.exists():
        value = base.read(progress)
        state["auxiliary_summary_progress"] = dict(
            completed_logical_cases=value["completed_logical_cases"],
            generation_attempts=value["generation_requests"],
        )
    if result.exists():
        value = base.read(result)
        state["auxiliary_summary_result"] = dict(
            path=str(result),
            sha256=base.sha(result),
            run_complete=value["run_complete"],
            terminal=value["logical_cases_terminal"],
            valid_body=value["all_logical_cases_have_valid_body"],
            formal_ready=False,
        )


if __name__ == "__main__":
    raise SystemExit(
        "Only the existing unique controller may launch auxiliary diagnostics"
    )
