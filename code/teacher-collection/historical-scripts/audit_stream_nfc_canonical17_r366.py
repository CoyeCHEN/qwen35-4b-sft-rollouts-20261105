"""CPU-only canonical student audit; preserve every earlier cache and proof."""
import fcntl
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from uuid import UUID

E = Path('/home/chenkeyi/workspace/RSI/runtime-evidence/qwen35-new-cf500-tmax500-20261029')
S = Path('/ssd/chenkeyi/qwen35-new-cf500-tmax500-20261029')
ident = str(UUID(sys.argv[1]))
original = E / 'validation/stream-r3' / ident
resource = S / 'student-tokenizer-r155'
root = S / 'data-canonical-trials-r366' / ident
root.mkdir(parents=True, exist_ok=True)
lock = (root / 'canonical-audit-r366.lock').open('a')
fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
proof = root / 'checks/STUDENT_AUDIT_TRIALS_ALL.json'
if proof.exists():
    report = json.loads(proof.read_text())
    assert report['entries'][0]['student_tokenizer_runtime_contract']['backend_semantics_sha256'] == '027a3f1c30acd5438805f34bb427a99772640beba2a4e5153ada9c90fc259281'
    print(json.dumps(dict(proof=str(proof), checks=str(root / 'checks'))))
    raise SystemExit
source, = (original / 'sources/canary-calls-all').glob('*.jsonl.gz')
source_sha = hashlib.sha256(source.read_bytes()).hexdigest()
for name in ['checks', 'logs', 'derived', 'sources/canary-calls-all']:
    (root / name).mkdir(parents=True, exist_ok=True)
target = root / 'sources/canary-calls-all' / source.name
if not target.exists():
    target.symlink_to(source.resolve())
assert hashlib.sha256(target.read_bytes()).hexdigest() == source_sha
if not (root / 'sft-code').exists():
    (root / 'sft-code').symlink_to(E / 'sft-code-nfc-prefix-r4', target_is_directory=True)
selection = dict(model_resource=str(resource),
    official_revision='851bf6e806efd8d0a36b00ddf55e13ccb7b8cd0a',
    source_manifest_sha256=hashlib.sha256((resource / 'SOURCE_MANIFEST_R155.json').read_bytes()).hexdigest(),
    original_tokenizer_config_sha256='316230d6a809701f4db5ea8f8fc862bc3a6f3229c937c174e674ff3ca0a64ac8',
    derived_tokenizer_config_sha256='3dd1cee8a0cb8f51800bcb47bd157eeef5bda2d39c85b7569892b9af95170071',
    backend_semantics_sha256='027a3f1c30acd5438805f34bb427a99772640beba2a4e5153ada9c90fc259281',
    explicit_loader_selection='Official tokenizer.json selected as PreTrainedTokenizerFast in both runtimes',
    official_template_and_processor_unchanged=True, original_model_directory_modified=False,
    history_thinking_policy='Official Qwen3.5 template, enable_thinking=true, preserve actual source history',
    input_normalization_policy='Pinned official tokenizer NFC at deployment; targets must round-trip as original text without normalization',
    encoder_sha256='68c2a68bb6d2c93d2981ca911eba22a880c29aaf817d7a45209a8da40da18d48')
assert hashlib.sha256((resource / 'tokenizer_config.json').read_bytes()).hexdigest() == selection['derived_tokenizer_config_sha256']
assert hashlib.sha256((E/'sft-code-nfc-prefix-r4/sft/teacher_segments.py').read_bytes()).hexdigest()==selection['encoder_sha256']
identity = json.loads((E / 'checks/qwen-tokenizer-processor-identity.json').read_text())
identity['source_file_checks_scope'] = 'Pinned original upstream files; runtime factory selection is explicitly derived below'
identity['runtime_tokenizer_selection'] = selection
identity_path = root / 'checks/qwen-tokenizer-processor-identity.json'
if identity_path.exists():
    assert json.loads(identity_path.read_text()) == identity
else:
    with identity_path.open('x') as stream:
        json.dump(identity, stream, indent=2)
env = dict(os.environ, CUDA_VISIBLE_DEVICES='', QWEN35_MODEL_PATH=str(resource),
    HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1', PYTHONPATH=str(E / 'sft-code-nfc-prefix-r4'),
    CF_TMAX_AUDIT_ROOT=str(root), HF_DATASETS_CACHE=str(root / 'derived/hf-cache'),
    TOKENIZERS_PARALLELISM='false', OMP_NUM_THREADS='1')
for key in ['DEEPSEEK_API_KEY', 'GH_TOKEN', 'OPENAI_API_KEY']:
    env.pop(key, None)
py = '/home/chenkeyi/workspace/RSI/runtime-evidence/qwen35-length-lf-audit-20261023/.venv/bin/python'
serving = '/ssd/chenkeyi/qwen35-m2-eval-20261026/serving-env/bin/python'
stages = [(py, 'audit_canary_qwen_v4.py'), (py, 'audit_canary_loader_r159.py'), (serving, 'audit_qwen_serving_final.py')]
for interpreter, name in stages:
    with (root / 'logs' / (name + '.r366.log')).open('x') as log:
        subprocess.run([interpreter, str(E / 'scripts' / name), '--all-canaries'], env=env,
            stdout=log, stderr=subprocess.STDOUT, check=True, timeout=12000)
assert hashlib.sha256(source.read_bytes()).hexdigest() == source_sha
with (root / 'logs/package-first-student-evidence.r366.log').open('x') as log:
    subprocess.run([py, str(E / 'scripts/package_nfc_student_evidence_r365.py'), '--all-canaries'],
        env=env, stdout=log, stderr=subprocess.STDOUT, check=True, timeout=1200)
report = json.loads(proof.read_text())
for item in report['entries']:
    item['student_tokenizer_runtime_contract'] = selection
report['canonical_audit_driver_sha256'] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
temporary = proof.with_suffix('.r366.pending')
temporary.write_text(json.dumps(report, indent=2))
temporary.replace(proof)
print(json.dumps(dict(proof=str(proof), checks=str(root / 'checks'))))
