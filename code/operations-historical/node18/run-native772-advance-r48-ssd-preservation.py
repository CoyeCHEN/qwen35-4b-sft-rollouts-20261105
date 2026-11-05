"""Continue the existing sole owner, preserving legacy jobs and host evidence."""

import fcntl
import importlib
import json
import os
from pathlib import Path
import socket
import time

base = importlib.import_module("run-native772-advance-r47-summary-and-m1e3-cold-r2")
R, C, B = base.R, base.C, base.B
D = R / "reliability-repair"
NEW_UNIT = "qwen35-772-native-advance-node18-20261103-r48-ssd-preservation.service"


def cold_gpu5(owner, state):
    folder = D / "cold-m1e3-gpu5-r2"
    worker = folder / "cold_m1e3_gpu5_only_native18_r2.py"
    plan = folder / "COLD_GPU5_ONLY_PLAN_R2.json"
    if (
        base.sha(worker)
        != "98ab4e9ed2de64a5be326e06dcd8996568b4eea781d8c079f71991944fc8e83d"
    ):
        raise RuntimeError("Reviewed GPU5 continuation source changed")
    plan_sha = "a5e5297b2ff871caf406236d123bea5e9767ab655fc2b429faa126ccdfb4b6de"
    if base.sha(plan) != plan_sha:
        raise RuntimeError("Reviewed GPU5 plan changed")
    hold = D / "LEGACY_RECOVERY_OPERATIONAL_HOLD_R1.json"
    hold_sha = "29324aef1ec83c783d39670ab335cfdfe1faa4907c2a5bce61146ae53e003c1a"
    if base.sha(hold) != hold_sha or not base.read(hold)["hold"]:
        raise RuntimeError("Explicit legacy dispatch hold is not verified")
    admission = folder / "ROOT_COLD_GPU5_ADMISSION_ACTUAL_R2.json"
    state["cold_gpu5_continuation"] = base.launch(
        "qwen35-reliability-cold-m1e3-gpu5-bootstrap-20261103-r2.service",
        str(worker),
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
            plan_sha256=plan_sha,
            required_evidence=dict(
                legacy_operational_hold=dict(path=str(hold), sha256=hold_sha)
            ),
            model_generation_calls=0,
            task_dispatches=0,
            preserve_gpu0_and_other_six=True,
        ),
        native_python=R / "env/harbor-reliability-r1/bin/python",
    )


def terminal_readout(owner, state):
    folder = D / "long-ab8-r2"
    terminal = folder / "actual-run-r1/NATIVE_DIAGNOSTIC_8_TERMINALS_R2.json"
    if not terminal.exists():
        state["long_ab8_operator_aware_readout"] = (
            "WAITING_REAL_TERMINALS_NO_REDISPATCH"
        )
        return
    actual = base.read(terminal)
    if actual.get("expected") != 8 or actual.get("terminal") != 8:
        state["long_ab8_operator_aware_readout"] = (
            "WAITING_REAL_TERMINALS_NO_REDISPATCH"
        )
        return
    source = folder / "readout-sources-r3"
    reader = source / "read_long_ab8_terminals18_r3.py"
    index = source / "OPERATOR_INTERVENTION_INDEX_R1.json"
    index_sha = "d1b759a5eecdbe4c6d50e07231e1e614caf3d65946f9746e6ce5c5db1f60abca"
    if (
        base.sha(reader)
        != "f0fbc0479e166616cdb03033e94fd0a31dd9fb57ce82463301dfcd10922c9d32"
        or base.sha(index) != index_sha
    ):
        raise RuntimeError("Operator-aware terminal reader identity changed")
    state["long_ab8_operator_aware_readout"] = base.launch(
        "qwen35-reliability-long-ab8-terminal-readout-20261103-r3.service",
        str(reader),
        [
            "--plan",
            str(folder / "DIAGNOSTIC_LONG_AB8_MANIFEST_R2.json"),
            "--plan-sha256",
            "3654c8b6d1ca35e35a95a2836c3a365c4ceeed8d8e87bab5b76cba9164a97128",
            "--worker-output",
            str(folder / "actual-run-r1"),
            "--output-dir",
            str(folder / "qualified-readout-operator-r3"),
            "--operator-intervention-index",
            str(index),
            "--operator-intervention-index-sha256",
            index_sha,
        ],
        folder / "TERMINAL_READOUT_ADMISSION_R3.json",
        owner,
        dict(
            operator_intervention_index_sha256=index_sha,
            model_generation_calls=0,
            raw_result_reward_recorder_modified=False,
            fixed_denominator=8,
        ),
        native_python=R / "env/harbor-reliability-r1/bin/python",
    )


