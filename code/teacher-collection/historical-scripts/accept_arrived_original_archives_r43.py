"""Admit only newly arrived exact archives into one released native prep slot."""
import datetime
import json
import os
from pathlib import Path
import shlex
import subprocess

import collection_readiness_r9 as n
from collection_attempts_r8 import attempt_counts
from collection_selection_r7 import active_rows


def main():
    prior_path = n.R / 'stream/native-exact-archive-recheck17-r34/TERMINAL.json'
    previous = json.loads(prior_path.read_text())
    if Path('/proc/' + str(previous['pid'])).exists() or previous['terminal'] != previous['planned']:
        raise ValueError('The original native preparation slot remains live')
    source = n.R / 'manifests/TMAX_READY_ORIGINAL_ARCHIVES_RECHECK_R29.json'
    old = json.loads(source.read_text())
    pending = old['pending_original_archives']
    direct_root=n.R/'stream/direct17-native-source-r17'
    direct_plan=json.loads((direct_root/'PLAN.json').read_text())
    direct_waiting={item['task_id'] for item in direct_plan['tasks'] if not (direct_root/'environment-outcomes'/(item['task_id']+'.json')).exists()}
    counts = attempt_counts()
    selected = {row['task_id']:row for row in active_rows(counts)}
    qualified = {row['task_id'] for row in map(json.loads, (n.R / 'indexes/TMAX_SUCCESS_INDEX.jsonl').open())}
    candidates = []
    dispositions = []
    for item in pending:
        ident = item['task_id']
        disposition = dict(task_id=ident, conservative_attempts=counts.get(ident, 0))
        if ident not in selected or counts.get(ident, 0) >= 2 or ident in qualified:
            dispositions.append(dict(disposition, status='SELECTION_BUDGET_OR_QUALIFIED_PRESERVED'))
            continue
        if ident in direct_waiting:
            dispositions.append(dict(disposition,status='ALREADY_ASSIGNED_FINITE_R17_PREPARATION_PRESERVED'))
            continue
        positive = []
        for root in n.readiness_roots():
            paths = [root / 'environment-outcomes' / (ident + '.json'),
                *sorted((root / 'ready-revisions' / ident).glob('*.json'))]
            for path in paths:
                if not path.exists():
                    continue
                value = json.loads(path.read_text())
                if value['status'] == 'ENV_READY':
                    value=n.normalize_ready(value,path)
                    if value['engine_id']!=n.NODE['engine_id'] or value['deployment_config_sha256']!=n.CONFIG_SHA:
                        raise ValueError('Positive readiness belongs to another deployment')
                    positive.append(str(path))
        if positive:
            dispositions.append(dict(disposition, status='CURRENT17_NATIVE_READY_PRESERVED', ready_receipts=positive))
            continue
        for key in ['original_failure', 'original_basic_receipt']:
            if n.sha(Path(item[key])) != item[key + '_sha256']:
                raise ValueError('Original frozen failure/preparation changed')
        admitted = n.prepare_identity(selected[ident])
        if admitted['image_id'] != item['image_id'] or admitted['prepared_task_toml_sha256'] != item['prepared_task_toml_sha256']:
            raise ValueError('Original prepared Task or image binding changed')
        candidates.append(item)
    code = r'''import json,sys,hashlib
from pathlib import Path
request=json.load(sys.stdin);S=Path(request['ssd_root']);R=Path(request['metadata_root']);out=[]
for item in request['tasks']:
 ident=item['task_id'];image=item['image_id'];row=dict(task_id=ident,image_id=image)
 path=S/'cold-images-from149-r1/tmax'/ident/image.split(':')[1]/'image-audit.json'
 if not path.exists():
  row['status']='ORIGINAL_ARCHIVE_NOT_YET_PRESENT';out.append(row);continue
 proof=json.loads(path.read_text());archive=Path(proof['archive'])
 if proof['image_id']!=image or not proof['all_original_manifest_config_layer_and_diffid_hashes_verified'] or not archive.is_relative_to(S):
  raise ValueError('Exact archive receipt changed')
 if not archive.is_file() or archive.stat().st_size!=proof['archive_bytes']:
  row['status']='ARCHIVE_FILE_NOT_COMPLETE';out.append(row);continue
 row.update(status='EXACT_ORIGINAL_ARCHIVE_AVAILABLE_ON17',archive_receipt=str(path),archive_receipt_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),archive=str(archive),archive_sha256=proof['archive_sha256']);out.append(row)
print(json.dumps(out))
'''
    request = dict(tasks=candidates, ssd_root=n.NODE['ssd_root'],
        metadata_root='/home/chenkeyi/workspace/RSI/runtime-evidence/' + n.R.name)
    reply = subprocess.run([*n.DEPLOYMENT['ssh'], n.DEPLOYMENT['host'],
        shlex.join([n.DEPLOYMENT['python17'], '-c', code])], input=json.dumps(request),
        capture_output=True, text=True, check=True, timeout=90)
    availability = {row['task_id']:row for row in json.loads(reply.stdout)}
    tasks = []
    for item in candidates:
        result = availability[item['task_id']]
        if result['status'] == 'EXACT_ORIGINAL_ARCHIVE_AVAILABLE_ON17':
            tasks.append(dict(item, archive_availability=result,
                conservative_attempts_before=counts.get(item['task_id'], 0)))
        dispositions.append(result)
    audit = dict(identity_policy='R9 exact archive resolver and per-image full SHA checks; historical per-Task receipts retained',direct17_already_assigned_tasks=sorted(direct_waiting),checked_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        source_plan=str(source), source_plan_sha256=n.sha(source),
        previous_native_slot=str(prior_path), previous_native_slot_sha256=n.sha(prior_path),
        pending_scope=len(pending), newly_available=len(tasks), dispositions=dispositions,
        source_sha256=n.sha(Path(__file__)), model_calls=0,
        image_identity_changes=0, image_rebuilds=0, original_task_or_test_changes=0)
    n.freeze(n.R / 'checks/arrived-original-archives-readonly-audit-r43.json', audit)
    if not tasks:
        print(json.dumps(dict(status='NO_NEW_EXACT_ARCHIVES_AVAILABLE', audit=audit)))
        return
    plan_path = n.R / 'manifests/TMAX_READY_ORIGINAL_ARCHIVES_RECHECK_R43.json'
    n.freeze(plan_path, dict(tasks=tasks, runtime_engine_id=n.NODE['engine_id'],
        deployment_config_sha256=n.CONFIG_SHA,
        availability_audit=str(n.R / 'checks/arrived-original-archives-readonly-audit-r43.json'),
        availability_audit_sha256=n.sha(n.R / 'checks/arrived-original-archives-readonly-audit-r43.json')))
    import recheck_exact_original_archives17_r43 as worker
    frozen = worker.plan()
    for item in tasks:
        admitted = n.prepare_identity(selected[item['task_id']])
        for kind in ['install', 'nop']:
            cfg = n.native_config(admitted, kind)
            if cfg.environment.kwargs['remote_socket_path'] != n.NODE['socket']:
                raise ValueError('Native precheck socket changed')
    n.freeze(n.R / 'checks/exact-original-archive-recheck-r43-offline-acceptance.json', dict(
        passed=True, source_sha256=frozen['source_sha256'], source_plan_sha256=n.sha(plan_path),
        tasks=len(tasks), model_calls=0, native_concurrency=1, original_task_changes=0))
    scope = n.R / 'stream/native-exact-archive-recheck17-r43'
    scope.mkdir(exist_ok=True)
    if (scope / 'PLAN.json').exists():
        raise FileExistsError('Observe the already launched native recheck')
    command = shlex.join([str(Path(os.sys.executable)), str(n.R / 'scripts/recheck_exact_original_archives17_r43.py')])
    command += ' > ' + shlex.quote(str(scope / 'worker.log')) + ' 2>&1'
    subprocess.run(['tmux', '-L', 'cf-tmax-teacher-20261029', 'new-window', '-d',
        '-n', 'exact-archive-recheck17-r43', command], check=True)
    print(json.dumps(dict(launched=True, tasks=len(tasks), scope=str(scope), model_calls=0,
        dispositions={status:sum(x['status']==status for x in dispositions) for status in {x['status'] for x in dispositions}})))


if __name__ == '__main__':
    os.environ['PATH'] = str(n.R / 'client-bin-v2') + ':' + os.environ['PATH']
    main()
