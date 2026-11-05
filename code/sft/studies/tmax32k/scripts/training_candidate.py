# ruff: noqa: S102, SIM118 -- execute only SHA-pinned historical Trainer/collator; safe_open keys() is its public API
"""Isolated wrapper around SHA-pinned original Trainer; mature PyTorch AMP.

P1 trainable FP32 parameters are master weights; autocast remains BF16. AdamW is
unchanged. Original conversion, collator, sampler, reduction, scheduler and full
epoch are reused. A real A800/Liger/resume gate must pass before full arms.
"""

import hashlib
import json
import math
import os
import random
import sys
import time
import types
from pathlib import Path

import numpy as np
import torch
from safetensors import safe_open
from safetensors.torch import load_model

ROOT = Path(os.environ["TMAX_ABLATION_ROOT"])
STAGE = Path(os.environ["TMAX_STAGE_ROOT"])
SOURCE = ROOT / "sources/original-train.py"
expected = "e6ff6e469add68c7c8fbc06f3b60eb10ae677d0dfc035c871b6731a17df6e0c8"
if hashlib.sha256(SOURCE.read_bytes()).hexdigest() != expected:
    raise RuntimeError("Original Trainer SHA mismatch")
mode = os.environ["TMAX_PRECISION"]
if mode not in ["bf16_direct", "fp32_master"]:
    raise ValueError(mode)
sys.path.insert(0, str(ROOT / "scripts"))
collator_source = ROOT / "sources/original-sft_data.py"
if (
    hashlib.sha256(collator_source.read_bytes()).hexdigest()
    != "019b6a7309ae602ae4480d9e50c540872d34625fb745a099780bf0a1c9e01327"
):
    raise RuntimeError("Original loss-mask collator SHA mismatch")
collator = types.ModuleType("sft_data")
exec(
    compile(
        (ROOT / "sources/original-sft_data.py").read_text(),
        "frozen-sft_data.py",
        "exec",
    ),
    collator.__dict__,
)
sys.modules["sft_data"] = collator
source = SOURCE.read_text()
if source.count("dtype=torch.bfloat16,") != 1:
    raise RuntimeError("Loader patch boundary changed")
source = source.replace(
    "dtype=torch.bfloat16,",
    'dtype=(torch.float32 if os.environ["TMAX_PRECISION"] == "fp32_master" else torch.bfloat16),',
)
source = source.replace(
    "with torch.no_grad():",
    'with torch.no_grad(), torch.autocast("cuda", dtype=torch.bfloat16):',
)
original = types.ModuleType("pinned_original_trainer")
original.__file__ = str(SOURCE)
exec(
    compile(source, str(SOURCE) + "::controlled-dtype-and-postcheck-autocast", "exec"),
    original.__dict__,
)
original.ROOT = STAGE
IDENTITIES = {}
base_selected = original.selected_dataset


def selected(*args, **kwargs):
    dataset = base_selected(*args, **kwargs)
    for row in dataset:
        key = hashlib.sha256(
            torch.tensor(row["input_ids"], dtype=torch.int64).numpy().tobytes()
        ).hexdigest()
        IDENTITIES[key] = {
            "call_id": row.get("call_id"),
            "trajectory_id": row.get("trajectory_id"),
            "task_group_id": row.get("task_group_id"),
        }
    return dataset


original.selected_dataset = selected
base_load_text_model = original.load_text_model


def load_text_model(*args, **kwargs):
    model, info = base_load_text_model(*args, **kwargs)
    # Trainer resumes with native state_dict keys. Transformers 5.14 otherwise
    # exports reverted source keys, which its Trainer does not convert on load.
    save = model.save_pretrained

    def save_native(*a, **kw):
        kw["save_original_format"] = False
        return save(*a, **kw)

    model.save_pretrained = save_native
    return model, info


original.load_text_model = load_text_model


