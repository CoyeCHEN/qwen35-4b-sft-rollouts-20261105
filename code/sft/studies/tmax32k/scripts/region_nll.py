"""Retokenize valid conditional targets using the frozen converter; region NLL.

Prepare stores only identities/counts/hashes. It emits no prompts, observations,
token IDs or private trajectories. Open-think autonomous behavior belongs to the
decode experiment, never to an invalid teacher-forced action lacking </think>.
"""

import argparse
import collections
import hashlib
import json
import os
import re
import sys
import time
from pathlib import Path

os.environ.update(
    HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1", TOKENIZERS_PARALLELISM="false"
)
sys.dont_write_bytecode = True
S = Path(os.environ["TMAX_MODEL_CACHE"])
O = Path(os.environ["TMAX_CANONICAL_ROOT"])
N = Path(os.environ["TMAX_M2_DATA_ROOT"])
R = Path(os.environ["TMAX_ABLATION_ROOT"])
reader = Path(os.environ["TMAX_APPROVED_READER"])
reader_identity = json.loads((reader / "PINNED_SFT_READER.json").read_text())
for relative, expected in reader_identity["files"].items():
    with (reader / relative).open("rb") as stream:
        if hashlib.file_digest(stream, "sha256").hexdigest() != expected:
            raise RuntimeError("Approved NLL converter SHA mismatch " + relative)
sys.path.insert(0, str(reader))
import pyarrow.parquet as pq
from transformers import AutoTokenizer

from sft.tokenization import _messages_for_call, tokenize_call

REGIONS = [
    "thinking",
    "tool_name",
    "tool_parameters",
    "final_text",
    "eos_final",
    "eos_tool",
    "other_boundary",
]
CONDITIONS = ["teacher_full", "empty_current", "empty_current_and_history"]
PAIRED_REGIONS = ["tool_name", "tool_parameters", "final_text", "eos_final", "eos_tool"]


def digest(xs):
    return hashlib.sha256(json.dumps(xs, separators=(",", ":")).encode()).hexdigest()


def make(call, tok, condition):
    c = dict(call)
    c["assistant_response"] = dict(call["assistant_response"])
    if condition != "teacher_full":
        c["assistant_response"]["reasoning_content"] = ""
    if condition == "empty_current_and_history":
        c["request_messages"] = [
            {**m, "reasoning_content": ""} if m.get("role") == "assistant" else m
            for m in call["request_messages"]
        ]
    sample = tokenize_call(c, tok, max_length=32768)
    txt = tok.apply_chat_template(
        _messages_for_call(c),
        tools=(c.get("provider_payload") or {}).get("tools"),
        tokenize=False,
    )
    enc = tok(txt, add_special_tokens=False, return_offsets_mapping=True)
    if enc["input_ids"] != sample["input_ids"]:
        raise RuntimeError("Rendered/direct tokens differ")
    head = "<|im_start|>assistant\n"
    start = txt.rfind(head) + len(head)
    end = txt.find("<|im_end|>", start)
    thend = txt.find("</think>", start, end) + len("</think>")
    if condition != "teacher_full":
        prefix = "<think>\n\n</think>\n\n"
        if not txt.startswith(prefix, start):
            raise RuntimeError("Empty inference prefix differs from target rendering")
        cutoff = start + len(prefix)
    else:
        cutoff = start + len("<think>\n")
    toolnames = []
    parameters = []
    for match in re.finditer(r"<tool_call>.*?</tool_call>", txt[start:end], re.DOTALL):
        text = match.group()
        base = start + match.start()
        for m in re.finditer(r"<function=([^>]+)>", text):
            toolnames.append((base + m.start(1), base + m.end(1)))
        for m in re.finditer(r"<parameter=[^>]+>.*?</parameter>", text, re.DOTALL):
            parameters.append((base + m.start(), base + m.end()))
    has_tools = bool(c["assistant_response"].get("tool_calls"))
    regions = [None] * len(sample["input_ids"])
    for i, ((a, b), label) in enumerate(zip(enc["offset_mapping"], sample["labels"])):
        if label == -100 or b <= cutoff:
            sample["labels"][i] = -100
            continue
        region = "other_boundary"
        if a < thend and b > start:
            region = "thinking"
        if not has_tools and a >= thend and a < end:
            region = "final_text"
        if any(a < y and b > x for x, y in parameters):
            region = "tool_parameters"
        if any(a < y and b > x for x, y in toolnames):
            region = "tool_name"
        if sample["input_ids"][i] == tok.eos_token_id:
            region = "eos_tool" if has_tools else "eos_final"
        regions[i] = region
    if condition == "teacher_full" and sum(x is not None for x in regions) != sum(
        sample["loss_mask"]
    ):
        raise RuntimeError("Region partition lost training labels")
    return sample, regions


