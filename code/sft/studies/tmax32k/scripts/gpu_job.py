# ruff: noqa: SIM115 -- GPU lock is deliberately held for process lifetime and inherited by the Trainer
"""UUID idle/lock checked entry point. Refuses occupied devices and source drift."""

import fcntl
import hashlib
import json
import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

lease_end = float(os.environ["FINAL_STUDY_LEASE_UNTIL_UNIX"])
if time.time() >= lease_end:
    raise RuntimeError("Training lease already expired")
R = Path(os.environ["TMAX_ABLATION_ROOT"])
name = sys.argv[1]
uuid = sys.argv[2]
jobs = json.loads((R / "TRAINING_QUEUE-v5-observed.json").read_text())["jobs"]
job = next(x for x in jobs if x["name"] == name)
stage = Path(job["stage"])
identity = job["identity"]
status = stage / "execution-status.json"
persistent = (stage / "runs").resolve().parent


def put(state, **kw):
    record = json.dumps(
        {"state": state, "at_unix": time.time(), "name": name, "gpu_uuid": uuid, **kw},
        indent=2,
    )
    status.write_text(record)
    (persistent / "execution-status.json").write_text(record)


def sha(p):
    with Path(p).open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


EXECUTOR_SHA256_AT_START = sha(Path(__file__))
io_plan = None
if (stage / "checkpoint-io.json").exists():
    from checkpoint_storage import activate, load_plan

    io_plan = load_plan(stage, job, EXECUTOR_SHA256_AT_START)
    persistent = Path(io_plan["persistent_runs"]).parent
entry = R / "scripts" / job.get("candidate_entry", "training_candidate.py")
if sha(entry) != identity["candidate_sha256"]:
    raise RuntimeError("Candidate source drift")
if sha(stage / "config.json") != identity["config_sha256"]:
    raise RuntimeError("Config drift")
if status.exists() and json.loads(status.read_text()).get("state") == "COMPLETED":
    raise RuntimeError("Refuse rerun of completed arm")
if sha(R / "sources/original-train.py") != identity["source_trainer_sha256"]:
    raise RuntimeError("Original Trainer source drift")
data = stage / "data/NiuNiu0110--TMax-Agent-SFT-terminus/data/pretokenized"
for split, expected in identity["data"].items():
    if sha(data / (split + ".parquet")) != expected:
        raise RuntimeError("Input data identity changed " + split)
if io_plan:
    from checkpoint_storage import verified_preload_sha

    actual_model_sha, model_verification = verified_preload_sha(
        stage, identity, Path(identity["model_source"]) / "model.safetensors"
    )
else:
    actual_model_sha, model_verification = (
        sha(Path(identity["model_source"]) / "model.safetensors"),
        "FULL_INPUT_FILE_SHA256",
    )
expected_model_sha = identity["input_model_sha256"]
if actual_model_sha != expected_model_sha:
    raise RuntimeError("Input model identity changed")
(stage / "input-verification.json").write_text(
    json.dumps(
        {
            "model_sha256": actual_model_sha,
            "data_sha256": identity["data"],
            "at_unix": time.time(),
            "model_verification": model_verification,
        },
        indent=2,
    )
)
if shutil.disk_usage(stage / "runs").free < 50 * 2**30:
    put("BLOCKED_STORAGE")
    sys.exit(73)
lock = Path(os.environ["TMAX_GPU_LOCK_PREFIX"] + uuid + ".lock").open("a")
fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
selected = json.loads(
    subprocess.check_output(
        [
            os.environ["TMAX_INFERENCE_PYTHON"],
            str(R / "scripts/nvml_selected_device.py"),
            uuid,
        ],
        text=True,
        timeout=60,
    )
)
if selected["processes"] or selected["memory_mib"] >= 512:
    put("BLOCKED_GPU_OCCUPIED", memory_used_mib=selected["memory_mib"])
    sys.exit(74)
if io_plan:
    activate(stage, io_plan, os.environ.get("TMAX_RESUME_PHASE", "fresh"))