def restore_checkpoint(self, resume_from_checkpoint, model=None):
    model = self.model if model is None else model
    if self.is_fsdp_enabled or self.is_deepspeed_enabled:
        raise RuntimeError(
            "This frozen study uses single-device full-parameter checkpoints"
        )
    checkpoint = Path(resume_from_checkpoint) / "model.safetensors"
    # Mature safetensors loader validates the native keys and tied aliases.
    # No legacy key conversion, partial load, or compatibility fallback.
    missing, unexpected = load_model(model, checkpoint, strict=True, device="cpu")
    with safe_open(checkpoint, framework="pt", device="cpu") as saved:
        state = model.state_dict()
        for key in saved.keys():
            actual = state[key].detach().cpu()
            expected = saved.get_tensor(key)
            if actual.dtype != expected.dtype or not torch.equal(actual, expected):
                raise RuntimeError("Checkpoint tensor restore mismatch: " + key)
        keys = len(saved.keys())
    if (
        model.get_input_embeddings().weight.data_ptr()
        != model.get_output_embeddings().weight.data_ptr()
    ):
        raise RuntimeError("Checkpoint restore broke tied embedding/head")
    with checkpoint.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    original.write_json(
        Path(self.args.output_dir) / "checkpoint-restore-audit.json",
        {
            "status": "EXACT_NATIVE_CHECKPOINT_RESTORE",
            "checkpoint": str(checkpoint),
            "sha256": digest,
            "saved_tensors_exactly_restored": keys,
            "missing": missing,
            "unexpected": unexpected,
            "tied_embedding_head": True,
        },
    )


original.VerifiedTrainer._load_from_checkpoint = restore_checkpoint


def assert_exact(actual, expected):
    if isinstance(expected, torch.Tensor):
        if (
            actual.dtype != expected.dtype
            or actual.shape != expected.shape
            or not torch.equal(actual.detach().cpu(), expected.detach().cpu())
        ):
            raise RuntimeError("Checkpoint state tensor differs after native restore")
        return 1
    if isinstance(expected, np.ndarray):
        if actual.dtype != expected.dtype or not np.array_equal(actual, expected):
            raise RuntimeError("Checkpoint NumPy RNG state differs")
        return 0
    if isinstance(expected, dict):
        if actual.keys() != expected.keys():
            raise RuntimeError("Checkpoint state keys differ")
        return sum(assert_exact(actual[k], v) for k, v in expected.items())
    if isinstance(expected, (list, tuple)):
        if type(actual) != type(expected) or len(actual) != len(expected):
            raise RuntimeError("Checkpoint state sequence differs")
        return sum(assert_exact(a, b) for a, b in zip(actual, expected))
    if actual != expected:
        raise RuntimeError("Checkpoint scalar state differs")
    return 0


base_restore_optimizer = original.VerifiedTrainer._load_optimizer_and_scheduler


def restore_optimizer(self, checkpoint):
    base_restore_optimizer(self, checkpoint)
    if checkpoint is None:
        return
    root = Path(checkpoint)
    saved = torch.load(
        root / "optimizer.pt", map_location="cpu", weights_only=True, mmap=True
    )
    tensors = assert_exact(self.optimizer.state_dict(), saved)
    scheduler = torch.load(root / "scheduler.pt", map_location="cpu", weights_only=True)
    assert_exact(self.lr_scheduler.state_dict(), scheduler)
    original.write_json(
        Path(self.args.output_dir) / "optimizer-restore-audit.json",
        {
            "status": "EXACT_OPTIMIZER_AND_SCHEDULER_RESTORE",
            "checkpoint": str(root),
            "optimizer_tensors_exactly_restored": tensors,
            "parameter_states": len(saved["state"]),
            "groups": len(saved["param_groups"]),
            "scheduler_exact": True,
        },
    )


original.VerifiedTrainer._load_optimizer_and_scheduler = restore_optimizer
base_restore_rng = original.VerifiedTrainer._load_rng_state


def restore_rng(self, checkpoint):
    base_restore_rng(self, checkpoint)
    if checkpoint is None:
        return
    # gpu_job verifies this study's complete checkpoint SHA before starting.
    # NumPy's RNG tuple is part of our own trusted native Trainer artifact.
    saved = torch.load(
        Path(checkpoint) / "rng_state.pth", map_location="cpu", weights_only=False
    )
    actual = {
        "python": random.getstate(),
        "numpy": np.random.get_state(),
        "cpu": torch.random.get_rng_state(),
        "cuda": torch.cuda.get_rng_state(),
    }
    if actual.keys() != saved.keys():
        raise RuntimeError("Unexpected RNG backend in frozen single-GPU study")
    assert_exact(actual, saved)
    original.write_json(
        Path(self.args.output_dir) / "rng-restore-audit.json",
        {
            "status": "EXACT_PYTHON_NUMPY_CPU_CUDA_RNG_RESTORE",
            "checkpoint": str(checkpoint),
            "backends": sorted(saved),
            "all_exact": True,
        },
    )


original.VerifiedTrainer._load_rng_state = restore_rng
ACTIVE_TRAINER = None
LAST_CLIP = None
base_trainer_init = original.VerifiedTrainer.__init__


