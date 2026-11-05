"""Finite repaired-Wheel acceptance, isolated from model evaluation admission."""

import importlib
from pathlib import Path
import subprocess

base = importlib.import_module("run-native772-advance-r48-ssd-preservation")
R, C, D = base.R, base.C, base.D
PYTHON = R / "env/harbor-reliability-r1/bin/python"


def registered(template_path, actual_path, owner):
    expected = base.base.read(template_path)
    if not actual_path.exists():
        value = dict(
            expected,
            authorized_by_unique_controller=True,
            prepared_only=False,
            owner=owner,
        )
        base.base.write(actual_path, value)
    actual = base.base.read(actual_path)
    if any(
        actual.get(key) != value
        for key, value in expected.items()
        if key not in {"owner", "authorized_by_unique_controller", "prepared_only"}
    ):
        raise RuntimeError("Persisted finite registration differs; never replace it")
    if actual.get("authorized_by_unique_controller") is not True:
        raise RuntimeError("Finite operation has no sole-owner authorization")
    return base.base.sha(actual_path)


def cli(owner, state):
    folder = D / "full-wheel-cli-context-source-r5"
    source = folder / "run_full_wheel_cli_context_r5.py"
    template = folder / "ROOT_REGISTRATION_TEMPLATE_R5.json"
    actual = folder / "ROOT_REGISTRATION_ACTUAL_R5.json"
    registration_sha = registered(template, actual, owner)
    state["full_wheel_cli_acceptance"] = base.base.launch(
        "qwen35-reliability-full-wheel-cli-context-20261103-r5.service",
        str(source),
        [
            "--wheel",
            str(
                D
                / "artifacts-r5/open_harness_ai-0.3.0+rsi.reliability.20261103.5-py3-none-any.whl"
            ),
            "--wheel-sha256",
            "5811dd31e800cc68278073e346dce6b3b6bbe7701e6f44cd084946778d10d279",
            "--output",
            str(D / "full-wheel-cli-context-r5"),
            "--root-registration",
            str(actual),
            "--root-registration-sha256",
            registration_sha,
            "--execute-registered",
        ],
        folder / "ROOT_LAUNCH_ADMISSION_R5.json",
        owner,
        dict(
            scripted_fixture_only=True,
            model_generation_calls=0,
            official_task_or_Verifier_calls=0,
        ),
        native_python=PYTHON,
    )


def projection(owner, state):
    folder = D / "context-projection-counter-source-r5"
    actual = folder / "ROOT_REGISTRATION_ACTUAL_R5.json"
    registration_sha = registered(
        folder / "ROOT_REGISTRATION_TEMPLATE_R5.json", actual, owner
    )
    state["actual_history_projection_count"] = base.base.launch(
        "qwen35-reliability-history-projection-count-20261103-r5.service",
        str(folder / "run_projection_count_only_r5.py"),
        [
            "--plan",
            str(folder / "CONTEXT_PROJECTION_COUNT_PLAN_R5.json"),
            "--plan-sha256",
            "8e8218ad74770020332d0b597a1b99d99538ddb70954a39569eddc399fdfdde7",
            "--root-registration",
            str(actual),
            "--root-registration-sha256",
            registration_sha,
            "--execute-registered",
        ],
        folder / "ROOT_LAUNCH_ADMISSION_R5.json",
        owner,
        dict(
            max_count_only_requests=8,
            model_generation_calls=0,
            official_task_or_Verifier_calls=0,
        ),
        native_python=PYTHON,
    )


def archived_native_abort(owner, state):
    receipt = D / "raw-spool-preservation-r1/RAW_SPOOL_ARCHIVE_ACCEPTANCE_R1.json"
    if not receipt.exists():
        state["archived_native_abort"] = "WAITING_FULL_INDEPENDENT_DECODE_AND_SHA"
        return
    value = base.base.read(receipt)
    if (
        value.get("passed") is not True
        or value.get("independent_full_decode_sha_verified") is not True
    ):
        raise RuntimeError("Incomplete archive cannot release the paused source")
    admission = (
        D / "raw-spool-preservation-r1/ROOT_NATIVE_ABORT_CONTINUATION_ADMISSION_R1.json"
    )
    state["archived_native_abort"] = base.base.launch(
        "qwen35-reliability-archived-native-abort-continuation-20261103-r1.service",
        str(D / "continue-owned-native-abort-after-archive18-r1.py"),
        [
            "--archive-acceptance",
            str(receipt),
            "--admission",
            str(admission),
            "--output-dir",
            str(D / "raw-spool-preservation-r1/native-abort-continuation-r1"),
        ],
        admission,
        owner,
        dict(
            archive_acceptance_sha256=base.base.sha(receipt),
            model_or_Verifier_calls=0,
            raw_source_not_deleted_or_truncated=True,
            official_results_not_modified=True,
        ),
        native_python=PYTHON,
    )


