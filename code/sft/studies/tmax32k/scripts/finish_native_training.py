import sys

"""CPU-only native output validation, optional storage commit, and final manifest."""
import json
import os
import subprocess
import time
from pathlib import Path

from checkpoint_storage import persist, sha


def finish(root, job, executor_sha, result_file, phase, io_plan=None):
    stage = Path(job["stage"])
    run = stage / "runs/run"
    name = job["name"]
    identity = job["identity"]
    release = json.loads((stage / ("GPU-RELEASE-" + phase + ".json")).read_text())
    if (
        release["trainer_returncode"] != 0
        or (Path("/proc") / str(release["trainer_pid"])).exists()
    ):
        raise RuntimeError("CPU finalization requires a successful exited Trainer")
    result = json.loads((stage / result_file).read_text())
    expected = job["expected_optimizer_steps"]
    if not result.get("completed") or result["global_step"] != expected:
        raise RuntimeError("Training incomplete/wrong step count")
    if not job["gate"]:
        # Bind a reusable native CPU verification to its exact closed inputs.
        ckpt = "checkpoint-" + str(expected)
        names = [
            "result.json",
            "environment.json",
            "actual-sample-order.jsonl",
            "optimizer-step-events.jsonl",
            "final/model.safetensors",
            *[
                ckpt + "/" + n
                for n in [
                    "model.safetensors",
                    "optimizer.pt",
                    "scheduler.pt",
                    "rng_state.pth",
                    "trainer_state.json",
                ]
            ],
        ]
        inputs = {
            "files": {n: sha(run / n) for n in names},
            "verifier_sha256": sha(root / "scripts/verify_final_training_state.py"),
            "config_sha256": identity["config_sha256"],
            "precision": job["precision"],
        }
        bound = run / "final-training-validation-inputs.json"
        if bound.exists():
            if json.loads(bound.read_text()) != inputs:
                raise RuntimeError("CPU validation input identity changed")
        else:
            bound.open("x").write(json.dumps(inputs, indent=2))
        proof = run / "final-training-state-validation.json"
        if not proof.exists():
            subprocess.run(
                [
                    sys.executable,
                    str(root / "scripts/verify_final_training_state.py"),
                    "--stage",
                    str(stage),
                    "--steps",
                    str(expected),
                    "--precision",
                    job["precision"],
                ],
                env={**os.environ, "CUDA_VISIBLE_DEVICES": ""},
                check=True,
            )
        verified = json.loads(proof.read_text())
        dtype = (
            "torch.float32" if job["precision"] == "fp32_master" else "torch.bfloat16"
        )
        if (
            verified["status"] != "PASS_FINAL_TRAINING_ARTIFACTS"
            or verified["optimizer_steps_all"] != expected
            or verified["optimizer_dtype"] != dtype
            or not verified["final_reload_exact"]
        ):
            raise RuntimeError("Native CPU verification receipt is not valid")
    if io_plan:
        persist(stage, io_plan, phase)
    persistent = (
        Path(io_plan["persistent_runs"]).parent
        if io_plan
        else (stage / "runs").resolve().parent
    )
    files = {
        str(p.relative_to(stage)): {"sha256": sha(p), "size": p.stat().st_size}
        for p in (stage / "runs/run").rglob("*")
        if p.is_file()
    }
    manifest = {
        "files": files,
        "config_sha256": identity["config_sha256"],
        "candidate_sha256": identity["candidate_sha256"],
        "executor_sha256": executor_sha,
        "cpu_finalizer_sha256": sha(__file__),
        "result_file": result_file,
        "finalization_program_sha256": sha(
            root / "scripts/finalize_committed_long_gate.py"
        )
        if result_file.endswith("finalization-result.json")
        else None,
        "checkpoint_io_plan_sha256": sha(stage / "checkpoint-io.json")
        if io_plan
        else None,
        "checkpoint_io_receipt_sha256": sha(
            persistent / "checkpoint-storage-receipt.json"
        )
        if io_plan
        else None,
    }
    (stage / "artifact-manifest.json").write_text(json.dumps(manifest, indent=2))
    record = {
        "state": "COMPLETED",
        "at_unix": time.time(),
        "name": name,
        "gpu_uuid": release["gpu_uuid"],
        "returncode": 0,
        "global_step": expected,
        "final_sha256": files["runs/run/final/model.safetensors"]["sha256"],
        "result_file": result_file,
    }
    encoded = json.dumps(record, indent=2)
    (stage / "execution-status.json").write_text(encoded)
    (persistent / "execution-status.json").write_text(encoded)
    return record
