"""Native cold deployment, bounded summary verification and terminal-only readout."""

import importlib

base = importlib.import_module("reliability-cold-serving18-r4")
R, C, D = base.R, base.C, base.D
NATIVE_PYTHON = R / "env/harbor-reliability-r1/bin/python"


def cold(owner, state, launch):
    folder = D / "cold-m1e3-gpu05-r1"
    worker, plan = (
        folder / "cold_m1e3_gpu05_native18_r1.py",
        folder / "COLD_M1E3_GPU05_PLAN_R1.json",
    )
    plan_sha = "187eb13246e26ec8b1e6e139b21f77d9301d021bd02f60159abc7139cb3d4b49"
    if (
        base.sha(worker)
        != "16553ea334bf914a90a4fb5108a4eeb6d475e43472d931c811898ff1d582d3cf"
        or base.sha(plan) != plan_sha
    ):
        raise RuntimeError("Registered two-replica cold deployment differs")
    admission, output = (
        folder / "ROOT_COLD_ADMISSION_ACTUAL_R1.json",
        folder / "actual-run-r1",
    )
    state["repaired_m1e3_gpu05_bootstrap"] = launch(
        "qwen35-reliability-cold-m1e3-gpu05-bootstrap-20261103-r1.service",
        str(worker),
        [
            "--plan",
            str(plan),
            "--admission",
            str(admission),
            "--output-dir",
            str(output),
        ],
        admission,
        owner,
        dict(
            plan_path=str(plan),
            plan_sha256=plan_sha,
            only_gpu_indices=[0, 5],
            preserve_six_other_services=True,
            fresh_native_lease_check_required=True,
            model_generation_calls=0,
            task_dispatches=0,
        ),
        native_python=NATIVE_PYTHON,
    )
    receipt = output / "COLD_M1E3_GPU05_LAUNCHED_R1.json"
    if receipt.exists():
        value = base.read(receipt)
        state["repaired_m1e3_gpu05_launch"] = dict(
            path=str(receipt),
            sha256=base.sha(receipt),
            replicas=len(value["replicas"]),
            independent_counter_and_serving_acceptance_pending=True,
        )


def summary(owner, state, launch):
    folder = D / "p2-aux-real-generation-source-r2"
    worker, plan = (
        folder / "run_auxiliary_summary_canary_r1.py",
        folder / "AUXILIARY_SUMMARY_12_CASE_PLAN_R2.json",
    )
    registration = folder / "ROOT_REGISTRATION_ACTUAL_R2.json"
    worker_sha = "98d0441ba82a62d23a342c5fe7d09ce941b4592b47da6049fd6ac4736e608213"
    plan_sha = "9a9aaf0d547fc4cb7f1f0805f4bac20996e662195c76076098f1704deff0c6ad"
    registration_sha = (
        "2e0bfb53b065377527e4897f020308c710c151c8d64b8c985a8403a725066b1c"
    )
    if (
        base.sha(worker) != worker_sha
        or base.sha(plan) != plan_sha
        or base.sha(registration) != registration_sha
    ):
        raise RuntimeError(
            "Independent same-context summary instruction comparison differs"
        )
    state["summary_new_prompt_diagnostics"] = launch(
        "qwen35-reliability-summary-new-prompt-12case-20261103-r2.service",
        str(worker),
        [
            "--plan",
            str(plan),
            "--plan-sha256",
            plan_sha,
            "--worker-sha256",
            worker_sha,
            "--root-registration",
            str(registration),
            "--root-registration-sha256",
            registration_sha,
            "--execute-registered",
        ],
        folder / "ROOT_LAUNCH_ADMISSION_R2.json",
        owner,
        dict(
            plan_path=str(plan),
            plan_sha256=plan_sha,
            logical_cases=12,
            maximum_generation_attempts=64,
            output_budget_per_case=16384,
            max_active_requests=2,
            total_wall_seconds=1800,
            main_output_budget=81920,
            new_harness_wheel_sha256="314cdee07bbc4f1fd6aeff2281317f9d21ae9a80e5b66688b4cbe821b37f7a6f",
            task_dispatches=0,
            verifier_calls=0,
        ),
        native_python=NATIVE_PYTHON,
    )
    folder = D / "p2-auxiliary-summary-canary-16k-prompt-r2"
    progress, result = (
        folder / "PROGRESS_R1.json",
        folder / "AUXILIARY_SUMMARY_CANARY_RESULT_R1.json",
    )
    if progress.exists():
        value = base.read(progress)
        state["summary_new_prompt_progress"] = dict(
            completed=value["completed_logical_cases"],
            generation_http_attempts=value["generation_requests"],
        )
    if result.exists():
        value = base.read(result)
        state["summary_new_prompt_result"] = dict(
            path=str(result),
            sha256=base.sha(result),
            terminal=value["logical_cases_terminal"],
            run_complete=value["run_complete"],
            mechanical_body_pass=value["all_logical_cases_have_valid_body"],
            semantic_acceptance_not_inferred_from_body=True,
        )


def readout(owner, state, launch):
    folder = D / "long-ab8-r2"
    terminal = folder / "actual-run-r1/NATIVE_DIAGNOSTIC_8_TERMINALS_R2.json"
    if not terminal.exists() or base.read(terminal)["terminal"] != 8:
        state["long_ab8_terminal_qualification"] = dict(
            status="WAITING_EIGHT_NATIVE_TERMINALS"
        )
        return
    source = folder / "readout-sources-r2/read_long_ab8_terminals18_r2.py"
    if (
        base.sha(source)
        != "206b71a368428bd47dac768a02e32057173073e8e8e00eda3c9c37e69c670d7a"
    ):
        raise RuntimeError("Fixed-Wheel terminal-only reader differs")
    state["long_ab8_terminal_qualification"] = launch(
        "qwen35-reliability-long-ab8-terminal-readout-20261103-r2.service",
        str(source),
        [
            "--plan",
            str(folder / "DIAGNOSTIC_LONG_AB8_MANIFEST_R2.json"),
            "--plan-sha256",
            "3654c8b6d1ca35e35a95a2836c3a365c4ceeed8d8e87bab5b76cba9164a97128",
            "--worker-output",
            str(folder / "actual-run-r1"),
            "--output-dir",
            str(folder / "qualified-terminal-readout-r1"),
        ],
        folder / "TERMINAL_READOUT_ADMISSION_R2.json",
        owner,
        dict(
            expected_wheel_sha256="4b9c4b72a0c18e64ff79caf6e5d7386bfe7bdeb4373b228efe4db5ae0ed3422e",
            all_eight_real_terminal_results_required=True,
            model_generation_calls=0,
        ),
        native_python=NATIVE_PYTHON,
    )


def advance(owner, state, launch):
    if base.read(C / "NATIVE_ADVANCE_OWNER.json") != owner:
        raise RuntimeError(
            "Only the unique controller may admit these finite operations"
        )
    if not (R / "checks/NATIVE_ADVANCE_R47_HANDOFF_COMPLETED.json").exists():
        state["summary_and_m1e3_acceptance"] = "WAITING_CONTROLLED_HANDOFF"
        return
    for name, operation in [("cold", cold), ("summary", summary), ("readout", readout)]:
        try:
            operation(owner, state, launch)
        except Exception as error:
            state["reliability_r47_" + name + "_blocker"] = repr(error)
    state["new212_protocol_gate"] = dict(
        admission=False,
        formal_ready=False,
        independent_summary_semantics_and_task_qualification_required=True,
    )


if __name__ == "__main__":
    raise SystemExit("Only the original unique controller may advance acceptance")