env = {
    **os.environ,
    "CUDA_VISIBLE_DEVICES": uuid,
    "CUDA_DEVICE_ORDER": "PCI_BUS_ID",
    "TMAX_STAGE_ROOT": str(stage),
    "TMAX_PRECISION": job["precision"],
    "PYTHONDONTWRITEBYTECODE": "1",
    "HF_HUB_OFFLINE": "1",
    "TRANSFORMERS_OFFLINE": "1",
    "OMP_NUM_THREADS": "8",
    "TOKENIZERS_PARALLELISM": "false",
}
env.update(
    TRITON_CACHE_DIR=str(R / "cache/triton_train"),
    TORCHINDUCTOR_CACHE_DIR=str(R / "cache/inductor_train"),
    TORCH_EXTENSIONS_DIR=str(R / "cache/extensions_train"),
    HF_DATASETS_CACHE=str(R / "cache/datasets_train"),
    PYTORCH_KERNEL_CACHE_PATH=str(R / "cache/kernels_train"),
)
proof = json.loads(
    subprocess.check_output(
        [
            sys.executable,
            "-c",
            'import torch,json;p=torch.cuda.get_device_properties(0);print(json.dumps({"uuid":str(p.uuid),"name":p.name}))',
        ],
        env=env,
        text=True,
    )
)
if proof["uuid"].removeprefix("GPU-") != uuid.removeprefix("GPU-"):
    raise RuntimeError("Actual Torch GPU UUID differs")
(stage / "torch-gpu-identity.json").write_text(json.dumps(proof, indent=2))
cmd = [sys.executable, "-u", str(entry), "--config", job["config"]]
resume_phase = os.environ.get("TMAX_RESUME_PHASE", "fresh")
recovery = stage / "reviewed-recovery-plan.json"
if recovery.exists() and resume_phase == "resume":
    plan = json.loads(recovery.read_text())
    assert (
        plan["config_sha256"] == identity["config_sha256"]
        and plan["candidate_sha256"] == identity["candidate_sha256"]
    )
    checkpoint = Path(plan["checkpoint"])
    if any(
        sha(checkpoint / relative) != h
        for relative, h in plan["checkpoint_sha256"].items()
    ):
        raise RuntimeError("Reviewed recovery checkpoint changed")
    cmd += ["--resume", str(checkpoint)]
    env.pop("TMAX_PAUSE_STEP", None)
elif resume_phase != "fresh":
    raise RuntimeError("Resume requires a SHA-bound reviewed recovery plan")
log = persistent / ("train-" + resume_phase + ".log")
logical_log = stage / log.name
if not logical_log.exists():
    logical_log.symlink_to(log)
