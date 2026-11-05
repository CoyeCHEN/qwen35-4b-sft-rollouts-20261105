"""Finite public-image download on149; verified durable storage on17. No model."""
from collections import Counter
import datetime
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import time
from verify_public_oci import verify, file_sha

R = Path(__file__).resolve().parents[1]
for key in ['DEEPSEEK_API_KEY', 'GH_TOKEN', 'GITHUB_TOKEN', 'OPENAI_API_KEY']:
    os.environ.pop(key, None)
os.environ['SSH_AUTH_SOCK'] = '/home/chenkeyi/.local/share/harbor-rsi/near-r3-20261015/auth.sock'
SSH = ['ssh', '-S', '/home/chenkeyi/.ssh/cf17-20261028.sock', '-oBatchMode=yes', '-oProxyCommand=false']
HOST = 'chenkeyi@180.163.192.17'
REMOTE = '/ssd/chenkeyi/qwen35-new-cf500-tmax500-20261029/registry/tasks-local-skopeo-r1'
CODE = '/home/chenkeyi/workspace/RSI/runtime-evidence/qwen35-new-cf500-tmax500-20261029/scripts/stage_public_oci_receipt_17.py'
PY = '/home/chenkeyi/workspace/RSI/runtime-evidence/qwen35-length-lf-audit-20261023/.venv/bin/python'
TOOL = R / 'tools/skopeo/bin/skopeo'
rows = list(map(json.loads, (R / 'manifests/CALIBFORGE_500_TASKS.jsonl').open()))
plan = R / 'manifests/CF_PUBLIC_OCI_PREFETCH_REMOTE149_R3.json'
if plan.exists():
    raise FileExistsError('Inspect existing finite pass before resumption')
plan.write_text(json.dumps(dict(task_ids=[r['task_id'] for r in rows],
    task_manifest_sha256=file_sha(R / 'manifests/CALIBFORGE_500_TASKS.jsonl'),
    tool_sha256=file_sha(TOOL), download_host='149', durable_archive_host='17',
    local_environment_builds=0, model_calls=0, worker_count=1), indent=2))
transit = R / 'sources/public-oci-remote149-transit-r3'
transit.mkdir(exist_ok=True)
observed = []

def run(args, **kwargs):
    return subprocess.run(args, check=True, **kwargs)

for row in sorted(rows, key=lambda x: x['task_id']):
    ident = row['task_id']
    source = json.loads((R / 'checks/cf-public-image-identities' / (ident + '.json')).read_text())
    start = time.monotonic()
    item = dict(task_id=ident, pinned=source['pinned'])
    try:
        old = R / 'checks/cf-environments-oci-r5' / (ident + '.json')
        if old.exists() and json.loads(old.read_text()).get('status') == 'IMAGE_IDENTITY_AND_BASIC_SETUP_PASSED':
            item['status'] = 'ALREADY_PREPARED_ON_149'
        else:
            dest = REMOTE + '/' + ident
            exists = subprocess.run(SSH + [HOST, 'test -f ' + shlex.quote(dest + '/cache.json')], capture_output=True, timeout=20)
            if exists.returncode == 0:
                item['status'] = 'ALREADY_STAGED_ON_17'
            elif exists.returncode != 1:
                raise RuntimeError('Archive inventory SSH failure; not a missing image')
            else:
                if shutil.disk_usage(R).free < 100 * 1024**3:
                    raise RuntimeError('149 transit headroom below100GiB')
                directory = transit / ident
                directory.mkdir(exist_ok=True)
                archive = directory / 'image.oci.tar'
                with (directory / 'copy.log').open('x') as log:
                    run([str(TOOL), '--policy', str(R / 'tools/skopeo/policy.json'), 'copy',
                        '--preserve-digests', '--retry-times', '2', '--src-no-creds',
                        'docker://docker.io/' + source['pinned'], 'oci-archive:' + str(archive) + ':' + ident],
                        stdout=log, stderr=subprocess.STDOUT, timeout=1200)
                value = verify(source, archive)
                value['cache_transport'] = 'Native Skopeo1.13.3 on149; verified public archive stored17'
                receipt = directory / 'cache-origin.json'
                receipt.write_text(json.dumps(value, indent=2))
                run(SSH + [HOST, 'mkdir -p ' + shlex.quote(dest)], timeout=20)
                run(['rsync', '-a', '--bwlimit=8192', '-e', shlex.join(SSH), str(archive), HOST + ':' + dest + '/image.oci.tar'], timeout=1800)
                run(['rsync', '-a', '-e', shlex.join(SSH), str(receipt), HOST + ':' + dest + '/cache-origin.json'], timeout=30)
                proof = run(SSH + [HOST, shlex.join([PY, CODE, ident])], capture_output=True, text=True, timeout=300)
                item.update(status='VERIFIED_OFFICIAL_ARCHIVE_DURABLE_ON_17', archive_sha256=value['archive_sha256'], remote_proof=proof.stdout.strip())
                archive.unlink()  # Only this pass's duplicate, after remote independent verification.
    except (OSError, ValueError, AssertionError, RuntimeError, subprocess.SubprocessError) as error:
        item.update(status='PUBLIC_ASSET_PREPARATION_FAILED', error_type=type(error).__name__, error=str(error)[:350])
    item['seconds'] = time.monotonic() - start
    observed.append(item)
    state = dict(status='PREPARING_PUBLIC_ARCHIVES_REMOTELY', pid=os.getpid(),
        checked_at=datetime.datetime.now(datetime.timezone.utc).isoformat(), planned_tasks=500,
        observed_tasks=len(observed), counts=dict(Counter(x['status'] for x in observed)),
        records=observed, model_calls=0, local_environment_builds=0)
    path = R / 'checks/cf-public-oci-remote149-r3.json'
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(state, indent=2))
    tmp.replace(path)
    print(json.dumps(item), flush=True)
state['status'] = 'ALL_500_PUBLIC_ARCHIVES_OBSERVED'
path.write_text(json.dumps(state, indent=2))
