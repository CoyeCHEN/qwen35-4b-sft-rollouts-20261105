"""Release unadmitted CF warm caches already held by the storage guard.

Exact original archives are rehashed on17 before removal. No active, referenced,
previously dispatched or unbacked image is eligible. Native Docker rmi only.
"""
from pathlib import Path
import datetime
import hashlib
import json
import os
import shlex
import shutil
import subprocess
import sys
from native_image_archive149_r1 import R, SSH, HOST, PY17, E17, image_info, load_verified_archive
from run_collection_stream_r3 import attempt_counts


def run(args, timeout=30, **kwargs):
    return subprocess.run(args, capture_output=True, text=True, check=True, timeout=timeout, **kwargs)


def protected():
    result = set(attempt_counts())
    result.update(json.loads((R / 'campaign-state.json').read_text())['active_task_pipelines'])
    result.update(json.loads(p.read_text())['task_id'] for p in R.glob('stream/*/dispatches/*/dispatch.json'))
    return result


def cold_proof(ident, image):
    program = '''import sys,json
sys.path.insert(0,sys.argv[1])
from resolve_cold_image17_r1 import resolve
from inspect_cold_oci_r1 import sha_file
p=resolve(sys.argv[2],sys.argv[3],'calibforge')
if sha_file(p['archive'])!=p['archive_sha256']:raise ValueError('Cold original archive SHA mismatch')
print(json.dumps(p))'''
    reply = run(SSH + [HOST, shlex.join([PY17, '-c', program, E17 + '/scripts', ident, image])], timeout=1800)
    return json.loads(reply.stdout)


def main():
    for key in ['DEEPSEEK_API_KEY', 'GH_TOKEN']:
        os.environ.pop(key, None)
    os.environ['SSH_AUTH_SOCK'] = '/home/chenkeyi/.local/share/harbor-rsi/near-r3-20261015/auth.sock'
    output = R / 'checks/capacity-held-cf-image-eviction-r1.json'
    if output.exists():
        raise FileExistsError('Observe the preserved finite warm-cache release')
    rows = {x['task_id']: x for x in map(json.loads, (R / 'manifests/CALIBFORGE_500_TASKS.jsonl').open())}
    candidates = []
    for ident, row in rows.items():
        path = R / 'checks/cf-environments-oci-r5' / (ident + '.json')
        if not path.exists():
            continue
        marker = json.loads(path.read_text())
        if marker['status'] != 'IMAGE_BASIC_PASSED_CAPACITY_HOLD' or ident in protected():
            continue
        info = image_info(marker['image_id'])
        if info:
            candidates.append((info['Size'], ident, path, info))
    candidates.sort(reverse=True)
    before = shutil.disk_usage(R).free; records = []
    for _, ident, path, info in candidates:
        entry = dict(task_id=ident, image_id=info['Id'])
        try:
            if ident in protected() or json.loads(path.read_text())['status'] != 'IMAGE_BASIC_PASSED_CAPACITY_HOLD':
                entry['status'] = 'SKIPPED_ADMITTED_OR_RELEASED_HOLD'; continue
            allowed = {rows[ident]['docker_image'], ident, ident + ':latest'}
            if not info.get('RepoTags') or not set(info['RepoTags']) <= allowed:
                entry['status'] = 'SKIPPED_UNEXPECTED_IMAGE_TAGS'; continue
            refs = run(['docker', 'ps', '-aq', '--filter', 'ancestor=' + info['Id']])
            if refs.stdout.strip():
                entry['status'] = 'SKIPPED_CONTAINER_REFERENCE'; continue
            proof = cold_proof(ident, info['Id'])
            if ident in protected() or run(['docker', 'ps', '-aq', '--filter', 'ancestor=' + info['Id']]).stdout.strip():
                entry['status'] = 'SKIPPED_NEW_REFERENCE'; continue
            # Only this task's own aliases may be untagged; no force or global prune.
            if len(info['RepoTags']) > 1:
                canonical = [tag for tag in info['RepoTags'] if ':' in tag]
                if canonical:
                    run(['docker', 'image', 'rm', *canonical], timeout=120)
            removed = run(['docker', 'image', 'rm', info['Id']], timeout=180)
            entry.update(status='UNADMITTED_EXACT_CF_WARM_CACHE_RELEASED',
                archive=proof['archive'], archive_sha256=proof['archive_sha256'],
                all_original_hashes_verified=proof['all_original_manifest_config_layer_and_diffid_hashes_verified'],
                native_removal_stdout=removed.stdout[-1000:])
        except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
            entry.update(status='CACHE_RETAINED_OR_REMOVAL_REFUSED', error_type=type(error).__name__, reason=str(error)[:800])
        finally:
            records.append(entry)
            value = dict(checked_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                records=records, original_free_bytes=before, current_free_bytes=shutil.disk_usage(R).free,
                original_tasks_tests_trials_recorders_or_archives_deleted=0, active_pipelines_cancelled=0,
                force_or_global_prune_actions=0, model_calls=0)
            temporary = output.with_suffix('.tmp'); temporary.write_text(json.dumps(value, indent=2)); temporary.replace(output)
            print(json.dumps(entry), flush=True)
        if shutil.disk_usage(R).free >= 100 * 1024**3:
            break


if __name__ == '__main__':
    main()
