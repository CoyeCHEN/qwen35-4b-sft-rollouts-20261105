"""Immutable metadata proof of actual native teachers and completion backfill."""
import collections, datetime, hashlib, json, os, subprocess
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

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
authority=next((R/'checks'/('CURRENT_DISPATCH_AUTHORITY_'+revision+'.json') for revision in ['R14','R13','R12','R11','R9','R8','R7'] if (R/'checks'/('CURRENT_DISPATCH_AUTHORITY_'+revision+'.json')).exists() and Path(json.loads((R/'checks'/('CURRENT_DISPATCH_AUTHORITY_'+revision+'.json')).read_text())['state_path']).exists()),R/'checks/CURRENT_DISPATCH_AUTHORITY_R7.json')
state_path=Path(json.loads(authority.read_text())['state_path']) if authority.exists() else R/'campaign-state.json'
state=json.loads(state_path.read_text())
probe_code="""import datetime,json
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
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
authority_doc=json.loads(authority.read_text());manifest=json.loads(Path(authority_doc['manifest']).read_text())
deployment=json.loads(Path(manifest['deployment_config']).read_text())
requests=[]
for name,admission in active.items():
    trial=S/'trials'/name;native=json.loads((trial/'config.json').read_text())
    if native['environment']['kwargs']['endpoint']!=deployment['environment']['kwargs']['endpoint']:
        raise ValueError('Actual teacher is outside the declared17 backend')
    compose,=trial.glob('remote-docker-*.compose.json')
    requests.append(dict(trial_name=name,task_id=admission['task_id'],pool=admission['pool'],
        agent_admitted_at=admission['agent_admitted_at'],native_result_present=(trial/'result.json').exists(),
        backend_endpoint=native['environment']['kwargs']['endpoint'],
        identity=compose.name.removeprefix('remote-docker-').removesuffix('.compose.json')))
node_code=r"""import json,sys,subprocess,datetime
from pathlib import Path
v=json.load(sys.stdin);d=v['deployment'];S=Path(d['ssd_root']);cli=['docker','--host','unix://'+d['socket']]
engine=subprocess.run(cli+['info','--format','{{.ID}}'],check=True,capture_output=True,text=True,timeout=20).stdout.strip()
assert engine==d['engine_id'];out=[];destination='/logs/agent/openharness-rollout/events.jsonl'
for item in v['rows']:
 row=dict(item,engine_id=engine,probe_returncode=0)
 try:
  ids=subprocess.run(cli+['ps','--filter','label=io.harbor.remote-docker.identity='+item['identity'],'--format','{{.ID}}'],check=True,capture_output=True,text=True,timeout=20).stdout.split()
  if len(ids)!=1:raise ValueError('No unique live native scope container')
  row['container_id']=ids[0]
  # Recorder is in this Task's writable layer. Use tiny C utilities for
  # file I/O, then decode on the host, outside a busy Task CPU cgroup.
  stat_reply=subprocess.run(cli+['exec',ids[0],'stat','-c','%s %Y',destination],capture_output=True,text=True,timeout=30)
  metadata=dict(recorder_exists=stat_reply.returncode==0,container_path=destination,
    storage='Owned private Engine writable layer; physical Docker root declared on17SSD')
  if stat_reply.returncode==0:
   size,modified=map(int,stat_reply.stdout.split());metadata.update(bytes=size,modified_at=datetime.datetime.fromtimestamp(modified,datetime.timezone.utc).isoformat())
   head=subprocess.run(cli+['exec',ids[0],'head','-c','1048576',destination],check=True,capture_output=True,timeout=30).stdout.splitlines()
   tail=subprocess.run(cli+['exec',ids[0],'tail','-c','1048576',destination],check=True,capture_output=True,timeout=30).stdout.splitlines()
   types=[]
   for line in [*head,*tail]:
    try:
     event=json.loads(line)
     if event.get('type') in ['call_chunk','call_payload','call_end']:types.append(event['type'])
    except ValueError:pass
   metadata.update(sampled_first_and_last_provider_event_count=len(types),sampled_first_and_last_provider_event_types=sorted(set(types)))
  row['recorder_metadata']=metadata
 except (OSError,ValueError,subprocess.SubprocessError) as error:
  row.update(probe_returncode=None,observation_error_type=type(error).__name__,observation_error=str(error)[-300:])
 out.append(row)
print(json.dumps(out))
"""
import shlex
reply=subprocess.run([*deployment['ssh'],deployment['host'],shlex.join([deployment['python17'],'-c',node_code])],input=json.dumps(dict(deployment=deployment['runtime'],rows=requests)),capture_output=True,text=True,timeout=300)
if reply.returncode:
    rows=[dict(item,probe_returncode=reply.returncode,observation_error='Host metadata sampler failed; no Task failure classification') for item in requests]
else:rows=json.loads(reply.stdout)
end_active=set()
for line in (S/'teacher-lifecycle.jsonl').open():
    item=json.loads(line)
    if item['event']=='TEACHER_ADMITTED':end_active.add(item['trial_name'])
    elif item['event']=='TEACHER_FINALIZED':end_active.discard(item['trial_name'])
unchanged_active_set=set(active)==end_active
stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
out=dict(checked_at=now(),controller_pid=state['pid'],controller_state_checked_at=state['checked_at'],
 lifecycle_snapshot_sha256=hashlib.sha256(raw).hexdigest(),lifecycle_snapshot_bytes=len(raw),
 maximum_teacher_trials=maximum,native_agent_phase_trials_at_snapshot=len(active),controller_reported_teacher_trials=state['actual_teacher_trials'],
 rows=rows,backfill_cycles=pairs,completed_backfill_cycles=len(pairs),
 delayed_cycles=[x for x in pairs if x['gap_seconds']>15],
 recent_cycles=pairs[-10:],ready_buffer=state['ready_buffer'],
 installed_or_setup_waiting=state['teacher_setup_or_gate_waiting'],
 eight_slot_intervals=intervals,ongoing_eight_slot_interval_start=at_eight,
 all_eight_current_have_provider_events=len(rows)==8 and unchanged_active_set and all(x.get('recorder_metadata',{}).get('sampled_first_and_last_provider_event_count',0)>0 and not x['native_result_present'] and not (S/'trials'/x['trial_name']/'result.json').exists() for x in rows),
 metadata_probe_max_concurrent=1,metadata_source='Tiny read-only stat/head/tail in the live Task; JSON decoding on17host outside its CPU cgroup; no Task Python imports',stable_actual_active_trial_names_through_all_probes=unchanged_active_set,source_of_current_trials='Actual lifecycle admission/finalization fold, independently of the controller state refresh',provider_sampling='Complete JSON records in first and last1MiB; large tool observations can contain no recent provider record. Historical R7 tail-only false negatives preserved.',
 observer_source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),model_calls_by_observer=0,raw_model_content_copied=0,qualified_success_claim=False)
p=R/'checks'/('actual-teacher-eight-and-backfill-r124-'+stamp+'.json')
with p.open('x') as f: json.dump(out,f,indent=2)
print(json.dumps(dict(proof=str(p),native_agent_phases=out['native_agent_phase_trials_at_snapshot'],provider_events_all_eight=out['all_eight_current_have_provider_events'],maximum=maximum,cycles=len(pairs),recent_gaps=[x['gap_seconds'] for x in pairs[-10:]],delayed=len(out['delayed_cycles']))))