def rows():
    keep = {}
    for split in ["train", "holdout"]:
        for batch in pq.ParquetFile(N / "own-data" / f"{split}.parquet").iter_batches(
            batch_size=8
        ):
            for row in batch.to_pylist():
                keep[row["call_id"]] = (split, row)
    for line in (O / "input/success.canonical.jsonl").open():
        t = json.loads(line)
        for call in t["calls"]:
            if call["call_id"] in keep:
                split, row = keep[call["call_id"]]
                yield call, split, row


def aligned_targets(triples):
    """Keep an identical token suffix in each region without editing any input.

    Removing teacher reasoning changes the BPE boundary of final prose. Scoring
    the shared suffix at each condition's freshly computed positions avoids
    treating different first tokens as the same target. Omitted counts remain
    explicit; this comparison cannot score the omitted boundary decision.
    """
    result = {c: {} for c in CONDITIONS}
    summary = {}
    for region in PAIRED_REGIONS:
        positions = {
            c: [i for i, g in enumerate(triples[c][1]) if g == region]
            for c in CONDITIONS
        }
        values = {
            c: [triples[c][0]["input_ids"][i] for i in positions[c]] for c in CONDITIONS
        }
        n = min(map(len, values.values()))
        shared = 0
        while shared < n and len({v[-shared - 1] for v in values.values()}) == 1:
            shared += 1
        for c in CONDITIONS:
            result[c][region] = set(positions[c][-shared:]) if shared else set()
        tokens = values["teacher_full"][-shared:] if shared else []
        summary[region] = {
            "shared_token_count": shared,
            "target_sha256": digest(tokens),
            "omitted_tokens": {c: len(values[c]) - shared for c in CONDITIONS},
        }
    return result, summary


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--prepare", action="store_true")
    ap.add_argument("--model")
    ap.add_argument("--name")
    args = ap.parse_args()
    tok = AutoTokenizer.from_pretrained(
        S / "models/allenai--tmax-2b-39227cc1", local_files_only=True
    )
    out = R / "nll"
    out.mkdir(exist_ok=True)
    metadata = []
    if not args.prepare:
        if not args.model or not args.name:
            raise ValueError("Model path/name required")
        import torch
        import torch.nn.functional as F
        from liger_kernel.transformers import apply_liger_kernel_to_qwen3_5
        from transformers import AutoModelForCausalLM

        torch.set_num_threads(int(os.environ.get("TMAX_CPU_THREADS", "1")))
        torch.manual_seed(42)
        model = (
            AutoModelForCausalLM.from_pretrained(
                args.model,
                dtype=torch.bfloat16,
                local_files_only=True,
                attn_implementation="sdpa",
            )
            .cuda()
            .eval()
        )
        apply_liger_kernel_to_qwen3_5(
            model=model,
            rope=False,
            rms_norm=False,
            swiglu=False,
            cross_entropy=False,
            fused_linear_cross_entropy=True,
        )
    target = out / (
        "prepared-regions-v2.jsonl"
        if args.prepare
        else f"{args.name}-region-nll-v2.jsonl"
    )
    with target.open("x") as f:
        for ordinal, (call, split, row) in enumerate(rows()):
            common = {}
            triples = {c: make(call, tok, c) for c in CONDITIONS}
            paired_indices, paired_summary = aligned_targets(triples)
            for condition in CONDITIONS:
                sample, regions = triples[condition]
                if condition == "teacher_full" and (
                    sample["input_ids"] != row["input_ids"]
                    or sample["loss_mask"] != row["loss_mask"]
                ):
                    raise RuntimeError("Saved training row mismatch")
                counts = collections.Counter(x for x in regions if x is not None)
                hashes = {
                    region: digest(
                        [v for v, g in zip(sample["input_ids"], regions) if g == region]
                    )
                    for region in REGIONS
                }
                if condition == "teacher_full":
                    common = hashes
                entry = {
                    "task_id": row["task_id"],
                    "call_id": call["call_id"],
                    "split": split,
                    "condition": condition,
                    "input_tokens": len(regions),
                    "input_sha256": digest(sample["input_ids"]),
                    "region_counts": dict(counts),
                    "target_region_sha256": hashes,
                    "paired_target_regions": paired_summary,
                    "comparable_target_regions": {
                        k: hashes[k] == common[k]
                        for k in [
                            "tool_name",
                            "tool_parameters",
                            "final_text",
                            "eos_final",
                            "eos_tool",
                        ]
                    },
                }
                if not args.prepare:
                    inputs = {
                        k: torch.tensor([sample[k]], device="cuda")
                        for k in ["input_ids", "attention_mask", "labels"]
                    }
                    started = time.monotonic()
                    with torch.no_grad(), torch.autocast("cuda", dtype=torch.bfloat16):
                        output = model(
                            **inputs, skip_logits=True, output_hidden_states=True
                        )
                        hidden = output.hidden_states[-1][0]
                        sums = collections.Counter()
                        observed = collections.Counter()
                        paired_sums = collections.Counter()
                        paired_counts = collections.Counter()
                        indices = [i for i, g in enumerate(regions) if g is not None]
                        for a in range(0, len(indices), 64):
                            js = indices[a : a + 64]
                            pred = torch.tensor([i - 1 for i in js], device="cuda")
                            logits = F.linear(
                                hidden[pred], model.get_output_embeddings().weight
                            )
                            labels = torch.tensor(
                                [sample["input_ids"][i] for i in js], device="cuda"
                            )
                            nll = (
                                F.cross_entropy(
                                    logits.float(), labels, reduction="none"
                                )
                                .double()
                                .cpu()
                                .tolist()
                            )
                            for i, value in zip(js, nll):
                                sums[regions[i]] += value
                                observed[regions[i]] += 1
                                if (
                                    regions[i] in PAIRED_REGIONS
                                    and i in paired_indices[condition][regions[i]]
                                ):
                                    paired_sums[regions[i]] += value
                                    paired_counts[regions[i]] += 1
                        whole = sum(sums.values()) / sum(observed.values())
                        reference = float(output.loss)
                    if abs(whole - reference) > 0.02:
                        raise RuntimeError(
                            "Region weighted NLL differs from actual Liger loss"
                        )
                    entry.update(
                        model=args.name,
                        region_nll_sum=dict(sums),
                        region_counts=dict(observed),
                        paired_region_nll_sum=dict(paired_sums),
                        paired_region_counts=dict(paired_counts),
                        weighted_nll=whole,
                        liger_loss=reference,
                        seconds=time.monotonic() - started,
                    )
                    del output, hidden, inputs
                f.write(json.dumps(entry) + "\n")
                f.flush()
                metadata.append(
                    {
                        "split": split,
                        "condition": condition,
                        "counts": dict(counts),
                        "comparable": entry["comparable_target_regions"],
                    }
                )
            if ordinal % 25 == 0:
                print(
                    json.dumps({"states_done": ordinal + 1, "prepare": args.prepare}),
                    flush=True,
                )
    summary = {
        "status": "PREPARED_NO_FORWARD" if args.prepare else "COMPLETED",
        "states": len(metadata) // len(CONDITIONS),
        "conditions": CONDITIONS,
        "region_names": REGIONS,
        "observations": len(metadata),
        "model": args.name,
        "stored_token_ids": False,
        "invalid_comparisons": sum(not all(x["comparable"].values()) for x in metadata),
        "scope": "EOS NLL is a next-token proxy, not an estimate of autonomous stopping probability. Fixed teacher states do not measure off-policy recovery.",
    }
    (
        out
        / (
            "prepared-summary-v2.json"
            if args.prepare
            else f"{args.name}-summary-v2.json"
        )
    ).write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary))


if __name__ == "__main__":
    main()
