"""Copy only closed, preregistered E3 evidence for the unchanged readonly reader."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shlex
import subprocess
import time

R = Path('/ssd/chenkeyi/qwen35-sft-772-20261101')
DEST = R / 'formal-native-eval-r1'
SOURCE = '/home/chenkeyi/.local/share/harbor-rsi/qwen35-new772-tb21-20261101'
SSH = ['/usr/bin/ssh', '-F', str(R / 'control-ssh/formal-engine149-r1.conf'), '127.0.0.1']
COLLECT = r'''
from pathlib import Path
import hashlib,json,os,time
r=Path(SOURCE)
jobs=['qwen35-new772-new-m1-epoch3-fixed-diagnostic',
 'qwen35-new772-new-m1-epoch3-fixed-unstarted-continuation-r1',
 'qwen35-new772-new-m2-epoch3-fixed-diagnostic']
files={};closed=[]
def add(p):
 if p.is_symlink():files[str(p.relative_to(r))]=dict(type='symlink',target=os.readlink(p));return
 if p.is_file():
  with p.open('rb')as stream:digest=hashlib.file_digest(stream,'sha256').hexdigest()
  files[str(p.relative_to(r))]=dict(type='file',bytes=p.stat().st_size,sha256=digest)
for job in jobs:
 for result in sorted((r/'jobs'/job).glob('*/result.json')):
  raw=json.loads(result.read_text());assert raw['finished_at']
  assert raw['config']['agent']['kwargs']['wheel_sha256']=='1d27eef1ca6696275f306d8c653f7a266a4c7aea7321f0d47fd01b739c27fa18'
  closed.append(dict(job=job,trial_name=raw['trial_name'],trial_id=raw['id'],result_sha256=hashlib.sha256(result.read_bytes()).hexdigest()))
  for path in sorted(result.parent.rglob('*')):add(path)
for relative in ['checks/E3_NATIVE_CONTROLLER_OOM_SNAPSHOT_R1.json',
 'manifests/E3_ORIGINAL_UNSTARTED_ACTUAL_NATIVE_TRIALS_R1.json',
 'recovery/e3-controller-oom-20261102-r1/regex-log/RAW_RECORDER_VALIDATION.json',
 'recovery/e3-controller-oom-20261102-r1/chess-best-move/ORIGINAL_ORPHAN_AGENT_CLOSED_AND_ARCHIVED.json']:
 add(r/relative)
for task in ['regex-log','chess-best-move']:
 add(r/'jobs/qwen35-new772-new-m1-epoch3-fixed-diagnostic'/(task+'__new-m1-e3-fixed-r1')/'config.json')
print(json.dumps(dict(at=time.time(),source_root=str(r),closed_trials=closed,files=files,live_trials_excluded=True)))
'''


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def matches(path, expected):
    if expected['type'] == 'symlink':
        return path.is_symlink() and os.readlink(path) == expected['target']
    return path.is_file() and not path.is_symlink() and path.stat().st_size == expected['bytes'] and sha(path) == expected['sha256']


def main(manifest_only):
    source = COLLECT.replace('Path(SOURCE)', 'Path(' + repr(SOURCE) + ')')
    run = subprocess.run(SSH + ['/home/chenkeyi/.local/share/harbor-rsi/qwen35-m1-m2-tb21-20261026/venv/bin/python -'],
        input=source, capture_output=True, text=True, timeout=600, check=True)
    manifest = json.loads(run.stdout)
    revision = DEST / 'cross-node-evidence' / str(time.time_ns())
    revision.mkdir(parents=True)
    (revision / 'source.json').write_text(json.dumps(manifest, indent=2) + '\n')
    if manifest_only:
        print(json.dumps(dict(manifest_only=True, closed_trials=len(manifest['closed_trials']),
            files=len(manifest['files']), bytes=sum(v.get('bytes',0) for v in manifest['files'].values()),
            manifest=str(revision/'source.json'), actual_new_task_or_model_calls=0)))
        return
    pending = []
    for relative, expected in manifest['files'].items():
        path = DEST / relative
        if path.exists() or path.is_symlink():
            assert matches(path, expected), 'Preserve conflicting evidence: ' + relative
        else:
            pending.append(relative)
    paths = revision / 'files.nul'
    paths.write_bytes(b''.join(n.encode() + b'\0' for n in pending))
    if pending:
        subprocess.run(['/usr/bin/rsync','-a','--no-owner','--no-group','--ignore-existing','--from0',
            '--files-from='+str(paths), '-e', shlex.join(SSH[:-1]),
            'chenkeyi@127.0.0.1:' + SOURCE + '/', str(DEST) + '/'], check=True, timeout=7200)
    assert all(matches(DEST / n, expected) for n, expected in manifest['files'].items())
    proof = dict(passed=True, at=time.time(), source_node='149', replica_node='18',
        closed_trials=manifest['closed_trials'], files=len(manifest['files']),
        bytes=sum(v.get('bytes',0) for v in manifest['files'].values()),
        source_manifest=str(revision/'source.json'), source_manifest_sha256=sha(revision/'source.json'),
        copied_files=len(pending), official_results_and_recorders_not_rewritten=True,
        no_live_trial_copied=True, no_new_task_or_model_calls=True,
        source_sha256=sha(Path(__file__)))
    (revision/'receipt.json').write_text(json.dumps(proof,indent=2)+'\n')
    path = R/'checks/E3_CLOSED_EVIDENCE_REPLICA_STATUS_R1.json'
    temp = path.with_suffix('.tmp');temp.write_text(json.dumps(proof,indent=2)+'\n');temp.replace(path)
    print(json.dumps(proof))


if __name__ == '__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--manifest-only',action='store_true')
    main(parser.parse_args().manifest_only)
