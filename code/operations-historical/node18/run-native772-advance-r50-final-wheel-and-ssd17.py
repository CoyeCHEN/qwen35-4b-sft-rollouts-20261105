"""Continue the same sole owner: full Wheel, Serving and native SSD17 preflight."""

import fcntl
import importlib
import json
import os
from pathlib import Path
import socket
import time

previous = importlib.import_module("run-native772-advance-r49-real-wheel-acceptance")
native = previous.native
R, C, B, D = previous.R, previous.C, previous.B, previous.D
six = importlib.import_module("new-six-serving-acceptance-phase18-r1")
images = importlib.import_module("ssd17-image-preparation-phase18-r1")
ssd17 = importlib.import_module("ssd17-native-two-step-phase18-r1")
UNIT = "qwen35-772-native-advance-node18-20261103-r50-final-wheel-and-ssd17.service"


def cli(owner, state):
    folder = D / "full-wheel-cli-context-source-r6"
    actual = folder / "ROOT_REGISTRATION_ACTUAL_R6.json"
    digest = previous.phase.registered(
        folder / "ROOT_REGISTRATION_TEMPLATE_R6.json", actual, owner
    )
    state["full_wheel_cli_acceptance"] = native.launch(
        "qwen35-reliability-full-wheel-cli-context-20261103-r6.service",
        str(folder / "run_full_wheel_cli_context_r6.py"),
        [
            "--wheel",
            str(
                D
                / "artifacts-r5/open_harness_ai-0.3.0+rsi.reliability.20261103.5-py3-none-any.whl"
            ),
            "--wheel-sha256",
            "5811dd31e800cc68278073e346dce6b3b6bbe7701e6f44cd084946778d10d279",
            "--output",
            str(D / "full-wheel-cli-context-r6"),
            "--root-registration",
            str(actual),
            "--root-registration-sha256",
            digest,
            "--execute-registered",
        ],
        folder / "ROOT_LAUNCH_ADMISSION_R6.json",
        owner,
        dict(
            scripted_fixture_only=True,
            model_generation_calls=0,
            official_task_or_Verifier_calls=0,
            failed_fixture_R5_preserved=True,
        ),
        native_python=R / "env/harbor-reliability-r1/bin/python",
    )


def main():
    private = str(D / "native-client-bin-r1")
    os.environ["RSI_REMOTE_DOCKER_SSH_CONFIG"] = str(
        R / "control-ssh/formal-engine149-mux-r2.conf"
    )
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
        for name, digest in native.read(B / "EXECUTION_RELEASE_R26.json")[
            "source_sha256"
        ].items():
            if native.sha(R / name) != digest:
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
            controller_unit=UNIT,
            deployment_revision="r50-final-wheel-and-native-ssd17",
            started_at=time.time(),
            entry="native_harbor",
            collection_closed=True,
        )
        native.write(C / "NATIVE_ADVANCE_OWNER.json", owner)
        while True:
            started = time.monotonic()
            state = dict(
                at=time.time(),
                owner=owner,
                status="ACTUAL_FINAL_WHEEL_AND_NATIVE_SSD17_PREFLIGHT",
                new_common30_model_admission=False,
                formal_ready=False,
                new212_admission=False,
                old801_disabled=True,
                legacy_recovery_operational_hold=True,
                closed_legacy_jobs_not_redispatched=True,
                runtime_injection_prohibited=True,
            )
            if (R / "checks/NATIVE_ADVANCE_R50_HANDOFF_COMPLETED.json").exists():
                operations = [
                    (
                        "archive_observation",
                        lambda: previous.previous.archive_observation(state),
                    ),
                    (
                        "archive_continuation",
                        lambda: previous.phase.archived_native_abort(owner, state),
                    ),
                    ("full_cli", lambda: cli(owner, state)),
                    ("six_serving", lambda: six.advance(owner, state, native.launch)),
                    (
                        "ssd17_images",
                        lambda: images.advance(owner, state, native.launch),
                    ),
                    (
                        "ssd17_native",
                        lambda: ssd17.advance(owner, state, native.launch),
                    ),
                ]
                for name, operation in operations:
                    try:
                        operation()
                    except Exception as error:
                        state[name + "_blocker"] = repr(error)
            else:
                state["handoff"] = "WAITING_ACTOR_PRESERVATION_RECEIPT"
            state["controller_cycle_seconds"] = time.monotonic() - started
            native.write(C / "NATIVE_ADVANCE_STATUS.json", state)
            print(json.dumps(state), flush=True)
            time.sleep(20)


if __name__ == "__main__":
    main()
