# ruff: noqa: SIM118 -- safetensors safe_open exposes keys(), not a dict iterator
"""Read-only full-coordinate final/M1 deltas, bounded CPU memory, no forward."""

import argparse
import hashlib
import json
import math
from pathlib import Path

import torch
from safetensors import safe_open


def normalized(key):
    return key.replace("model.language_model.", "model.", 1)


def compare(original, final):
    torch.set_num_threads(4)
    rows = []
    with (
        safe_open(original, framework="pt", device="cpu") as a,
        safe_open(final, framework="pt", device="cpu") as b,
    ):
        keys = {normalized(k): k for k in a.keys()}
        if len(keys) != len(a.keys()):
            raise ValueError("Ambiguous original tensor names")
        for key in b.keys():
            if normalized(key) not in keys:
                raise ValueError("Final parameter absent from input " + key)
            x = a.get_tensor(keys[normalized(key)]).flatten()
            y = b.get_tensor(key).flatten()
            if x.shape != y.shape:
                raise ValueError("Parameter shape changed")
            count = visible = hidden = 0
            norm = [0.0, 0.0, 0.0]
            for offset in range(0, x.numel(), 1048576):
                before = x[offset : offset + 1048576]
                after = y[offset : offset + 1048576]
                changed = after.float() != before.float()
                vchanged = after.bfloat16() != before.bfloat16()
                count += int(changed.sum())
                visible += int(vchanged.sum())
                hidden += int((changed & ~vchanged).sum())
                xx = before.double()
                delta = after.double() - xx
                vdelta = after.bfloat16().double() - before.bfloat16().double()
                for i, t in enumerate([xx, delta, vdelta]):
                    norm[i] += float(t.square().sum())
            rows.append(
                {
                    "parameter": key,
                    "n": x.numel(),
                    "input_dtype": str(x.dtype),
                    "final_dtype": str(y.dtype),
                    "master_changed": count,
                    "bf16_visible_changed": visible,
                    "master_changed_bf16_unchanged": hidden,
                    "input_squared_norm": norm[0],
                    "master_delta_squared_norm": norm[1],
                    "bf16_delta_squared_norm": norm[2],
                }
            )
    n = sum(r["n"] for r in rows)
    return {
        "status": "COMPLETE_FULL_COORDINATE_CPU_DELTA",
        "independent_coordinates": n,
        "layers": rows,
        "master_change_fraction": sum(r["master_changed"] for r in rows) / n,
        "bf16_visible_change_fraction": sum(r["bf16_visible_changed"] for r in rows)
        / n,
        "master_changed_bf16_unchanged_fraction": sum(
            r["master_changed_bf16_unchanged"] for r in rows
        )
        / n,
        "input_l2": math.sqrt(sum(r["input_squared_norm"] for r in rows)),
        "master_delta_l2": math.sqrt(sum(r["master_delta_squared_norm"] for r in rows)),
        "bf16_visible_delta_l2": math.sqrt(
            sum(r["bf16_delta_squared_norm"] for r in rows)
        ),
        "gradient_claim": "No inference that unchanged weights had zero gradients; step gradient samples are recorded separately",
    }


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--original", required=True)
    p.add_argument("--final", required=True)
    p.add_argument("--out", required=True)
    a = p.parse_args()
    result = compare(a.original, a.final)
    for k, path in [("input", a.original), ("final", a.final)]:
        with Path(path).open("rb") as f:
            result[k + "_sha256"] = hashlib.file_digest(f, "sha256").hexdigest()
    with Path(a.out).open("x") as f:
        f.write(json.dumps(result, indent=2))
