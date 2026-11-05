"""Same sole Harbor owner: cached native NOP and independent finite asset work."""

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
ssd17 = importlib.import_module("ssd17-native-nop-recheck-phase18-r5b")
UNIT = "qwen35-772-native-advance-node18-20261103-r54-public-apt-native-nop.service"


def serving_evidence(state):
    path = (
        D
        / "serving-offline-readout-r1/OFFLINE_EIGHTEEN_NATIVE_EVIDENCE_REASSESSMENT_R1.json"
    )
    expected = "9682b171f9d5b045df192f41cdbe762c2bd3106c71f501a55bfb6374b51f1a1d"
    if native.sha(path) != expected:
        raise RuntimeError("Accepted independent Serving readout changed")
    proof = native.read(path)
    if not (
        proof["passed"]
        and proof["completed"] == proof["reliability_passed"] == 18
        and proof["semantic_passed"] == 13
        and proof["additional_model_requests"] == 0
        and proof["additional_count_requests"] == 0
        and proof["formal_ready"] is False
    ):
        raise RuntimeError("Serving-only evidence cannot admit model Task Trials")
    state["final5_serving_offline_acceptance"] = dict(
        path=str(path),
        sha256=expected,
        reliability_passed=18,
        expected=18,
        semantic_passed=13,
        scope="SERVING_ONLY_NOT_AGENT_OR_VERIFIER",
        original_false_results_preserved=True,
        additional_generation_requests=0,
        image_post_processor_ids_independently_observed=False,
    )


def asset_observation(state):
    raw = D / "raw-spool-preservation-r2/PROGRESS_R2.json"
    value = native.read(raw) if raw.exists() else None
    if (
        value
        and value["plan_sha256"]
        != "f91c4e67d94c398aa17799e93f8ad94911452cfa6243458a0baa5c9f608c7b89"
    ):
        raise RuntimeError("Raw preservation progress belongs to another scope")
    state["raw_preservation_r2"] = dict(
        unit=native.props(
            "qwen35-reliability-raw-spool-preservation-chunks-20261103-r2.service"
        ),
        progress=value,
        original_raw_bytes=731008204800,
        full_archive_acceptance_exists=(
            D / "raw-spool-preservation-r2/RAW_CHUNK_ARCHIVE_ACCEPTANCE_R2.json"
        ).exists(),
        source_holder_release_authorized_by_this_controller=False,
        model_generation_calls=0,
    )
    path = D / "ssd17-common29-image-batch-r2/actual-batch-r1/PROGRESS_R2.json"
    value = native.read(path) if path.exists() else None
    if value and (
        value["image_source_sha256"]
        != "383e03fe6dc166e9a06ede56805dbfaca28b75fb169d6042f66b151bb5b13988"
        or value["deployment_sha256"]
        != "f0d536a602070ae3c14c0a6c7cc259164c59f1b90a19fde1ea51e6bef260316d"
    ):
        raise RuntimeError("Image progress belongs to another source/backend")
    state["ssd17_common29_images"] = dict(
        unit=native.props(
            "qwen35-reliability-common29-ssd17-image-batch-20261103-r2.service"
        ),
        progress={
            key: value[key]
            for key in [
                "at",
                "n_planned",
                "n_accounted",
                "n_passed",
                "n_failed",
                "n_unknown",
                "n_pending",
                "completed_finite_batch",
            ]
        }
        if value
        else None,
        image_ready_is_not_environment_ready=True,
        existing_fixgit_image_reused=True,
        model_generation_calls=0,
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
            path
            for path in os.environ["PATH"].split(":")
            if path not in [private, str(R / "formal-controller18-client-bin-r1")]
        )
    )
    with (C / "unique-native-advance.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        for name, digest in native.read(B / "EXECUTION_RELEASE_R30.json")[
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
            deployment_revision="r54-public-apt-native-nop",
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
                status="CACHED_NATIVE_SSD17_ENVIRONMENT_ACCEPTANCE",
                formal_ready=False,
                new212_admission=False,
                new_common30_model_admission=False,
                old801_disabled=True,
                legacy_recovery_operational_hold=True,
                closed_legacy_jobs_not_redispatched=True,
                runtime_injection_prohibited=True,
                node17_current_phase=dict(
                    operation="NOP",
                    status_key="ssd17_native_nop_r5",
                    source_sha256="2b3a37ebf540d4a6d1f9678385d4998a52464b6e3717c19cee13bf30633d8886",
                    plan_sha256="be0ae752bce4da8e85dcdc40da5f4a7b5488d403e91ba4fa79cbf40e7709c876",
                    phase_source_sha256="5e91d2e8b912e7addabdee476cb84b8212fc411b483a9188ba779554eae19068",
                ),
            )
            if (R / "checks/NATIVE_ADVANCE_R54_HANDOFF_COMPLETED.json").exists():
                for name, operation in [
                    ("serving_evidence", lambda: serving_evidence(state)),
                    ("asset_observation", lambda: asset_observation(state)),
                    (
                        "native_ssd17_nop_r5",
                        lambda: ssd17.advance(owner, state, native.launch),
                    ),
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
