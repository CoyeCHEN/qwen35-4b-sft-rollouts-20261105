"""Retain two already-attempted historical images after the348 archive completes.

This never builds or loads an image, never prepares a future Task on149,
and never dispatches a teacher. The original archival lock is reused.
"""
import datetime
import fcntl
import json
import os
from pathlib import Path
import time

from native_image_archive149_r1 import R, archive_image
import collection_readiness_r7 as n


S = R / 'stream/historical-attempted-archive-delta-r35'


def main():
    S.mkdir(exist_ok=True)
    own_lock = (S / 'worker.lock').open('a')
    fcntl.flock(own_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    plan_path = R / 'manifests/HISTORICAL_ATTEMPTED_IMAGE_RETENTION_DELTA_R35.json'
    plan = json.loads(plan_path.read_text())
    source = R / 'scripts/archive_resident_tmax149_unlimited_r2.py'
    if n.sha(source) != plan['previous_source_sha256']:
        raise ValueError('Existing historical archiver source changed')
    policy = json.loads(Path(plan['bandwidth_policy']).read_text())
    if n.sha(Path(policy['entrypoint'])) != policy['entrypoint_sha256']:
        raise ValueError('Authorized dedicated rsync entrypoint changed')
    if (S / 'PLAN.json').exists():
        raise FileExistsError('Observe the preserved historical delta; never replay blindly')
    n.freeze(S / 'PLAN.json', dict(plan, worker_source_sha256=n.sha(Path(__file__))))
    records = []

    def state(stage):
        value = dict(pid=os.getpid(), checked_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
            stage=stage, planned=len(plan['tasks']), observed=len(records), records=records,
            model_calls=0, teacher_dispatches=0, image_builds=0, image_loads=0,
            archive_concurrency=1, original_task_modifications=0)
        tmp = S / 'state.pending'
        tmp.write_text(json.dumps(value, indent=2))
        tmp.replace(S / 'state.json')

    while True:
        process = Path('/proc') / str(plan['previous_pid'])
        try:
            tick = (process / 'stat').read_text().rsplit(')', 1)[1].split()[19]
        except FileNotFoundError:
            break
        if tick != plan['previous_process_start_ticks']:
            break
        if 'archive_resident_tmax149_unlimited_r2.py' not in (process / 'cmdline').read_text():
            raise ValueError('Previous historical archiver process identity changed')
        state('WAITING_FOR_EXISTING_HISTORICAL_ARCHIVE_NATIVE_COMPLETION')
        time.sleep(20)
    previous = json.loads((R / 'checks/native-tmax-resident-archive-r1.json').read_text())
    if previous['status'] != 'FINITE_ORIGINAL_IMAGE_ARCHIVAL_TERMINAL' or previous['observed_tasks'] != previous['planned_tasks']:
        state('PREVIOUS_ARCHIVE_MISSING_TERMINAL_PROOF')
        raise ValueError('Do not start a second archive or infer completion from a missing PID')
    shared_lock = (R / 'checks/native-tmax-resident-archive-r1.lock').open('a')
    fcntl.flock(shared_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    state('RETAINING_ALREADY_ATTEMPTED_ORIGINAL_IMAGES')
    for item in plan['tasks']:
        for original in item['original_teacher_results']:
            if n.sha(Path(original['result_path'])) != original['result_sha256']:
                raise ValueError('Historical teacher Result changed')
        if n.sha(Path(item['preparation_receipt'])) != item['source_identity']['preparation_receipt_sha256']:
            raise ValueError('Original image preparation identity changed')
        try:
            proof = archive_image(item['task_id'], item['image_id'], 'tmax', item['source_identity'])
            record = dict(task_id=item['task_id'], status='ORIGINAL_HISTORICAL_IMAGE_ARCHIVED_AND_VERIFIED',
                image_id=item['image_id'], archive=proof['archive'], archive_sha256=proof['archive_sha256'])
        except Exception as error:
            record = dict(task_id=item['task_id'], status='HISTORICAL_IMAGE_RETENTION_FAILED',
                error_type=type(error).__name__, reason=str(error)[-1200:])
        records.append(record)
        state('RETAINING_ALREADY_ATTEMPTED_ORIGINAL_IMAGES')
        print(json.dumps(record), flush=True)
    state('FINITE_HISTORICAL_IMAGE_RETENTION_TERMINAL')
    n.freeze(S / 'TERMINAL.json', json.loads((S / 'state.json').read_text()))


if __name__ == '__main__':
    for key in ['DEEPSEEK_API_KEY', 'OPENAI_API_KEY', 'GH_TOKEN']:
        os.environ.pop(key, None)
    os.environ['PATH'] = str(R / 'client-bin-v2') + ':' + os.environ['PATH']
    os.environ['SSH_AUTH_SOCK'] = '/home/chenkeyi/.local/share/harbor-rsi/near-r3-20261015/auth.sock'
    main()