def archive_observation(state):
    folder = D / "raw-spool-preservation-r1"
    state["raw_spool_preservation"] = dict(
        unit=base.props(
            "qwen35-reliability-raw-spool-preservation-20261103-r1.service"
        ),
        source_trial_uuid="023a8e38-79db-4b06-87e3-e29f84303650",
        source_raw_bytes=731008204800,
        destination_node="18",
        destination_mount="/ssd",
        source_paused_at_archival_start=True,
        full_archive_verified=False,
        raw_source_deletion_authorized=False,
    )
    progress = folder / "source-control.jsonl"
    if progress.exists():
        # The finite archival emits at most one small control event per 15s.
        for line in reversed(progress.read_text().splitlines()):
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            state["raw_spool_preservation"]["last_actual_event"] = event
            break
    receipt = folder / "RAW_SPOOL_ARCHIVE_ACCEPTANCE_R1.json"
    if receipt.exists():
        value = base.read(receipt)
        state["raw_spool_preservation"].update(
            full_archive_verified=value["passed"],
            acceptance_path=str(receipt),
            acceptance_sha256=base.sha(receipt),
            native_abort_continuation_required=True,
        )


def main():
    os.environ["RSI_REMOTE_DOCKER_SSH_CONFIG"] = str(
        R / "control-ssh/formal-engine149-mux-r2.conf"
    )
    private = str(D / "native-client-bin-r1")
    os.environ["PATH"] = (
        private
        + ":"
        + ":".join(
            p
            for p in os.environ["PATH"].split(":")
            if p != private and p != str(R / "formal-controller18-client-bin-r1")
        )
    )
    with (C / "unique-native-advance.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        for name, digest in base.read(B / "EXECUTION_RELEASE_R24.json")[
            "source_sha256"
        ].items():
            if base.sha(R / name) != digest:
                raise RuntimeError("Frozen source changed: " + name)
        owner = dict(
            kind="UNIQUE_NATIVE_ADVANCE_NODE18",
            host=socket.gethostname(),
            pid=os.getpid(),
            start_ticks=Path("/proc/self/stat")
            .read_text()
            .rsplit(")", 1)[1]
            .split()[19],
            boot_id=Path("/proc/sys/kernel/random/boot_id").read_text().strip(),
            controller_unit=NEW_UNIT,
            deployment_revision="r48-ssd-preservation-operator-aware",
            started_at=time.time(),
            entry="native_harbor",
            collection_closed=True,
        )
        base.write(C / "NATIVE_ADVANCE_OWNER.json", owner)
        while True:
            started = time.monotonic()
            state = dict(
                at=time.time(),
                owner=owner,
                status="RELIABILITY_REPAIR_AND_SSD_PRESERVATION",
                new_common30_model_admission=False,
                formal_ready=False,
                new212_admission=False,
                old801_disabled=True,
                legacy_recovery_operational_hold=True,
                closed_legacy_jobs_not_redispatched=True,
                runtime_injection_prohibited=True,
            )
            if (R / "checks/NATIVE_ADVANCE_R48_HANDOFF_COMPLETED.json").exists():
                for name, operation in [
                    ("archive", lambda: archive_observation(state)),
                    ("cold_gpu5", lambda: cold_gpu5(owner, state)),
                    ("readout", lambda: terminal_readout(owner, state)),
                ]:
                    try:
                        operation()
                    except Exception as error:
                        state[name + "_blocker"] = repr(error)
            else:
                state["handoff"] = "WAITING_ACTOR_PRESERVATION_RECEIPT"
            state["controller_cycle_seconds"] = time.monotonic() - started
            base.write(C / "NATIVE_ADVANCE_STATUS.json", state)
            print(json.dumps(state), flush=True)
            time.sleep(20)


if __name__ == "__main__":
    main()
