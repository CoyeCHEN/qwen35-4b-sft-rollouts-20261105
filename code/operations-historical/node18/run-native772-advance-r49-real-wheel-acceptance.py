"""Same Ceph owner lock, finite real Wheel acceptance and SSD evidence custody."""

import fcntl
import importlib
import json
import os
from pathlib import Path
import socket
import time

previous = importlib.import_module("run-native772-advance-r48-ssd-preservation")
native = previous.base
phase = importlib.import_module("reliability-ssd-and-wheel-acceptance18-r9")
R, C, B, D = previous.R, previous.C, previous.B, previous.D
UNIT = "qwen35-772-native-advance-node18-20261103-r49-real-wheel-acceptance.service"


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
        for name, digest in native.read(B / "EXECUTION_RELEASE_R25.json")[
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
            deployment_revision="r49-real-wheel-and-ssd-acceptance",
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
                status="ACTUAL_WHEEL_AND_SSD_ACCEPTANCE",
                new_common30_model_admission=False,
                formal_ready=False,
                new212_admission=False,
                old801_disabled=True,
                legacy_recovery_operational_hold=True,
                closed_legacy_jobs_not_redispatched=True,
                runtime_injection_prohibited=True,
                backend17_status="EXACT_IMAGE_SOURCE_AND_NATIVE_SOCKET_PREPARATION_IN_PROGRESS",
            )
            if (R / "checks/NATIVE_ADVANCE_R49_HANDOFF_COMPLETED.json").exists():
                for name, operation in [
                    (
                        "archive_observation",
                        lambda: previous.archive_observation(state),
                    ),
                    (
                        "operator_readout",
                        lambda: previous.terminal_readout(owner, state),
                    ),
                    ("finite_acceptance", lambda: phase.advance(owner, state)),
                ]:
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
