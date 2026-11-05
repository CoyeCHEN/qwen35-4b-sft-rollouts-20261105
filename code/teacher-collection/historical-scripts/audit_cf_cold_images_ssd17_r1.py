"""Finite CF500 expanded image audit on17; no downloads, builds or model calls."""
from pathlib import Path
from collections import Counter
import datetime
import fcntl
import hashlib
import json
import os
import tarfile
import time
from inspect_cold_oci_r1 import inspect_archive, publish, S

R = Path('/home/chenkeyi/workspace/RSI/runtime-evidence/qwen35-new-cf500-tmax500-20261029')
for key in ['DEEPSEEK_API_KEY', 'GH_TOKEN', 'OPENAI_API_KEY']:
    os.environ.pop(key, None)


def main():
    lock = (R / 'checks/cf-cold-sizes-r1.lock').open('a'); fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    allowed = sorted(os.sched_getaffinity(0)); os.sched_setaffinity(0, allowed[:2])
    source = R / 'manifests/CF_PUBLIC_OCI_REMOTE17_R5.json'
    plan = json.loads(source.read_text()); rows = plan['tasks']
    if len(rows) != 500 or len({x['task_id'] for x in rows}) != 500:
        raise ValueError('Original500 task scope differs')
    statefile = R / 'checks/cf-cold-sizes-r1.json'; counts = Counter(); records = []
    for row in rows:
        ident = row['task_id']; started = time.monotonic()
        try:
            cached = next(json.loads(p.read_text()) for name in ['tasks-local-skopeo-r1', 'tasks']
                if (p := S / 'registry' / name / ident / 'cache.json').exists())
            if cached['pinned'] != row['source']['pinned']:
                raise ValueError('Frozen public image source differs')
            receipt = R / 'checks/cold-image-sizes-r1' / (ident + '.json')
            if receipt.exists():
                value = json.loads(receipt.read_text())
                if value['archive_sha256'] != cached['archive_sha256'] or value['image_id'] != cached['image_id']:
                    raise ValueError('Previously audited immutable image differs')
            else:
                value = inspect_archive(cached['archive'], cached['image_id'], cached['archive_sha256'])
                publish(receipt, value)
            item = dict(task_id=ident, status=value['status'], archive_sha256=value['archive_sha256'],
                archive_bytes=value['archive_bytes'], expanded_layer_tar_bytes=value['expanded_layer_tar_bytes'])
        except (OSError, ValueError, KeyError, StopIteration, tarfile.TarError) as error:
            item = dict(task_id=ident, status='COLD_IMAGE_INSPECTION_FAILED', error_type=type(error).__name__, error=str(error)[:800])
        item['seconds'] = time.monotonic() - started; records.append(item); counts[item['status']] += 1
        state = dict(status='AUDITING_ORIGINAL_CF500_COLD_IMAGES', pid=os.getpid(),
            checked_at=datetime.datetime.now(datetime.timezone.utc).isoformat(), observed_tasks=len(records),
            planned_tasks=500, counts=dict(counts), records=records, model_calls=0, source_plan_sha256=hashlib.sha256(source.read_bytes()).hexdigest())
        temp = statefile.with_suffix('.tmp'); temp.write_text(json.dumps(state, indent=2)); temp.replace(statefile)
        print(json.dumps(item), flush=True)
    state['status'] = 'ORIGINAL_CF500_COLD_IMAGE_AUDIT_TERMINAL'
    statefile.write_text(json.dumps(state, indent=2))


if __name__ == '__main__':
    main()
