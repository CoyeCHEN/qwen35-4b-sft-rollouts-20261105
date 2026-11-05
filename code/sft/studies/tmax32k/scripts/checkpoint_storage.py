"""Keep native Trainer checkpoints on SSD; persist after the Trainer exits.

This changes storage only. No tensor staging, async Trainer hooks, or CUDA.
The explicit plan is used solely by a not-yet-started training stage.
"""

import hashlib
import json
import os
import shutil
import time
from pathlib import Path

SSD_ROOT = Path(os.environ["TMAX_SSD_ROOT"])
NFS_ROOTS = [Path(p) for p in json.loads(os.environ["TMAX_NFS_ROOTS"])]


def sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def verified_preload_sha(stage, identity, path):
    """Reuse the actual SHA from a rejected pre-load attempt only for the same file."""
    cache = stage / "verified-preload-model-input.json"
    if not cache.exists():
        return sha(path), "FULL_INPUT_FILE_SHA256"
    saved = json.loads(cache.read_text())
    stat = path.stat()
    fingerprint = {
        k: getattr(stat, k)
        for k in ["st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns"]
    }
    record = saved["original_input_verification"]
    if (
        saved["model_path"] != str(path)
        or saved["source_stat"] != fingerprint
        or max(stat.st_mtime_ns, stat.st_ctime_ns)
        >= int(record["at_unix"] * 1e9) - 1_000_000_000
        or saved["config_sha256"] != identity["config_sha256"]
        or saved["candidate_sha256"] != identity["candidate_sha256"]
        or record["data_sha256"] != identity["data"]
    ):
        raise RuntimeError(
            "Previously verified pre-load input changed; refuse cached identity"
        )
    return record["model_sha256"], "REUSED_ACTUAL_SHA_SAME_UNCHANGED_PRELOAD_FILE"


def load_plan(stage, job, executor_sha):
    path = stage / "checkpoint-io.json"
    if not path.exists():
        return None
    plan = json.loads(path.read_text())
    if (
        plan["stage"] != str(stage)
        or plan["name"] != job["name"]
        or plan["config_sha256"] != job["identity"]["config_sha256"]
        or plan["candidate_sha256"] != job["identity"]["candidate_sha256"]
        or plan["executor_sha256"] != executor_sha
        or plan["helper_sha256"] != sha(__file__)
    ):
        raise RuntimeError("Checkpoint storage plan identity mismatch")
    root = stage.parent.parent
    if (
        plan["queue_sha256"] != sha(root / "TRAINING_QUEUE-v5-observed.json")
        or plan["finalizer_sha256"] != sha(root / "scripts/finish_native_training.py")
        or job["gate"]
    ):
        raise RuntimeError("Checkpoint storage queue/finalizer identity mismatch")
    if (
        sha(stage / "config.json") != job["identity"]["config_sha256"]
        or sha(root / "scripts/training_candidate.py")
        != job["identity"]["candidate_sha256"]
    ):
        raise RuntimeError("Checkpoint storage config/candidate source drift")
    local = Path(plan["local_runs"])
    persistent = Path(plan["persistent_runs"])
    if local != SSD_ROOT / job["name"] / "runs" or local.resolve() != local:
        raise RuntimeError("SSD stage is outside the explicit private storage path")
    if not any(persistent == root / job["name"] / "runs" for root in NFS_ROOTS):
        raise RuntimeError("Persistent stage is outside existing study NFS storage")
    if plan["status"] != "APPROVED_STORAGE_ONLY_AMENDMENT":
        raise RuntimeError("Unapproved storage plan")
    return plan


def activate(stage, plan, phase):
    local = Path(plan["local_runs"])
    persistent = Path(plan["persistent_runs"])
    if not persistent.is_dir():
        raise RuntimeError("Original persistent directory is missing")
    local.mkdir(parents=True, exist_ok=True)
    if local.stat().st_uid != os.getuid():
        raise RuntimeError("SSD checkpoint storage is not owned by this user")
    if not os.access(persistent, os.R_OK | os.W_OK | os.X_OK):
        raise RuntimeError("Existing authorized NFS stage is not writable by this user")
    for path in [local, persistent]:
        if shutil.disk_usage(path).free < 50 * 2**30:
            raise RuntimeError("Checkpoint storage reserve below original 50 GiB gate")
    if phase == "fresh" and (local / "run").exists():
        raise RuntimeError("Refuse fresh training over existing SSD model work")
    link = stage / "runs"
    if not link.is_symlink() or link.resolve() not in [local, persistent]:
        raise RuntimeError("Unexpected existing logical training output path")
    if link.resolve() == persistent and any(persistent.iterdir()):
        raise RuntimeError("Refuse to replace existing persistent model work")
    if link.resolve() != local:
        temp = stage / "runs.ssd-link-new"
        temp.symlink_to(local, target_is_directory=True)
        temp.replace(link)


