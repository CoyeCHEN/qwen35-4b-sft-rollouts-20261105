"""Finite SSD-only CPU snapshot audit; collection and its data writer continue."""
import datetime
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess

E = Path('/home/chenkeyi/workspace/RSI/runtime-evidence/qwen35-new-cf500-tmax500-20261029')
S = Path('/ssd/chenkeyi/qwen35-new-cf500-tmax500-20261029')
D = S / 'data-combined-audit-r242'
PY = '/home/chenkeyi/workspace/RSI/runtime-evidence/qwen35-length-lf-audit-20261023/.venv/bin/python'
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    D.mkdir(exist_ok=False)
    lock = (D / 'audit.lock').open('a')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    stages = ['audit_partial_primary_cache17_r238.py', 'assemble_primary_native_cache17_r241.py']
    sources = {name: sha(E / 'scripts' / name) for name in stages}
    assert sources == {
        'audit_partial_primary_cache17_r238.py': 'd5114611c872ff3a9da7e1ba44bd1d69e6947ba76a1bd4a4ca45d04bafe44816',
        'assemble_primary_native_cache17_r241.py': '3628df89f5f4cb421c2461477a2a58cb5e82abb42719a42c0831e3a740e640c7',
    }
    env = dict(os.environ, CUDA_VISIBLE_DEVICES='', PYTHONPATH=str(E / 'sft-code-weight-audit-r3'),
        QWEN35_MODEL_PATH=str(S / 'student-tokenizer-r155'), HF_HUB_OFFLINE='1',
        TRANSFORMERS_OFFLINE='1', TOKENIZERS_PARALLELISM='false', OMP_NUM_THREADS='2',
        HF_DATASETS_CACHE=str(D / 'hf-cache'), TMPDIR=str(S / 'tmp'))
    (S / 'tmp').mkdir(exist_ok=True)
    for name in ['DEEPSEEK_API_KEY', 'OPENAI_API_KEY', 'GH_TOKEN']:
        env.pop(name, None)
    plan = dict(checked_at=datetime.datetime.now(datetime.timezone.utc).isoformat(), pid=os.getpid(),
        stage='STARTED', sources=sources, input_snapshot=str(S / 'data-primary-snapshots/r238'),
        input_snapshot_sha256=sha(S / 'data-primary-snapshots/r238/INPUTS.json'),
        output=str(S / 'data-corpus-snapshots/r242'), canonical_resource=env['QWEN35_MODEL_PATH'],
        full_campaign_complete=False, formal_release=False, training_started=False,
        teacher_calls=0, teacher_or_data_writer_signals=0)

    def save(stage, **details):
        plan.update(stage=stage, checked_at=datetime.datetime.now(datetime.timezone.utc).isoformat(), **details)
        temp = D / 'state.pending'
        temp.write_text(json.dumps(plan, indent=2))
        temp.replace(D / 'state.json')

    save('CANONICAL_GAP_REVALIDATION_PENDING')
    preflight = '''import importlib.util,json,sys
from pathlib import Path
p=Path(sys.argv[1]);spec=importlib.util.spec_from_file_location('combined',p);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
counts={};historical=0
for pool in ['CALIBFORGE','TMAX']:
 rows=[r for line in (m.SSD/'data-primary-snapshots/r238'/(pool+'_SUCCESS_INDEX.jsonl')).open() if (r:=json.loads(line))['is_primary_trajectory']]
 for row in rows:
  bound=m.canonical_binding(row)
  historical+=bool(bound.get('proofs'))
 counts[pool]=len(rows)
print(json.dumps(dict(passed=True,counts=counts,historical_revalidated=historical,source_journal_or_cache_changes=0)))
'''
    try:
        gap_source=E/'scripts/audit_canonical_primary17_r240.py'
        assert sha(gap_source)=='a0cff6cb1e858c63333c7ff5a86e440475760edb9580a5133eb188f172ac5749'
        save('CANONICAL_GAP_REVALIDATION_RUNNING')
        jobs=[]
        for label,interpreter in [('training',PY),('serving','/ssd/chenkeyi/qwen35-m2-eval-20261026/serving-env/bin/python')]:
            log=(D/(label+'-canonical-gap-revalidation.log')).open('x')
            child=subprocess.Popen([interpreter,str(gap_source),label],env=env,stdout=log,stderr=subprocess.STDOUT)
            jobs.append((label,child,log))
        for label,child,log in jobs:
            status=child.wait(timeout=21600);log.close()
            if status:raise subprocess.CalledProcessError(status,child.args)
        gap_file=S/'data-canonical-gaps-r239/PLAN.json';gap=json.loads(gap_file.read_text())
        for label,_,_ in jobs:
            proof=json.loads((S/'data-canonical-primary-r240'/label/'PROGRESS.json').read_text())
            assert proof['status']=='COMPLETE' and proof['passed_tasks']==len(gap['missing_two_runtime_revalidation']) and not proof['failed_trial_ids']
            assert proof['gap_manifest_sha256']==sha(gap_file)
        save('CANONICAL_BINDING_PREFLIGHT')
        reply = subprocess.run([PY, '-c', preflight, str(E / 'scripts' / stages[1])],
            env=env, capture_output=True, text=True, check=True, timeout=180)
        (D / 'canonical-binding-preflight.json').write_text(reply.stdout)
        save('ALL_NATIVE_CACHE_TOKEN_LABEL_MAPPING_AUDIT')
        with (D / 'native-cache-label-audit.log').open('x') as stream:
            subprocess.run([PY, str(E / 'scripts' / stages[0])], env=env,
                stdout=stream, stderr=subprocess.STDOUT, check=True, timeout=21600)
        save('ASSEMBLY_AND_FORMAL_LOADER_COLLATOR_AUDIT')
        with (D / 'combined-formal-loader-audit.log').open('x') as stream:
            subprocess.run([PY, str(E / 'scripts' / stages[1]), '--input-snapshot',
                str(S / 'data-primary-snapshots/r238'), '--output', str(S / 'data-corpus-snapshots/r242')],
                env=env, stdout=stream, stderr=subprocess.STDOUT, check=True, timeout=21600)
        save('PARTIAL_SNAPSHOT_COMBINED_AUDIT_COMPLETE', passed=True)
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        save('PARTIAL_SNAPSHOT_AUDIT_FAILED', passed=False, error_type=type(error).__name__,
             error=str(error)[-500:])
        if isinstance(error, subprocess.CalledProcessError) and error.stderr:
            (D / 'preflight-error.txt').write_text(error.stderr)
        raise


if __name__ == '__main__':
    main()
