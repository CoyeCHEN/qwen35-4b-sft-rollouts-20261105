"""Read-only attribution of recent Teacher vacancies to native setup/gate phases."""
from collections import deque
import datetime
import hashlib
import json
from pathlib import Path

R=Path('/home/chenkeyi/.local/share/harbor-rsi/qwen35-new-cf500-tmax500-20261029')
S=R/'stream/collection-r4'
raw=(S/'teacher-lifecycle.jsonl').read_bytes()
events=[json.loads(line) for line in raw.splitlines()]
terminal_at={}
for path in (S/'trials').glob('*/result.json'):
    item=json.loads(path.read_text())
    if item.get('finished_at'):terminal_at[path.parent.name]=datetime.datetime.fromisoformat(item['finished_at'].replace('Z','+00:00'))
ready={};active={};pending=deque();cycles=[]
for event in events:
    kind=event['event'];name=event['trial_name'];at=event['observed_at']
    moment=datetime.datetime.fromisoformat(at)
    for ended in list(ready):
        if ended in terminal_at and terminal_at[ended]<=moment:ready.pop(ended)
    if kind=='SETUP_READY_WAITING_FOR_TEACHER_SLOT':ready[name]=at
    elif kind=='TEACHER_ADMITTED':
        before=dict(ready);setup_at=ready.pop(name,None);active[name]=at
        if pending:
            end=pending.popleft()
            duration=(datetime.datetime.fromisoformat(at)-datetime.datetime.fromisoformat(end['observed_at'])).total_seconds()
            cycles.append(dict(end_trial=end['trial_name'],end_at=end['observed_at'],new_trial=name,new_at=at,gap_seconds=duration,
                installed_ready_at_vacancy=end['ready'],installed_ready_before_admission=before,
                new_trial_install_ready_at=setup_at,
                new_trial_native_gate_wait_seconds=(datetime.datetime.fromisoformat(at)-datetime.datetime.fromisoformat(setup_at)).total_seconds() if setup_at else None))
    elif kind in ['TEACHER_AGENT_ENDED','TEACHER_FINALIZED'] and name in active:
        active.pop(name);pending.append(dict(event,ready=dict(ready)))
ready={name:at for name,at in ready.items() if name not in terminal_at}
state=json.loads((S/'deployment-r16/state.json').read_text())
staged=[]
for path in (S/'staging-dispatches').glob('*/setup.json'):
    value=json.loads(path.read_text());trial=S/'trials'/value['trial_name']
    if (trial/'result.json').exists() or value['trial_name'] in active:continue
    lifecycle=list(trial.glob('remote-docker-*.jsonl'))
    last={}
    if lifecycle:
        for line in lifecycle[0].read_text().splitlines():
            try:
                item=json.loads(line)
                if item['action'] in ['started','exec_completed','operation_interrupted']:last={k:item[k] for k in ['action','time','duration_ms','exit_code','error_type'] if k in item}
            except ValueError:pass
    staged.append(dict(task_id=value['task_id'],trial_name=value['trial_name'],native_setup_ready=value['trial_name'] in ready,
        staged_config_mtime_epoch_149=path.stat().st_mtime,last_native_operation=last))
value=dict(checked_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    lifecycle_sha256=hashlib.sha256(raw).hexdigest(),native_teacher_permits=len(active),installed_waiting_for_teacher_slot=ready,
    current_not_admitted_native_stages=staged,last_cycles=cycles[-30:],
    last30_long_gap_without_installed_ready=sum(x['gap_seconds']>15 and not x['installed_ready_at_vacancy'] for x in cycles[-30:]),
    last30_long_gap_with_installed_ready=sum(x['gap_seconds']>15 and bool(x['installed_ready_at_vacancy']) for x in cycles[-30:]),
    image_ready_buffer=state['ready_buffer'],hot_setup_buffer=4,native_lifecycle_cap=24,
    actual_cli_concurrency_is_separately_measured=True,model_calls=0)
stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
path=R/'checks'/('native-setup-capacity-r196-'+stamp+'.json')
with path.open('x') as stream:json.dump(value,stream,indent=2)
print(json.dumps(dict(proof=str(path),native_permits=len(active),installed_waiting=len(ready),unadmitted_stages=len(staged),
    long_gap_no_ready=value['last30_long_gap_without_installed_ready'],long_gap_with_ready=value['last30_long_gap_with_installed_ready'],
    recent=[dict(gap_seconds=x['gap_seconds'],installed_at_vacancy=len(x['installed_ready_at_vacancy']),gate_wait=x['new_trial_native_gate_wait_seconds']) for x in cycles[-10:]])))
