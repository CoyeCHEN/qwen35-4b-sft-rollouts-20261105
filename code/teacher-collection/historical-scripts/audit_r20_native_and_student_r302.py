"""Read-only first new-deployment teacher closure, archive and student evidence."""
import datetime
import hashlib
import json
from pathlib import Path

R = Path('/home/chenkeyi/.local/share/harbor-rsi/qwen35-new-cf500-tmax500-20261029')
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    authority_path = R / 'checks/CURRENT_DISPATCH_AUTHORITY_R20.json'
    authority = json.loads(authority_path.read_text())
    campaign_path = Path(authority['manifest'])
    if sha(campaign_path) != authority['manifest_sha256']:
        raise ValueError('Current Campaign identity differs')
    campaign = json.loads(campaign_path.read_text())
    sources = {}
    index_hashes = {}
    for pool in ['CALIBFORGE', 'TMAX']:
        for name in ['SUCCESS_INDEX', 'FAILURE_OR_PENDING_INDEX']:
            path = R / 'indexes' / (pool + '_' + name + '.jsonl')
            raw = path.read_bytes(); index_hashes[str(path)] = hashlib.sha256(raw).hexdigest()
            for line in raw.splitlines():
                record = json.loads(line)
                sources[record['trial_id']] = record
    names = [json.loads(line)['trial_name'] for line in (R / 'stream/collection-r4/teacher-lifecycle.jsonl').open() if json.loads(line)['event'] == 'TEACHER_ADMITTED' and json.loads(line).get('controller_revision') == 'r20']
    rows = []
    for name in names:
        trial = R / 'stream/collection-r4/trials' / name
        path = trial / 'result.json'
        if not path.exists():
            continue
        value = json.loads(path.read_text())
        record = sources.get(value['id'])
        if record is not None and record['result_sha256'] != sha(path):
            raise ValueError('Indexed raw Result differs')
        archive = campaign_path.parent / 'ssd-trial-archives' / (name + '.json')
        archived = json.loads(archive.read_text()) if archive.exists() else None
        if archived and archived['result_sha256'] != sha(path):
            raise ValueError('Native SSD archive Result differs')
        rows.append(dict(task_id=value['task_name'], trial_name=name, trial_id=value['id'], result=str(path), result_sha256=sha(path), raw_reward=(value.get('verifier_result') or {}).get('rewards'), agent_execution=value.get('agent_execution'), verifier=value.get('verifier'), exception=(value.get('exception_info') or {}).get('exception_type'), infrastructure_errors=value.get('infrastructure_errors'), archive=str(archive) if archived else None, archive_sha256=sha(archive) if archived else None, qualified_success=record['qualified_success'] if record else False, is_primary_trajectory=record.get('is_primary_trajectory',False) if record else False, classification=record['classification'] if record else 'TERMINAL_NATIVE_RESULT_INDEX_PENDING', recorder_contract=record.get('teacher_contract_status') if record else None, cli_normal_closure=record.get('cli_normal_closure') if record else None, student_proof=record.get('student_proof') if record else None))
    out = dict(checked_at=datetime.datetime.now(datetime.timezone.utc).isoformat(), authority_sha256=sha(authority_path), campaign_sha256=sha(campaign_path), controller_runtime=campaign['controller_runtime'], new_deployment_admissions=len(names), terminal_new_deployment_trials=len(rows), qualified_new_deployment_tasks=len({x['task_id'] for x in rows if x['qualified_success']}), index_snapshot_sha256=index_hashes, rows=rows, raw_reward_one_is_not_qualified_success=True, model_calls_by_observer=0, index_mutations=0, training_started=False, source_sha256=sha(Path(__file__)))
    stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    target=R / 'checks' / ('r20-native-student-joint-r302-' + stamp + '.json')
    with target.open('x') as stream:
        json.dump(out,stream,indent=2)
    print(json.dumps(dict(proof=str(target), admissions=len(names), terminal=len(rows), qualified=out['qualified_new_deployment_tasks'], classifications=[dict(task_id=x['task_id'],classification=x['classification'],archive=x['archive'] is not None) for x in rows])))


if __name__ == '__main__':
    main()
