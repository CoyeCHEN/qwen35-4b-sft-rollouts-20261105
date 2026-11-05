"""Backpressure the existing readiness interface at its original100GiB guard.

Only unadmitted preparation markers change. Exact old bytes remain available
by SHA. No original Task, native Trial/Result, active pipeline or model changes.
"""
from pathlib import Path
import datetime
import hashlib
import json
import shutil
from run_collection_stream_r3 import attempt_counts

R = Path('/home/chenkeyi/.local/share/harbor-rsi/qwen35-new-cf500-tmax500-20261029')
S = R / 'stream/collection-r3'
PASSED = {'IMAGE_IDENTITY_AND_BASIC_SETUP_PASSED', 'IMAGE_AND_ORIGINAL_INITIAL_STATE_PASSED_FINAL_VERIFIER_PENDING'}


def admitted():
    ids = {json.loads(p.read_text())['task_id'] for p in R.glob('stream/*/dispatches/*/dispatch.json')}
    ids.update(attempt_counts())
    ids.update(p.stem for p in (S / 'environment-outcomes').glob('*.json'))
    ids.update(json.loads((R / 'campaign-state.json').read_text())['active_task_pipelines'])
    return ids


def main():
    output = R / 'checks/admission-capacity-hold-r1.json'
    if output.exists():
        raise FileExistsError('Observe the original capacity-backpressure operation')
    before = shutil.disk_usage(R).free
    if before >= 100 * 1024**3:
        raise ValueError('Original preparation capacity guard is not breached')
    selected = [row for name in ['CALIBFORGE_500_TASKS.jsonl', 'TMAX_RUNTIME_CANDIDATES_V2.jsonl']
        for row in map(json.loads, (R / 'manifests' / name).open())]
    known = admitted(); records = []
    originals = R / 'checks/admission-capacity-hold-r1-originals'
    for row in selected:
        ident = row['task_id']
        if ident in known:
            continue
        if row['pool'] == 'calibforge' and (R / 'prepared-tasks/calibforge-pinned-stream-r1' / ident).exists():
            continue
        names = ['cf-environments-oci-r5'] if row['pool'] == 'calibforge' else [
            'tmax-environments-public-input-review-r6', 'tmax-environments-collision-recheck-r5', 'tmax-environments-runtime-r4']
        for name in names:
            path = R / 'checks' / name / (ident + '.json')
            if not path.exists():
                continue
            raw = path.read_bytes(); value = json.loads(raw)
            if value['status'] not in PASSED:
                continue
            live = json.loads((R / 'campaign-state.json').read_text())
            if ident in live['active_task_pipelines']:
                continue
            digest = hashlib.sha256(raw).hexdigest()
            archive = originals / name / (ident + '.json'); archive.parent.mkdir(parents=True, exist_ok=True)
            with archive.open('xb') as stream:
                stream.write(raw)
            held = dict(value, status='IMAGE_BASIC_PASSED_CAPACITY_HOLD', original_status=value['status'],
                original_evidence=str(archive), original_evidence_sha256=digest,
                capacity_hold_reason='Original100GiB preparation guard breached; no new native pipeline until exact-image cold-storage handoff/capacity recovery',
                capacity_hold_at=datetime.datetime.now(datetime.timezone.utc).isoformat())
            temporary = path.with_suffix('.capacity-tmp'); temporary.write_text(json.dumps(held, indent=2)); temporary.replace(path)
            # Never hold a pipeline that was concurrently admitted by the old queue.
            active = json.loads((R / 'campaign-state.json').read_text())['active_task_pipelines']
            if ident in active:
                path.write_bytes(raw); action = 'ORIGINAL_MARKER_RESTORED_FOR_CONCURRENT_ADMISSION'
            else:
                action = 'UNADMITTED_PREPARATION_CAPACITY_HELD'
            records.append(dict(task_id=ident, pool=row['pool'], marker=str(path),
                original_evidence=str(archive), original_evidence_sha256=digest, action=action))
    result = dict(checked_at=datetime.datetime.now(datetime.timezone.utc).isoformat(), records=records,
        original_guard_bytes=100 * 1024**3, observed_free_bytes=before,
        original_tasks_or_tests_modified=0, native_trials_results_or_recorders_modified=0,
        active_pipelines_cancelled=0, model_calls=0, goal_paused=False)
    output.write_text(json.dumps(result, indent=2))
    print(json.dumps(dict(held_markers=len(records), original_evidence_bytes_preserved=True, active_pipelines_cancelled=0, model_calls=0)))


if __name__ == '__main__':
    main()