def inventory(root):
    files = {}
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise RuntimeError("Unexpected symlink inside native training output")
        if path.is_file():
            files[str(path.relative_to(root))] = {
                "bytes": path.stat().st_size,
                "sha256": sha(path),
            }
    return files


def copy_verified(source, destination):
    """Idempotent CPU transfer; retain incomplete copies on error, never overwrite a result."""
    expected = inventory(source)
    if not expected:
        raise RuntimeError("Refuse to persist empty training output")
    if destination.exists() and any(destination.iterdir()):
        if inventory(destination) != expected:
            raise RuntimeError("Persistent output conflicts with SSD output")
        return expected
    temporary = destination.with_name(destination.name + ".ssd-copy-incomplete")
    if temporary.is_symlink():
        raise RuntimeError("Unexpected symlink for incomplete transfer")
    temporary.mkdir(exist_ok=True)
    existing = set(inventory(temporary))
    if existing - set(expected):
        raise RuntimeError("Unexpected files in private incomplete transfer")
    for name, identity in expected.items():
        source_file = source / name
        target = temporary / name
        target.parent.mkdir(parents=True, exist_ok=True)
        if (
            not target.exists()
            or target.stat().st_size != identity["bytes"]
            or sha(target) != identity["sha256"]
        ):
            shutil.copy2(source_file, target)
        with target.open("rb") as stream:
            os.fsync(stream.fileno())
        if (
            target.stat().st_size != identity["bytes"]
            or sha(target) != identity["sha256"]
        ):
            raise RuntimeError("NFS transfer SHA mismatch: " + name)
    if inventory(source) != expected:
        raise RuntimeError("SSD output changed during CPU transfer")
    temporary.replace(destination)
    return expected


def persist(stage, plan, phase):
    source = Path(plan["local_runs"])
    destination = Path(plan["persistent_runs"])
    release = json.loads((stage / ("GPU-RELEASE-" + phase + ".json")).read_text())
    pid = Path("/proc") / str(release["trainer_pid"])
    if pid.exists():
        raise RuntimeError(
            "Trainer still exists; refuse concurrent tensor/output transfer"
        )
    files = copy_verified(source, destination)
    receipt = {
        "status": "PERSISTED_NFS_SHA_VERIFIED",
        "unix": time.time(),
        "plan_sha256": sha(stage / "checkpoint-io.json"),
        "source_local_runs": str(source),
        "persistent_runs": str(destination),
        "files": files,
        "gpu_release_sha256": sha(stage / ("GPU-RELEASE-" + phase + ".json")),
        "original_ssd_copy_retained": True,
        "training_step_or_rng_changes": False,
    }
    path = destination.parent / "checkpoint-storage-receipt.json"
    path.write_text(json.dumps(receipt, indent=2))
    with path.open("rb") as stream:
        os.fsync(stream.fileno())
    link = stage / "runs"
    if not link.is_symlink() or link.resolve() not in [source, destination]:
        raise RuntimeError("Logical output link changed during persistence")
    if link.resolve() != destination:
        temp = stage / "runs.nfs-link-new"
        temp.symlink_to(destination, target_is_directory=True)
        temp.replace(link)
    return receipt


if __name__ == "__main__":
    # CPU-only recovery after a transfer interruption: never starts a Trainer.
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--stage", type=Path, required=True)
    parser.add_argument("--phase", default="fresh")
    args = parser.parse_args()
    stage = args.stage
    root = stage.parent.parent
    queue = json.loads((root / "TRAINING_QUEUE-v5-observed.json").read_text())
    job = next(j for j in queue["jobs"] if j["stage"] == str(stage))
    executor_sha = sha(root / "scripts/gpu_job.py")
    plan = load_plan(stage, job, executor_sha)
    if plan is None:
        raise RuntimeError("No explicit SSD storage plan for CPU recovery")
    from finish_native_training import finish

    print(
        json.dumps(
            finish(root, job, executor_sha, "runs/run/result.json", args.phase, plan)
        )
    )
