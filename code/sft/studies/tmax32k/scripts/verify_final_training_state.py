"""CPU artifact check after an actual full training process has exited."""

import argparse
import json
import os
from pathlib import Path

os.environ["CUDA_VISIBLE_DEVICES"] = ""
import torch

ap = argparse.ArgumentParser()
ap.add_argument("--stage", required=True)
ap.add_argument("--steps", type=int, required=True)
ap.add_argument("--precision", required=True)
args = ap.parse_args()
stage = Path(args.stage)
run = stage / "runs/run"
ckpt = run / f"checkpoint-{args.steps}"
result = json.loads((run / "result.json").read_text())
env = json.loads((run / "environment.json").read_text())
assert (
    result["completed"]
    and result["reload_exact_tensor_match"]
    and result["global_step"] == args.steps
)
assert result["train_metrics"]["epoch"] == 1
rows = [
    json.loads(v) for v in (run / "actual-sample-order.jsonl").read_text().splitlines()
]
events = [
    json.loads(v)
    for v in (run / "optimizer-step-events.jsonl").read_text().splitlines()
]
assert len(rows) == env["train_rows"] and len(events) == args.steps
assert [v["optimizer_step"] for v in events] == list(range(1, args.steps + 1))
assert [v["global_step_before"] for v in rows] == [i // 4 for i in range(len(rows))]
assert (
    sum(v["supervised_tokens"] for v in rows)
    == result["actual_supervised_tokens"]
    == env["train_supervised_tokens"]
)
assert (
    sum(v["context_tokens"] for v in rows)
    == result["actual_context_tokens"]
    == env["train_context_tokens"]
)
assert (
    events[-1]["actual_supervised_tokens_cumulative"] == env["train_supervised_tokens"]
)
assert all(v["native_pre_clip_gradient_norm"] >= 0 for v in events)
assert all(
    (ckpt / n).is_file()
    for n in [
        "model.safetensors",
        "optimizer.pt",
        "scheduler.pt",
        "rng_state.pth",
        "trainer_state.json",
    ]
)
opt = torch.load(
    ckpt / "optimizer.pt", map_location="cpu", mmap=True, weights_only=True
)
ids = [i for group in opt["param_groups"] for i in group["params"]]
assert len(ids) == len(set(ids)) == len(opt["state"]) == 320
dtype = torch.float32 if args.precision == "fp32_master" else torch.bfloat16
for item in opt["state"].values():
    assert int(item["step"]) == args.steps
    assert item["exp_avg"].dtype == item["exp_avg_sq"].dtype == dtype
scheduler = torch.load(ckpt / "scheduler.pt", map_location="cpu", weights_only=True)
assert scheduler["last_epoch"] == args.steps
assert (
    json.loads((ckpt / "trainer_state.json").read_text())["global_step"] == args.steps
)
proof = {
    "status": "PASS_FINAL_TRAINING_ARTIFACTS",
    "optimizer_states": 320,
    "optimizer_steps_all": args.steps,
    "optimizer_dtype": str(dtype),
    "scheduler_last_epoch": scheduler["last_epoch"],
    "actual_epoch": 1,
    "actual_microbatches": len(rows),
    "optimizer_events": len(events),
    "actual_supervised_tokens": result["actual_supervised_tokens"],
    "actual_context_tokens": result["actual_context_tokens"],
    "final_reload_exact": True,
    "last_accumulation_window_microbatches": len(rows) % 4 or 4,
    "GPU_used_for_this_check": False,
}
(run / "final-training-state-validation.json").open("x").write(
    json.dumps(proof, indent=2)
)
print(json.dumps(proof))
