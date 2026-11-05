"""Full isolated per-target audit of a real tokenizer-prefix failure; CPU only."""
import datetime
import hashlib
import json
import os
from pathlib import Path
import subprocess

E = Path('/home/chenkeyi/workspace/RSI/runtime-evidence/qwen35-new-cf500-tmax500-20261029')
S = Path('/ssd/chenkeyi/qwen35-new-cf500-tmax500-20261029')
ident = 'ddc3d97b-cd36-44c5-b911-28451892baeb'
old = E / 'validation/stream-r3' / ident
root = S / 'data-tokenizer-revalidation-r159' / ident
root.mkdir(parents=True, exist_ok=False)
for name in ['checks', 'logs', 'derived', 'sources/canary-calls-all']:
    (root / name).mkdir(parents=True, exist_ok=True)
source, = (old / 'sources/canary-calls-all').glob('*.jsonl.gz')
source_sha = hashlib.sha256(source.read_bytes()).hexdigest()
(root / 'sources/canary-calls-all' / source.name).symlink_to(source.resolve())
(root / 'sft-code').symlink_to(E / 'sft-code-weight-audit-r3', target_is_directory=True)
env = dict(os.environ, CUDA_VISIBLE_DEVICES='', QWEN35_MODEL_PATH=str(S / 'student-tokenizer-r155'),
    HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1', PYTHONPATH=str(E / 'sft-code-weight-audit-r3'),
    CF_TMAX_AUDIT_ROOT=str(root), HF_DATASETS_CACHE=str(root / 'derived/hf-cache'),
    TOKENIZERS_PARALLELISM='false', OMP_NUM_THREADS='1')
for name in ['DEEPSEEK_API_KEY', 'GH_TOKEN', 'OPENAI_API_KEY']:
    env.pop(name, None)
py = '/home/chenkeyi/workspace/RSI/runtime-evidence/qwen35-length-lf-audit-20261023/.venv/bin/python'
serving = '/ssd/chenkeyi/qwen35-m2-eval-20261026/serving-env/bin/python'
stages = [(py, 'audit_canary_qwen_v4.py'), (py, 'audit_canary_loader_r159.py'),
          (serving, 'audit_qwen_serving_final.py')]
for interpreter, name in stages:
    with (root / 'logs' / (name + '.log')).open('x') as log:
        subprocess.run([interpreter, str(E / 'scripts' / name), '--all-canaries'],
            env=env, stdout=log, stderr=subprocess.STDOUT, check=True, timeout=12000)
checks = root / 'checks'
projection, = json.loads((checks / 'canary-qwen-projection-all-v4.json').read_text())
loader = json.loads((checks / 'canary-native-loader-all-v4.json').read_text())
parser = json.loads((checks / 'canary-native-serving-parsers-all-v4.json').read_text())
assert projection['calls'] == projection['projected'] == parser['targets'] and not projection['errors']
assert loader['passed'] and loader['numerical_reference']['passed'] and parser['passed']
assert projection['lengths']['262144']['all_original_targets_once']
assert projection['closing_target_retained']
assert source_sha == hashlib.sha256(source.read_bytes()).hexdigest()
report = dict(checked_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
    trial_id=ident, source_export_sha256=source_sha, full_trial_targets=projection['calls'],
    all_targets_training_and_serving_prefix_identical=True, native_loader_collator_passed=True,
    cpu_loss_gradient_reference_passed=True, all_targets_once=True, closing_retained=True,
    model_resource=env['QWEN35_MODEL_PATH'],
    proofs={p.name:dict(path=str(p), sha256=hashlib.sha256(p.read_bytes()).hexdigest())
        for p in checks.glob('*.json')},
    model_calls=0, original_caches_modified=False, original_model_directory_modified=False,
    final_corpus_admission=False, remaining='Revalidate every final Task under the same frozen backend')
with (checks / 'TOKENIZER_FULL_TRIAL_ACCEPTANCE_R159.json').open('x') as stream:
    json.dump(report, stream, indent=2)
print(json.dumps(report))
