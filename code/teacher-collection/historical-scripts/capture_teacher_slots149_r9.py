"""Immutable metadata proof of actual native teachers and completion backfill."""
import collections, datetime, hashlib, json, os, subprocess
from pathlib import Path

R=Path('/home/chenkeyi/.local/share/harbor-rsi/qwen35-new-cf500-tmax500-20261029')
S=R/'stream/collection-r4'
os.environ['PATH']=str(R/'client-bin-v2')+':'+os.environ['PATH']
os.environ['SSH_AUTH_SOCK']='/home/chenkeyi/.local/share/harbor-rsi/near-r3-20261015/auth.sock'
def now(): return datetime.datetime.now(datetime.timezone.utc).isoformat()
def dt(s): return datetime.datetime.fromisoformat(s)
def run(args): return subprocess.run(args,capture_output=True,text=True,timeout=25)
raw=(S/'teacher-lifecycle.jsonl').read_bytes()
events=[json.loads(x) for x in raw.splitlines() if x.strip()]
active={}; pending=collections.deque(); pairs=[]; maximum=0; intervals=[]; at_eight=None
for event in events:
    kind=event['event']; timestamp=event['observed_at']; name=event['trial_name']
    if kind=='TEACHER_ADMITTED':
        active[name]=event
        if pending:
            end=pending.popleft()
            pairs.append(dict(finished_trial=end['trial_name'],finished_at=end['observed_at'],replacement_trial=name,replacement_at=timestamp,gap_seconds=(dt(timestamp)-dt(end['observed_at'])).total_seconds()))
    elif kind=='TEACHER_FINALIZED':
        active.pop(name,None); pending.append(event)
    else: continue
    maximum=max(maximum,len(active))
    if len(active)==8 and at_eight is None: at_eight=timestamp
    if len(active)<8 and at_eight:
        intervals.append(dict(start=at_eight,end=timestamp,seconds=(dt(timestamp)-dt(at_eight)).total_seconds())); at_eight=None
assert maximum<=8
authority=next((R/'checks'/('CURRENT_DISPATCH_AUTHORITY_'+revision+'.json') for revision in ['R8','R7'] if (R/'checks'/('CURRENT_DISPATCH_AUTHORITY_'+revision+'.json')).exists() and Path(json.loads((R/'checks'/('CURRENT_DISPATCH_AUTHORITY_'+revision+'.json')).read_text())['state_path']).exists()),R/'checks/CURRENT_DISPATCH_AUTHORITY_R7.json')
state_path=Path(json.loads(authority.read_text())['state_path']) if authority.exists() else R/'campaign-state.json'
state=json.loads(state_path.read_text())
probe_code="""import datetime,json
from pathlib import Path
p=Path('/logs/agent/openharness-rollout/events.jsonl')
out={'recorder_exists':p.exists()}
if p.exists():
 s=p.stat();out.update(bytes=s.st_size,modified_at=datetime.datetime.fromtimestamp(s.st_mtime,datetime.timezone.utc).isoformat())
 with p.open('rb') as f:
  head=f.read(1048576).splitlines()
  f.seek(max(0,s.st_size-1048576));tail=f.read(1048576).splitlines()
 events=[]
 for line in [*head,*tail]:
  try: events.append(json.loads(line))
  except ValueError: pass
 out['sampled_first_and_last_provider_event_count']=sum(x.get('type') in ['call_chunk','call_payload','call_end'] for x in events)
 out['sampled_first_and_last_provider_event_types']=sorted({x.get('type') for x in events if x.get('type') in ['call_chunk','call_payload','call_end']})
print(json.dumps(out))
"""
rows=[]
engines={}
for name,admission in active.items():
    item={key:admission[key] for key in ['task_id','pool','agent_admitted_at']}
    trial=S/'trials'/name; compose=list(trial.glob('remote-docker-*.compose.json'))
    row=dict(trial_name=name,**item,native_result_present=(trial/'result.json').exists())
    config=json.loads((trial/'config.json').read_text());endpoint=config['environment']['kwargs']['endpoint']
    if endpoint=='ssh://chenkeyi@127.0.0.1:5102':client=['docker'];expected='c6e16cdf-e878-4cc5-84c8-78a56c54b5c5'
    elif endpoint=='ssh://chenkeyi@180.163.192.17:22':client=['docker','--host',endpoint];expected='59c8ba22-0aa4-4aed-bc43-4e1b5989fa22'
    else:raise ValueError('Unregistered teacher backend: '+endpoint)
    if endpoint not in engines:
        reply=run([*client,'info','--format','{{.ID}}']);assert reply.returncode==0 and reply.stdout.strip()==expected
        engines[endpoint]=expected
    row.update(backend_endpoint=endpoint,engine_id=engines[endpoint])
    if len(compose)==1:
        identity=compose[0].name.removeprefix('remote-docker-').removesuffix('.compose.json')
        query=run([*client,'ps','--filter','label=io.harbor.remote-docker.identity='+identity,'--format','{{.ID}}'])
        names=query.stdout.split()
        if len(names)==1:
            row['container_id']=names[0]
            reply=run([*client,'exec',names[0],'/harbor/agent-runtime/harbor-open-harness-venv/bin/python','-c',probe_code])
            row['probe_returncode']=reply.returncode
            if reply.returncode==0: row['recorder_metadata']=json.loads(reply.stdout)
            else: row['probe_error']=reply.stderr[-300:]
    rows.append(row)