def trainer_init(self, *args, **kwargs):
    global ACTIVE_TRAINER
    base_trainer_init(self, *args, **kwargs)
    ACTIVE_TRAINER = self
    native_clip = self.accelerator.clip_grad_norm_

    def record_clip(*a, **kw):
        global LAST_CLIP
        norm = native_clip(*a, **kw)
        value = float(norm)
        if not math.isfinite(value):
            raise FloatingPointError(
                "Nonfinite native gradient norm before optimizer step"
            )
        LAST_CLIP = {
            "global_step_before": self.state.global_step,
            "native_pre_clip_gradient_norm": value,
        }
        return norm

    self.accelerator.clip_grad_norm_ = record_clip


original.VerifiedTrainer.__init__ = trainer_init
base_training_step = original.VerifiedTrainer.training_step


def training_step(self, model, inputs, *args, **kwargs):
    if os.environ.get("TMAX_RESUME_PHASE") == "resume":
        for name in [
            "checkpoint-restore-audit.json",
            "optimizer-restore-audit.json",
            "rng-restore-audit.json",
        ]:
            if not (Path(self.args.output_dir) / name).is_file():
                raise RuntimeError(
                    "Resume state audit missing before real training: " + name
                )
    digest = hashlib.sha256(
        inputs["input_ids"][0].detach().cpu().numpy().tobytes()
    ).hexdigest()
    row = {
        "input_sha256": digest,
        **IDENTITIES[digest],
        "global_step_before": self.state.global_step,
        "context_tokens": int(inputs["attention_mask"].sum()),
        "supervised_tokens": int(inputs["labels"].ne(-100).sum()),
    }
    with (Path(self.args.output_dir) / "actual-sample-order.jsonl").open("a") as f:
        f.write(json.dumps(row) + "\n")
    return base_training_step(self, model, inputs, *args, **kwargs)


original.VerifiedTrainer.training_step = training_step