with log.open("x") as stream:
    proc = subprocess.Popen(
        cmd,
        env=env,
        stdout=stream,
        stderr=subprocess.STDOUT,
        pass_fds=(lock.fileno(),),
        start_new_session=True,
    )
    put("RUNNING", pid=proc.pid, phase=resume_phase, lease_until_unix=lease_end)

    def stop(sig, frame):
        try:
            os.killpg(proc.pid, sig)
        except ProcessLookupError:
            pass

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    try:
        last_verified = time.monotonic()
        while True:
            try:
                code = proc.wait(timeout=min(20, max(0, lease_end - time.time())))
                break
            except subprocess.TimeoutExpired:
                if time.time() >= lease_end:
                    raise
                # Check actual users/process ancestry locally even during an SSH outage.
                try:
                    selected = json.loads(
                        subprocess.check_output(
                            [
                                os.environ["TMAX_INFERENCE_PYTHON"],
                                str(R / "scripts/nvml_selected_device.py"),
                                uuid,
                            ],
                            text=True,
                            timeout=60,
                        )
                    )
                except (subprocess.SubprocessError, ValueError) as exc:
                    with (stage / "resource-observations.jsonl").open("a") as f:
                        f.write(
                            json.dumps(
                                {
                                    "unix": time.time(),
                                    "state": "UNKNOWN_RESOURCE_QUERY",
                                    "error": type(exc).__name__,
                                }
                            )
                            + "\n"
                        )
                    if time.monotonic() - last_verified > 180:
                        raise RuntimeError(
                            "Selected GPU ownership could not be verified for 180 seconds"
                        ) from exc
                    continue
                last_verified = time.monotonic()
                lines = [uuid + "," + str(p["pid"]) for p in selected["processes"]]
                for line in lines:
                    device, pid = [v.strip() for v in line.split(",")]
                    if device != uuid:
                        continue
                    pid = int(pid)
                    owned = False
                    for _ in range(32):
                        path = Path("/proc") / str(pid)
                        if not path.exists():
                            owned = True
                            break
                        if path.stat().st_uid != os.getuid():
                            break
                        if pid == proc.pid:
                            owned = True
                            break
                        pid = int(
                            (path / "stat").read_text().rsplit(")", 1)[1].split()[1]
                        )
                        if pid <= 1:
                            break
                    if not owned:
                        stop(signal.SIGTERM, None)
                        put("FOREIGN_GPU_PROCESS", foreign_pid=int(line.split(",")[1]))
                        raise RuntimeError(
                            "Foreign GPU process entered; stop only this study"
                        )
    except subprocess.TimeoutExpired:
        stop(signal.SIGTERM, None)
        try:
            code = proc.wait(timeout=60)
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid, signal.SIGKILL)
            code = proc.wait()
        put(
            "LEASE_EXPIRED" if time.time() >= lease_end else "RESOURCE_MONITOR_TIMEOUT",
            returncode=code,
        )
        sys.exit(124)
    except BaseException as exc:
        stop(signal.SIGTERM, None)
        try:
            code = proc.wait(timeout=60)
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid, signal.SIGKILL)
            code = proc.wait()
        previous = json.loads(status.read_text())
        put(
            "FAILED_RESOURCE_MONITOR",
            returncode=code,
            reason=type(exc).__name__ + ": " + str(exc),
            previous_resource_state=previous,
        )
        raise
# The Trainer has exited; prove CUDA memory/process release before CPU hashing.
released = json.loads(
    subprocess.check_output(
        [
            os.environ["TMAX_INFERENCE_PYTHON"],
            str(R / "scripts/nvml_selected_device.py"),
            uuid,
        ],
        text=True,
        timeout=60,
    )
)
remaining = released["processes"]
memory = released["memory_mib"]
(stage / ("GPU-RELEASE-" + resume_phase + ".json")).write_text(
    json.dumps(
        {
            "unix": time.time(),
            "gpu_uuid": uuid,
            "trainer_pid": proc.pid,
            "trainer_returncode": code,
            "processes": remaining,
            "memory_mib": memory,
            "state": "GPU_RELEASED"
            if not remaining and memory < 512
            else "GPU_NOT_UNOCCUPIED",
        },
        indent=2,
    )
)
if (stage / "runs/run").is_dir():
    shutil.copy2(
        stage / ("GPU-RELEASE-" + resume_phase + ".json"),
        stage / "runs/run" / ("GPU-RELEASE-" + resume_phase + ".json"),
    )
# CUDA has exited: release this study's advisory lock before CPU verification.
fcntl.flock(lock, fcntl.LOCK_UN)
lock.close()
if code:
    put("FAILED", returncode=code)
    sys.exit(code)
result_file = "runs/run/result.json"
from finish_native_training import finish

if io_plan:
    put(
        "ARTIFACT_VERIFYING",
        trainer_returncode=code,
        phase=resume_phase,
        gpu_process_exited=True,
    )
try:
    finish(R, job, EXECUTOR_SHA256_AT_START, result_file, resume_phase, io_plan)
except Exception as exc:
    if io_plan:
        put(
            "PERSISTENCE_BLOCKED",
            trainer_returncode=code,
            phase=resume_phase,
            reason=str(exc),
            ssd_copy_retained=True,
        )
    raise
