"""Release only qualified, idle CF image caches after remote byte verification.

Original Task files, raw results and SSD archives remain intact. No global prune,
force removal, teacher dispatch or changes to an active Trial are performed.
"""
from pathlib import Path
import datetime
import json
import os
import shlex
import shutil
import subprocess

R = Path('/home/chenkeyi/.local/share/harbor-rsi/qwen35-new-cf500-tmax500-20261029')
E17 = '/home/chenkeyi/workspace/RSI/runtime-evidence/qwen35-new-cf500-tmax500-20261029'
PY17 = '/home/chenkeyi/workspace/RSI/runtime-evidence/qwen35-length-lf-audit-20261023/.venv/bin/python'
SSH = ['ssh', '-S', '/home/chenkeyi/.ssh/cf17-20261028.sock', '-oBatchMode=yes', '-oProxyCommand=false', 'chenkeyi@180.163.192.17']
os.environ['SSH_AUTH_SOCK'] = '/home/chenkeyi/.local/share/harbor-rsi/near-r3-20261015/auth.sock'
for key in ['DEEPSEEK_API_KEY', 'GH_TOKEN']:
    os.environ.pop(key, None)


def run(args, timeout=30):
    return subprocess.run(args, capture_output=True, text=True, timeout=timeout)


def success_ids():
    return {json.loads(line)['task_id'] for line in (R / 'indexes/CALIBFORGE_SUCCESS_INDEX.jsonl').open()}


def main():
    output = R / 'checks/qualified-public-image-cache-release-r12.json'
    if output.exists():
        raise FileExistsError('Inspect the preserved finite release pass before resumption')
    rows = {x['task_id']: x for x in map(json.loads, (R / 'manifests/CALIBFORGE_500_TASKS.jsonl').open())}
    records = []
    before = shutil.disk_usage(R).free
    for ident in sorted(success_ids()):
        item = dict(task_id=ident)
        try:
            state = json.loads((R / 'campaign-state.json').read_text())
            if ident in state['active_task_pipelines']:
                item['status'] = 'SKIPPED_ACTIVE_PIPELINE'
                continue
            receipt = R / 'checks/cf-environments-oci-r5' / (ident + '.json')
            evidence = json.loads(receipt.read_text())
            info = run(['docker', 'image', 'inspect', evidence['image_id']])
            if info.returncode:
                item['status'] = 'CACHE_ALREADY_ABSENT'
                continue
            image = json.loads(info.stdout)[0]
            expected = {rows[ident]['docker_image'], ident, ident + ':latest'}
            tags = image.get('RepoTags') or []
            if not tags or not set(tags) <= expected:
                item.update(status='SKIPPED_UNEXPECTED_IMAGE_TAGS', tags=tags)
                continue
            refs = run(['docker', 'ps', '-a', '--filter', 'ancestor=' + image['Id'], '--format', '{{.ID}}'])
            refs.check_returncode()
            if refs.stdout.strip():
                item['status'] = 'SKIPPED_CONTAINER_REFERENCE'
                continue
            # Read and hash every original descriptor on17, not only cache.json.
            code = '''from pathlib import Path
import json,sys
sys.path.insert(0,sys.argv[1]);from verify_public_oci import verify,file_sha
ident=sys.argv[2];s=Path('/ssd/chenkeyi/qwen35-new-cf500-tmax500-20261029/registry')
for name in ['tasks-local-skopeo-r1','tasks']:
 p=s/name/ident/'cache.json'
 if not p.exists():continue
 x=json.loads(p.read_text());a=Path(x['archive']).resolve()
 if not a.is_relative_to(s):raise ValueError('Archive outside campaign SSD')
 if file_sha(a)!=x['archive_sha256']:raise ValueError('Original archive hash mismatch')
 v=verify(x['source'],a)
 if v['image_id']!=sys.argv[3]:raise ValueError('Original image identity differs')
 print(json.dumps(dict(receipt=str(p),archive=str(a),archive_sha256=v['archive_sha256'],image_id=v['image_id'],all_original_blobs_verified=True)));break
else:raise FileNotFoundError('No verified cold archive; keep149 cache')
'''
            command = shlex.join([PY17, '-c', code, E17 + '/scripts', ident, image['Id']])
            cold = run(SSH + [command], timeout=180)
            if cold.returncode:
                item.update(status='RETAINED_COLD_ARCHIVE_UNAVAILABLE_OR_INVALID', error=cold.stderr[-500:])
                continue
            proof = json.loads(cold.stdout)
            # Recheck both dynamic ownership conditions immediately before rmi.
            if ident not in success_ids() or ident in json.loads((R / 'campaign-state.json').read_text())['active_task_pipelines']:
                raise ValueError('Qualified terminal task ownership changed')
            refs = run(['docker', 'ps', '-a', '--filter', 'ancestor=' + image['Id'], '--format', '{{.ID}}'])
            refs.check_returncode()
            if refs.stdout.strip():
                raise ValueError('A container now references this image; retained')
            if len(tags)>1:
                canonical=[tag for tag in tags if ':' in tag]
                if canonical:
                    untagged=run(['docker','image','rm',*canonical],timeout=120)
                    untagged.check_returncode()
            removed = run(['docker', 'image', 'rm', image['Id']], timeout=120)
            item.update(status='QUALIFIED_IDLE_IMAGE_CACHE_RELEASED' if removed.returncode == 0 else 'CACHE_RELEASE_REFUSED',
                image_id=image['Id'], tags=tags, remote_cold_archive=proof, returncode=removed.returncode,
                stdout=removed.stdout[-1000:], stderr=removed.stderr[-500:])
        except (OSError, ValueError, subprocess.SubprocessError) as error:
            item.update(status='CACHE_RETAINED_ON_EXPLICIT_ERROR', error_type=type(error).__name__, error=str(error)[:500])
        finally:
            records.append(item)
            value = dict(checked_at=datetime.datetime.now(datetime.timezone.utc).isoformat(), records=records,
                before_free_bytes=before, after_free_bytes=shutil.disk_usage(R).free,
                raw_artifact_deletions=0, task_modifications=0, model_calls=0, global_prune_actions=0)
            temp = output.with_suffix('.tmp'); temp.write_text(json.dumps(value, indent=2)); temp.replace(output)
            print(json.dumps(item), flush=True)


if __name__ == '__main__':
    main()