end_active=set()
for line in (S/'teacher-lifecycle.jsonl').open():
    item=json.loads(line)
    if item['event']=='TEACHER_ADMITTED':end_active.add(item['trial_name'])
    elif item['event']=='TEACHER_FINALIZED':end_active.discard(item['trial_name'])
unchanged_active_set=set(active)==end_active
stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
out=dict(checked_at=now(),controller_pid=state['pid'],controller_state_checked_at=state['checked_at'],
 lifecycle_snapshot_sha256=hashlib.sha256(raw).hexdigest(),lifecycle_snapshot_bytes=len(raw),
 maximum_teacher_trials=maximum,actual_teacher_trials_at_snapshot=len(active),controller_reported_teacher_trials=state['actual_teacher_trials'],
 rows=rows,backfill_cycles=pairs,completed_backfill_cycles=len(pairs),
 delayed_cycles=[x for x in pairs if x['gap_seconds']>15],
 recent_cycles=pairs[-10:],ready_buffer=state['ready_buffer'],
 installed_or_setup_waiting=state['teacher_setup_or_gate_waiting'],
 eight_slot_intervals=intervals,ongoing_eight_slot_interval_start=at_eight,
 all_eight_current_have_provider_events=len(rows)==8 and unchanged_active_set and all(x.get('recorder_metadata',{}).get('sampled_first_and_last_provider_event_count',0)>0 and not x['native_result_present'] for x in rows),
 stable_actual_active_trial_names_through_all_probes=unchanged_active_set,source_of_current_trials='Actual lifecycle admission/finalization fold, independently of the controller state refresh',provider_sampling='Complete JSON records in first and last1MiB; large tool observations can contain no recent provider record. Historical R7 tail-only false negatives preserved.',
 observer_source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),model_calls_by_observer=0,raw_model_content_copied=0,qualified_success_claim=False)
p=R/'checks'/('actual-teacher-eight-and-backfill-r9-'+stamp+'.json')
with p.open('x') as f: json.dump(out,f,indent=2)
print(json.dumps(dict(proof=str(p),actual=out['actual_teacher_trials_at_snapshot'],provider_events_all_eight=out['all_eight_current_have_provider_events'],maximum=maximum,cycles=len(pairs),recent_gaps=[x['gap_seconds'] for x in pairs[-10:]],delayed=len(out['delayed_cycles']))))
