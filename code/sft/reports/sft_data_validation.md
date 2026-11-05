# SFT Data Validation

The real canonical rollout was converted with:

```text
python examples/convert_rollouts.py openharness_v2 \
  /home/cky/workspace/RSI/runtime-evidence/deepseek-20261013/trajectory \
  /home/cky/workspace/RSI/runtime-evidence/deepseek-20261013/canonical.jsonl
```

The direct fixed TMax checkout was then verified on `aibox-167`, using an
`NVIDIA A800 80GB PCIe`. The model is `allenai/tmax-2b`, revision
`39227cc1b9d221c53140e56a66094d84d115d579`, with Transformers `5.14.0`,
PyTorch `2.8.0+cu128`, CUDA `12.8`, and Python `3.12.3`. Resolved file hashes:

```text
tokenizer.json        87a7830d63fcf43bf241c3c5242e96e62dd3fdc29224ca26fed8ea333db72de4
tokenizer_config.json 25e545c9bbc8dbe4ba86741aad19b266c1eda469b42261c60358192b5580fe2a
chat_template.jinja   273d8e0e683b885071fb17e08d71e5f2a5ddfb5309756181681de4f5a1822d80
config.json           ed1c1723241f23f7f4e23430759cbd7dcfb4103cbdfe052bfe7626b57c2615b4
model.safetensors     58ac4d01503b73cf48baa472abc7112e4361309318d3de7f9d6482d9a8a85d70
```

The model weight file is 3,763,692,048 bytes. The earlier local compatible
tokenizer check remains useful as a preflight, but the A800 result below is the
authoritative TMax tokenizer check.

The real tokenizer produced four per-call samples:

| call | input tokens | supervised tokens |
|---|---:|---:|
| 1 | 152 | 65 |
| 2 | 253 | 86 |
| 3 | 308 | 39 |
| 4 | 429 | 103 |

The template has no `{% generation %}` block. The adapter uses the audited
offset-mask path: render once, tokenize with offsets, require rendered/direct
token equality, and mark only the current Call's Assistant span through
`<|im_end|>`. Earlier Assistant messages remain in the request context but are
explicitly marked with `step_loss_mask=0`; this prevents replaying history as
labels. System, User, and Tool Observation spans are zero. Assistant reasoning
(when actually present), text, tool XML, and the end marker are one. No extra
special token or causal shift is added, and inputs over 8192 are rejected rather
than truncated. Every sample had nonzero supervised tokens and
`loss_mask[0] == 0`.

The saved A800 output is
`/home/cky/workspace/RSI/runtime-evidence/deepseek-20261013/tmax2b-real-check-after-mask-fix.txt`
(SHA-256
`4062dbdc69a00bbc460dc9a1728531057c7bcf667f3b44416dcf74e893137f6b`). The
printed supervised spans include the real DeepSeek reasoning where it was
recorded and the converted TMax XML tool call, for example
`<function=bash><parameter=command>cat target.txt</parameter>`. No teacher token
IDs or missing reasoning were synthesized.

This validates real tokenization and masking with the fixed TMax tokenizer on the
A800 host. No SFT training was started because this rollout has no verifier
reward; it remains diagnostic data and cannot enter a successful SFT set.

## Clean positive batch audit (2026-10-14)

The first six-trajectory batch was re-audited against task source files. The
`hello-user` source contains the Terminal-Bench canary GUID in
`solution/solve.sh`; that trajectory was removed before the replacement build.
The clean canonical JSONL is
`runtime-evidence/openharness-teacher-batch-20261014/canonical_positive_batch_clean_v1.jsonl`
with SHA-256
`d31290b501e487f8555d0cd0c187b61a9c7253817bbb0e7bbd7cf31e52c91347`.

Using the same fixed tokenizer and the existing offset-mask implementation, the
clean split contains 17 train Call rows (4 task groups, 1101 supervised tokens)
and 3 holdout Call rows (1 task group, 216 supervised tokens). Maximum context is
1854 tokens. The A800 output is in
`runtime-evidence/openharness-teacher-batch-20261014/a800-clean-v1/`; the train
and holdout parquet hashes are `904dc6778533c91810e6317180a10e6182017d519aecc23005bc60a4d833f1b0`
and `0b7ad5a8c9f1da4b3e551e0b98a8f2e2b2924a87103bbcfd84af4714634f95ea`.
The old 21-row split and its checkpoint are retained only as invalidated audit
evidence and must not be used for training.