class NumericalAudit(original.AuditCallback):
    def __init__(self, model, out):
        super().__init__(model, out)
        self.capture = None
        self.rows = []
        self.dtype_hooks = []
        self.params = dict(model.named_parameters())
        if (out / "numerical-steps.json").exists():
            self.rows = json.loads((out / "numerical-steps.json").read_text())[
                "records"
            ]
        self.expected_dtype = torch.float32 if mode == "fp32_master" else torch.bfloat16
        if any(p.dtype != self.expected_dtype for p in model.parameters()):
            raise RuntimeError("Parameter/master dtype wrong")
        if (
            model.get_input_embeddings().weight.data_ptr()
            != model.get_output_embeddings().weight.data_ptr()
        ):
            raise RuntimeError("Tied embedding/head changed")
        for name, module in list(model.named_modules()):
            if isinstance(module, torch.nn.Linear) and len(self.dtype_hooks) < 3:

                def hook(m, inp, out, n=name):
                    if len(self.rows) < 3:
                        with (self.out / "compute-dtypes.jsonl").open("a") as f:
                            f.write(
                                json.dumps(
                                    {
                                        "module": n,
                                        "parameter": str(m.weight.dtype),
                                        "input": str(inp[0].dtype),
                                        "output": str(out.dtype),
                                        "cuda_autocast": torch.is_autocast_enabled(),
                                    }
                                )
                                + "\n"
                            )

                self.dtype_hooks.append(module.register_forward_hook(hook))

    def on_pre_optimizer_step(
        self, args, state, control, model=None, optimizer=None, **kwargs
    ):
        super().on_pre_optimizer_step(args, state, control, model=model, **kwargs)
        if not (
            state.global_step < 3
            or state.global_step % 20 == 0
            or state.global_step + 1 >= state.max_steps
        ):
            return
        opt = optimizer
        while hasattr(opt, "optimizer"):
            opt = opt.optimizer
        groups = {id(p): g for g in opt.param_groups for p in g["params"]}
        capture = []
        for name, p in model.named_parameters():
            if p.grad is None:
                raise RuntimeError("Missing gradient " + name)
            if p.dtype != self.expected_dtype or p.grad.dtype != self.expected_dtype:
                raise RuntimeError("Gradient/master mismatch")
            stride = max(1, p.numel() // 2048)
            idx = torch.arange(0, p.numel(), stride, device=p.device)[:2048]
            before = p.detach().flatten()[idx].cpu()
            grad = p.grad.detach().flatten()[idx].cpu()
            g = groups[id(p)]
            # Use PyTorch AdamW for a FP32 arithmetic reference with the exact
            # sampled current gradient and previously stored moments. This is
            # not a hand-written Adam implementation or historical replay.
            ref = torch.nn.Parameter(before.float().clone())
            ref.grad = grad.float().clone()
            ropt = torch.optim.AdamW(
                [ref],
                lr=g["lr"],
                betas=g["betas"],
                eps=g["eps"],
                weight_decay=g["weight_decay"],
                fused=False,
            )
            if opt.state.get(p):
                rs = {}
                for key, value in opt.state[p].items():
                    rs[key] = (
                        (
                            value.detach().cpu().clone()
                            if value.ndim == 0
                            else value.detach().flatten()[idx].float().cpu().clone()
                        )
                        if isinstance(value, torch.Tensor)
                        else value
                    )
                ropt.state[ref] = rs
            ropt.step()
            capture.append(
                (name, p, idx, before, grad, ref.detach().clone(), float(g["lr"]))
            )
        self.capture = (state.global_step + 1, capture)

    def on_optimizer_step(
        self, args, state, control, model=None, optimizer=None, **kwargs
    ):
        opt = optimizer
        while hasattr(opt, "optimizer"):
            opt = opt.optimizer
        if LAST_CLIP is None or LAST_CLIP["global_step_before"] != state.global_step:
            raise RuntimeError("Native clip observation missing")
        first = opt.param_groups[0]["params"][0]
        actual_step = int(opt.state[first]["step"])
        if actual_step != state.global_step + 1:
            raise RuntimeError("Native optimizer step skipped/repeated")
        event = {
            "optimizer_step": actual_step,
            "unix": time.time(),
            **LAST_CLIP,
            "learning_rates": [float(g["lr"]) for g in opt.param_groups],
            "actual_context_tokens_cumulative": ACTIVE_TRAINER.context_tokens,
            "actual_supervised_tokens_cumulative": ACTIVE_TRAINER.supervised_tokens,
            "peak_allocated_gib": torch.cuda.max_memory_allocated() / 2**30,
        }
        with (self.out / "optimizer-step-events.jsonl").open("a") as f:
            f.write(json.dumps(event, allow_nan=False) + "\n")
        if self.capture is None:
            return
        step, items = self.capture
        rows = []
        opt = optimizer
        while hasattr(opt, "optimizer"):
            opt = opt.optimizer
        for name, p, idx, before, grad, reference, lr in items:
            after = p.detach().flatten()[idx].cpu()
            delta = after.float() - before.float()
            rd = reference - before.float()
            st = opt.state[p]
            if mode == "fp32_master" and any(
                st[k].dtype != torch.float32 for k in ["exp_avg", "exp_avg_sq"]
            ):
                raise RuntimeError("FP32 optimizer states missing")
            rows.append(
                {
                    "parameter": name,
                    "sample_n": len(idx),
                    "gradient_nonzero_fraction": float((grad != 0).float().mean()),
                    "gradient_l2": float(grad.float().norm()),
                    "actual_update_fraction": float((after != before).float().mean()),
                    "actual_delta_l2": float(delta.norm()),
                    "parameter_l2": float(before.float().norm()),
                    "fp32_reference_update_fraction": float(
                        (reference != before.float()).float().mean()
                    ),
                    "fp32_reference_delta_l2": float(rd.norm()),
                    "bf16_reference_update_fraction": float(
                        (reference.bfloat16() != before.bfloat16()).float().mean()
                    ),
                    "master_changed_but_bf16_unchanged_fraction": float(
                        ((after != before) & (after.bfloat16() == before.bfloat16()))
                        .float()
                        .mean()
                    ),
                    "parameter_dtype": str(p.dtype),
                    "gradient_dtype": str(p.grad.dtype),
                    "exp_avg_dtype": str(st["exp_avg"].dtype),
                    "exp_avg_sq_dtype": str(st["exp_avg_sq"].dtype),
                    "lr": lr,
                }
            )
        self.rows.append({"step": step, "rows": rows})
        original.write_json(
            self.out / "numerical-steps.json",
            {
                "mode": mode,
                "master": "FP32 trainable parameters under BF16 autocast"
                if mode == "fp32_master"
                else "none",
                "records": self.rows,
            },
        )
        self.capture = None

    def on_save(self, args, state, control, **kwargs):
        ckpt = Path(args.output_dir) / f"checkpoint-{state.global_step}"
        required = [
            "model.safetensors",
            "optimizer.pt",
            "scheduler.pt",
            "rng_state.pth",
            "trainer_state.json",
        ]
        if not all((ckpt / f).exists() for f in required):
            raise RuntimeError("Incomplete saved checkpoint")


original.AuditCallback = NumericalAudit
original.main()
