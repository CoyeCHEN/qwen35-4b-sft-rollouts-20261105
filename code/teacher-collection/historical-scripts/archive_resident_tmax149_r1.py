"""Archive the currently resident original TMax images to owned17 SSD.

Finite source-preparation pass, one transfer at a time. No cache deletion,
teacher dispatch, task replacement or model credential is involved.
"""
from pathlib import Path
from collections import Counter
import datetime
import fcntl
import hashlib
import json
import os
import subprocess
from native_image_archive149_r1 import archive_image, image_info, ImageCapacityError, R


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    for key in ['DEEPSEEK_API_KEY', 'GH_TOKEN']:
        os.environ.pop(key, None)
    os.environ['SSH_AUTH_SOCK'] = '/home/chenkeyi/.local/share/harbor-rsi/near-r3-20261015/auth.sock'
    lock = (R / 'checks/native-tmax-resident-archive-r1.lock').open('a')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    manifest = R / 'manifests/TMAX_RUNTIME_CANDIDATES_V2.jsonl'
    rows = list(map(json.loads, manifest.open())); planned = []
    for row in rows:
        ident = row['task_id']
        for name in ['tmax-environments-public-input-review-r6', 'tmax-environments-collision-recheck-r5', 'tmax-environments-runtime-r4']:
            path = R / 'checks' / name / (ident + '.json')
            if not path.exists():
                continue
            check = json.loads(path.read_text())
            if check['status'] == 'IMAGE_AND_ORIGINAL_INITIAL_STATE_PASSED_FINAL_VERIFIER_PENDING':
                image = image_info(check['image_id'])
                if image is not None:
                    planned.append(dict(row=row, image_id=check['image_id'], preparation_receipt=str(path),
                        preparation_receipt_sha256=sha(path), build_context_sha256=check['build_context_sha256']))
                break
    planfile = R / 'manifests/TMAX_RESIDENT_IMAGE_ARCHIVE_PLAN_R1.json'
    if planfile.exists():
        raise FileExistsError('Observe existing finite archive pass before resumption')
    planfile.write_text(json.dumps(dict(tasks=planned, source_manifest_sha256=sha(manifest),
        model_calls=0, image_deletions=0, source_images_remain_resident=True), indent=2))
    records = []
    for item in planned:
        row = item['row']; ident = row['task_id']
        try:
            identity = dict(dataset_revision=row['revision'], task_json_sha256=row['task_json_sha256'],
                setup_sha256=row['setup_sha256'], preparation_receipt_sha256=item['preparation_receipt_sha256'],
                build_context_sha256=item['build_context_sha256'])
            proof = archive_image(ident, item['image_id'], 'tmax', identity)
            record = dict(task_id=ident, status='ORIGINAL_NATIVE_IMAGE_ARCHIVED_AND_VERIFIED',
                image_id=item['image_id'], archive_sha256=proof['archive_sha256'], archive_bytes=proof['archive_bytes'])
        except ImageCapacityError as error:
            record = dict(task_id=ident, status='IMAGE_ARCHIVAL_CAPACITY_BLOCKED', reason=str(error))
        except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
            record = dict(task_id=ident, status='IMAGE_ARCHIVAL_FAILED', error_type=type(error).__name__, reason=str(error)[:800])
        records.append(record)
        value = dict(status='ARCHIVING_RESIDENT_ORIGINAL_TMAX_IMAGES', pid=os.getpid(),
            checked_at=datetime.datetime.now(datetime.timezone.utc).isoformat(), planned_tasks=len(planned),
            observed_tasks=len(records), counts=dict(Counter(x['status'] for x in records)), records=records,
            model_calls=0, image_deletions=0, original_task_modifications=0)
        path = R / 'checks/native-tmax-resident-archive-r1.json'; temporary = path.with_suffix('.tmp')
        temporary.write_text(json.dumps(value, indent=2)); temporary.replace(path)
        print(json.dumps(record), flush=True)
    value['status'] = 'FINITE_ORIGINAL_IMAGE_ARCHIVAL_TERMINAL'
    path.write_text(json.dumps(value, indent=2))


if __name__ == '__main__':
    main()