def cold_gpu5(owner, state, deployment):
    item = deployment["gpu5_continuation"]
    source, plan = Path(item["source"]), Path(item["plan"])
    if (
        base.base.sha(source) != item["source_sha256"]
        or base.base.sha(plan) != item["plan_sha256"]
    ):
        raise RuntimeError("GPU5 R3 source or deployment plan differs")
    folder = plan.parent
    admission = folder / "ROOT_COLD_GPU5_ADMISSION_ACTUAL_R3.json"
    hold = D / "LEGACY_RECOVERY_OPERATIONAL_HOLD_R1.json"
    state["cold_gpu5_continuation"] = base.base.launch(
        "qwen35-reliability-cold-m1e3-gpu5-bootstrap-20261103-r3.service",
        str(source),
        [
            "--plan",
            str(plan),
            "--admission",
            str(admission),
            "--output-dir",
            str(folder / "actual-run-r1"),
        ],
        admission,
        owner,
        dict(
            plan_sha256=item["plan_sha256"],
            required_evidence=dict(
                legacy_operational_hold=dict(
                    path=str(hold),
                    sha256="29324aef1ec83c783d39670ab335cfdfe1faa4907c2a5bce61146ae53e003c1a",
                )
            ),
            model_generation_calls=0,
            task_dispatches=0,
            preserve_gpu0_and_other_six=True,
        ),
        native_python=PYTHON,
    )


def cold_four(owner, state, deployment):
    item = deployment["four_checkpoint_continuation"]
    source, plan_path = Path(item["source"]), Path(item["plan"])
    if (
        base.base.sha(source) != item["source_sha256"]
        or base.base.sha(plan_path) != item["plan_sha256"]
    ):
        raise RuntimeError("Four checkpoint source or plan differs")
    plan = base.base.read(plan_path)
    receipt = Path(plan["gpu5_receipt_path"])
    worker_unit = "qwen35-reliability-cold-m1e3-gpu5-bootstrap-20261103-r3.service"
    status = base.base.props(worker_unit)
    if (
        not receipt.exists()
        or status["MainPID"] != "0"
        or status["ActiveState"] != "inactive"
        or status["Result"] != "success"
    ):
        state["cold_four_continuation"] = "WAITING_NATIVE_GPU5_R3_COMPLETION"
        return
    binding = plan["new_gpu5_binding"]
    unit = binding["unit"]
    target = base.base.props(unit)
    if target["ActiveState"] != "active" or int(target["MainPID"]) <= 0:
        state["cold_four_continuation"] = "WAITING_NEW_GPU5_PROCESS"
        return
    # The worker rechecks all of these facts before each native service stop.
    model = importlib.import_module("reliability-cold-serving18-r4").get(
        binding["port"], "/model_info"
    )
    if (
        model["model_path"] != binding["model_path"]
        or model["weight_version"] != binding["weight_version"]
    ):
        raise RuntimeError("Actual GPU5 model identity differs")
    pid = int(target["MainPID"])
    process = dict(
        unit=unit,
        pid=pid,
        start_ticks=(Path("/proc") / str(pid) / "stat")
        .read_text()
        .rsplit(")", 1)[1]
        .split()[19],
        control_group=subprocess.check_output(
            ["systemctl", "--user", "show", unit, "-p", "ControlGroup", "--value"],
            text=True,
            timeout=5,
        ).strip(),
        gpu_uuid=binding["gpu_uuid"],
    )
    hold = D / "LEGACY_RECOVERY_OPERATIONAL_HOLD_R1.json"
    admission = plan_path.parent / "ROOT_COLD_FOUR_ADMISSION_ACTUAL_R2.json"
    state["cold_four_continuation"] = base.base.launch(
        "qwen35-reliability-cold-four-checkpoint-bootstrap-20261103-r2.service",
        str(source),
        [
            "--plan",
            str(plan_path),
            "--admission",
            str(admission),
            "--output-dir",
            str(plan_path.parent / "actual-run-r1"),
            "--apply",
        ],
        admission,
        owner,
        dict(
            plan_sha256=item["plan_sha256"],
            required_evidence=dict(
                legacy_operational_hold=dict(
                    path=str(hold),
                    sha256="29324aef1ec83c783d39670ab335cfdfe1faa4907c2a5bce61146ae53e003c1a",
                ),
                gpu5_new_receipt=dict(path=str(receipt), sha256=base.base.sha(receipt)),
                gpu5_new_process_identity=process,
                gpu5_worker_unit=worker_unit,
            ),
            model_generation_calls=0,
            task_dispatches=0,
            targets=[1, 4, 6, 7],
            preserve_gpu0_gpu2_gpu3_gpu5=True,
        ),
        native_python=PYTHON,
    )


def advance(owner, state):
    if base.base.read(C / "NATIVE_ADVANCE_OWNER.json") != owner:
        raise RuntimeError("Only the original sole owner may admit finite acceptance")
    deployment = base.base.read(D / "R49_ACCEPTANCE_DEPLOYMENT_R1.json")
    for name, operation in [
        ("cli", lambda: cli(owner, state)),
        ("projection", lambda: projection(owner, state)),
        ("archive", lambda: archived_native_abort(owner, state)),
        ("gpu5", lambda: cold_gpu5(owner, state, deployment)),
        ("four", lambda: cold_four(owner, state, deployment)),
    ]:
        try:
            operation()
        except Exception as error:
            state["reliability_r49_" + name + "_blocker"] = repr(error)
    state["formal_ready"] = False
    state["new212_admission"] = False
