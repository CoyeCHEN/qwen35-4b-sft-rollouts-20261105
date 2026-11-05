"""Finite final SSD corpus assembly using the already accepted native audits.

All immutable final inputs must pass R340 first. Both pools and both context
views are fully read through the formal Loader/Collator. No training or GPU.
"""
import argparse
from collections import Counter
import datetime
import fcntl
import hashlib
import importlib.util
import inspect
import json
import os
from pathlib import Path
import shutil

S = Path('/ssd/chenkeyi/qwen35-new-cf500-tmax500-20261029')
E = Path('/home/chenkeyi/workspace/RSI/runtime-evidence/qwen35-new-cf500-tmax500-20261029')


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def load(name, expected):
    path = E / 'scripts' / (name + '.py')
    if sha(path) != expected:
        raise ValueError('Accepted native data audit source changed: ' + name)
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input-snapshot', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    inputs = args.input_snapshot.resolve()
    output = args.output.resolve()
    if not inputs.is_relative_to(S / 'data-final-inputs') or not output.is_relative_to(S / 'data-frozen') or output.exists():
        raise ValueError('Only new final SSD corpus roots are accepted')
    contract = json.loads((inputs / 'INPUTS.json').read_text())
    if contract.get('full_campaign_complete') is not True or contract.get('training_started') is not False:
        raise ValueError('A partial snapshot cannot be released as final')
    for name, value in contract['all_files'].items():
        path = inputs / name
        if not path.resolve().is_relative_to(inputs) or sha(path) != value['sha256']:
            raise ValueError('Frozen final input changed: ' + name)
    frozen_gate = json.loads((inputs / 'metadata/checks/data-finalization-readiness-r324.json').read_text())
    if frozen_gate['status'] != 'READY_FOR_FINAL_CORPUS_INPUT_FREEZE' or any(frozen_gate['blockers'].values()) or sha(inputs / 'metadata/checks/data-finalization-readiness-r324.json') != contract['final_gate_sha256']:
        raise ValueError('Final full-campaign gate is incomplete')
    for name in ['DEEPSEEK_API_KEY', 'OPENAI_API_KEY', 'GH_TOKEN']:
        os.environ.pop(name, None)
    os.environ.update(CUDA_VISIBLE_DEVICES='', QWEN35_MODEL_PATH=str(S / 'student-tokenizer-r155'),
        HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1', TOKENIZERS_PARALLELISM='false',
        OMP_NUM_THREADS='2', HF_DATASETS_CACHE=str(output / 'hf-cache'), TMPDIR=str(S / 'tmp'))
    os.environ['PYTHONPATH'] = str(E / 'sft-code-weight-audit-r3')
    import sys
    sys.path.insert(0, str(E / 'sft-code-weight-audit-r3'))
    native = load('assemble_primary_native_cache17_r241', '3628df89f5f4cb421c2461477a2a58cb5e82abb42719a42c0831e3a740e640c7')
    token_audit = load('audit_partial_primary_cache17_r238', 'd5114611c872ff3a9da7e1ba44bd1d69e6947ba76a1bd4a4ca45d04bafe44816')
    source = Path(inspect.getfile(native.audit_corpus)).parent
    expected = {'public_corpus.py': 'f28b1d3a0cbc28ceda3bd9eda188bb8240d972f078c3313472297d364d7f66e5',
                'public_corpus_audit.py': 'ff9d66dd6f9a1e97248fb4dd057d25497227099b8aa28ce4f09f2c4c66fc63aa',
                'teacher_segments.py': native.ENCODER_SHA}
    if any(sha(source / name) != digest for name, digest in expected.items()):
        raise ValueError('Frozen student audit implementation changed')
    policy = S / 'student-protocol-r256/STUDENT_DATA_AND_SERVING_POLICY_LOCK_R256.json'
    if sha(policy) != '86a11f1e1612b772ff4499a0327d80be7447270b268450659e3abdbb61065482':
        raise ValueError('Frozen joint student data and serving policy changed')
    output.mkdir(parents=True, exist_ok=False)
    lock = (output / 'assembly.lock').open('a')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    provenance = dict(scope='FINAL_ALL_SELECTED_TASKS_NATIVE_CACHE_FREEZE', full_campaign_complete=True,
        input_snapshot=str(inputs), input_snapshot_sha256=sha(inputs / 'INPUTS.json'),
        source_sha256=sha(Path(__file__)), all1000_task_gate_sha256=contract['final_gate_sha256'],
        source_indexes=contract['files'], qwen_revision=native.REVISION,
        official_template_sha256=native.TEMPLATE_SHA, canonical_backend_semantics_sha256=native.CANONICAL_BACKEND_SHA,
        token_source='Exact original native per-Trial Qwen caches; no retokenization or target edits',
        token_audit_source_sha256=sha(E / 'scripts/audit_partial_primary_cache17_r238.py'),
        assembly_source_sha256=sha(E / 'scripts/assemble_primary_native_cache17_r241.py'),
        token_audit_explicit_input_directory=str(inputs),
        joint_student_data_and_serving_policy_sha256=sha(policy),
        context_views_are_mutually_exclusive=True,
        serving_policy=dict(enable_thinking=True, reasoning_parser='qwen3',
            tool_call_parser='qwen3_coder', force_reasoning=True, separate_reasoning=True),
        corpus_release_requires_complete_data_audit=True, training_started=False)
    native.write_json(output / 'PLAN.json', provenance)
    shutil.copyfile(policy, output / policy.name)
    # Explicit input-directory binding only; accepted token/label audit code and
    # its historical report names remain byte-identical and retained as evidence.
    token_audit.D = inputs
    token_audit.audit()
    native.write_json(output / 'DATA_AUDIT_STARTED.json', dict(**provenance,
        complete=False, pools={}, model_calls=0, cuda_initialized=False))
    report = dict(**provenance, complete=False, pools={}, model_calls=0,
        raw_sources_changed=0, formal_training_started=False,
        numerical_reference_scope='Formal CPU miniature-model manual shifted loss/gradient reference; not a Qwen4B GPU run')
    for pool in ['calibforge', 'tmax']:
        records = [json.loads(line) for kind in ['SUCCESS_INDEX', 'FAILURE_OR_PENDING_INDEX']
            for line in (inputs / (pool.upper() + '_' + kind + '.jsonl')).open()]
        manifest = native.assemble_pool(pool, records, inputs, output / pool, provenance)
        manifest.update(status='FROZEN_FINAL_CACHE_REQUIRES_DATA_AUDIT',
            full_campaign_complete=True, actual_release_evidence='../DATA_AUDIT.json',
            release_condition='complete=true and both independent pool formal audits passed',
            external_publication=False, training_started=False)
        # Final manifest bytes are frozen before the formal Loader reads them.
        (output / pool / 'DATA_MANIFEST.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2))
        audit = native.audit_corpus(output / pool, model_path=str(S / 'student-tokenizer-r155'))
        if not audit['passed'] or not audit['all_caches_and_both_fixed_splits_read_through_formal_loader'] or not audit['all_row_labels_checked'] or audit['manifest_sha256'] != sha(output / pool / 'DATA_MANIFEST.json') or audit['cuda_initialized']:
            raise ValueError('Final native Loader/Collator or manifest audit failed')
        report['pools'][pool] = dict(qualified_independent_tasks=manifest['qualified_independent_tasks'],
            primary_trajectories=manifest['primary_trajectories'],
            manifest_sha256=sha(output / pool / 'DATA_MANIFEST.json'),
            formal_loader_audit_sha256=sha(output / pool / 'NATIVE_CACHE_AUDIT.json'),
            all_row_labels_verified=True, numerical_reference=audit['numerical_reference'],
            cached_rows=len(audit['rows']), length_views=manifest['length_views'],
            failure_or_quarantine_classifications=dict(Counter(x['classification'] for x in records if not x['qualified_success'])),
            independent_task_success_gap=500-manifest['qualified_independent_tasks'])
        native.write_json(output / (pool.upper() + '_DATA_AUDIT.json'), report['pools'][pool])
    for name in ['SAMPLING_MANIFEST.json', 'ACTIVE_1000_TASKS.jsonl']:
        shutil.copyfile(inputs / name, output / name)
    indexes = output / 'indexes'
    indexes.mkdir()
    for name in contract['files']:
        shutil.copyfile(inputs / name, indexes / name)
    shutil.copyfile(inputs / 'metadata/indexes/NATIVE_TRIAL_COST_TOKEN_LEDGER.jsonl', indexes / 'NATIVE_TRIAL_COST_TOKEN_LEDGER.jsonl')
    report.update(complete=True, status='FROZEN_BOTH_POOLS_FULL_LOADER_AND_TARGET_AUDIT_PASSED',
        checked_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        sampling_manifest_sha256=sha(output / 'SAMPLING_MANIFEST.json'),
        frozen_indexes={p.name: sha(p) for p in indexes.iterdir()},
        corpus_freeze_complete=True, external_publication=False, formal_training_started=False)
    native.write_json(output / 'DATA_AUDIT.json', report)
    print(json.dumps(dict(output=str(output), complete=True,
        pools={k:v['qualified_independent_tasks'] for k,v in report['pools'].items()},
        data_audit_sha256=sha(output / 'DATA_AUDIT.json'), training_started=False)))


if __name__ == '__main__':
    main()
