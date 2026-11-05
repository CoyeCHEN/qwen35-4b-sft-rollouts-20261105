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
    elif kind=='TEACHER_AGENT_ENDED':
        active.pop(name,None); pending.append(event)
    elif kind=='TEACHER_FINALIZED':
        if name not in active:continue
        active.pop(name,None); pending.append(event)
    else: continue
    maximum=max(maximum,len(active))
    if len(active)==8 and at_eight is None: at_eight=timestamp
    if len(active)<8 and at_eight:
        intervals.append(dict(start=at_eight,end=timestamp,seconds=(dt(timestamp)-dt(at_eight)).total_seconds())); at_eight=None
assert maximum<=8
authority=next((R/'checks'/('CURRENT_DISPATCH_AUTHORITY_'+revision+'.json') for revision in ['R17','R16','R15','R14','R13','R12','R11','R9','R8','R7'] if (R/'checks'/('CURRENT_DISPATCH_AUTHORITY_'+revision+'.json')).exists() and Path(json.loads((R/'checks'/('CURRENT_DISPATCH_AUTHORITY_'+revision+'.json')).read_text())['state_path']).exists()),R/'checks/CURRENT_DISPATCH_AUTHORITY_R7.json')
state_path=Path(json.loads(authority.read_text())['state_path']) if authority.exists() else R/'campaign-state.json'
state=json.loads(state_path.read_text())
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
import tarfile

def archived_file(container,path,limit):
 process=subprocess.Popen(cli+['cp',container+':'+path,'-'],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
 result=None;failure=None
 try:
  with tarfile.open(fileobj=process.stdout,mode='r|') as archive:
   member=next(iter(archive))
   if not member.isfile():raise ValueError('Recorder metadata path is not a regular file')
   data=archive.extractfile(member).read(min(limit,member.size))
   result=dict(exists=True,bytes=member.size,mtime=member.mtime,data=data,prefix_only=member.size>limit)
 except (OSError,ValueError,tarfile.TarError,StopIteration) as error:failure=type(error).__name__
 finally:
  process.stdout.close()
  try:process.wait(timeout=2)
  except subprocess.TimeoutExpired:
   process.terminate();process.wait(timeout=3)
  stderr=process.stderr.read(8192).decode(errors='replace');process.stderr.close()
 if result is not None:return result
 if any(marker in stderr.lower() for marker in ['could not find the file','no such file or directory']):return dict(exists=False)
 raise ValueError('Read-only Docker filesystem archive unavailable: '+str(failure))

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
  record=archived_file(ids[0],destination,1048576)
  metadata=dict(recorder_exists=record['exists'],container_path=destination,
    storage='Read-only Docker filesystem archive in the owned private17 Engine; no Task executable or new helper container')
  if record['exists']:
   metadata.update(bytes=record['bytes'],modified_at=datetime.datetime.fromtimestamp(record['mtime'],datetime.timezone.utc).isoformat())
   types=[]
   for line in record['data'].splitlines():
    try:
     event=json.loads(line)
     if event.get('type') in ['call_chunk','call_payload','call_end']:types.append(event['type'])
    except ValueError:pass
   metadata.update(sampled_provider_event_count=len(types),sampled_provider_event_types=sorted(set(types)),bounded_prefix_bytes=1048576)
  row['recorder_metadata']=metadata
  top=subprocess.run(cli+['top',ids[0],'-eo','pid,stat,args'],check=True,capture_output=True,text=True,timeout=15).stdout
  import shlex
  processes=[]
  for line in top.splitlines():
   fields=line.split(None,2)
   if len(fields)!=3 or not fields[0].isdigit():continue
   try:argv=shlex.split(fields[2])
   except ValueError:continue
   if argv[:1]==['{open-harness}']:argv=argv[1:]
   direct=bool(argv and argv[0].endswith('/bin/open-harness'))
   interpreted=bool(len(argv)>1 and Path(argv[0]).name.startswith('python') and argv[1].endswith('/bin/open-harness'))
   if direct or interpreted:processes.append(dict(pid=int(fields[0]),state=fields[1],live=fields[1][0] not in ['Z','T','t']))
  marker=archived_file(ids[0],'/logs/agent/open-harness.complete.json',65536)
  marker_present=marker['exists']
  marker_time=float(marker['mtime']) if marker_present else None
  node_probe_time=datetime.datetime.now(datetime.timezone.utc).timestamp()
  row['agent_phase_metadata']=dict(cli_processes=processes,completion_marker_present=marker_present,
    completion_marker_mtime_epoch_node17=marker_time,probe_epoch_node17=node_probe_time,
    completed_cli_wait_seconds=max(0,node_probe_time-marker_time) if marker_time is not None and not any(p['live'] for p in processes) else None,
    vacancy_clock_basis='Same17clock: completion-marker mtime to host probe time; no cross-node timestamp subtraction',
    agent_execution_active=any(p['live'] for p in processes) and not marker_present,
    source='Actual native CLI process state and native completion marker; no raw process arguments retained')
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
    elif item['event'] in ['TEACHER_AGENT_ENDED','TEACHER_FINALIZED']:end_active.discard(item['trial_name'])
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
 all_eight_current_have_provider_events=len(rows)==8 and unchanged_active_set and all(x.get('recorder_metadata',{}).get('sampled_provider_event_count',0)>0 and x.get('agent_phase_metadata',{}).get('agent_execution_active') is True and not x['native_result_present'] and not (S/'trials'/x['trial_name']/'result.json').exists() for x in rows),
 current_agent_execution_slots=sum(x.get('agent_phase_metadata',{}).get('agent_execution_active') is True and x.get('recorder_metadata',{}).get('sampled_provider_event_count',0)>0 for x in rows) if unchanged_active_set else None,live_cli_and_absent_completion_marker_required=True,metadata_probe_max_concurrent=1,metadata_source='Bounded read-only Docker filesystem archives and Engine process metadata; no Task executable, libc, new container or model call',stable_actual_active_trial_names_through_all_probes=unchanged_active_set,source_of_current_trials='Actual lifecycle admission/finalization fold, independently of the controller state refresh',provider_sampling='Complete JSON records from at most first1MiB via native Docker filesystem archive; partial final JSON ignored. Historical exec/head/tail probes preserved. Provider history alone does not prove live execution.',
 observer_source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),model_calls_by_observer=0,raw_model_content_copied=0,qualified_success_claim=False,closed_cli_waits=[dict(trial_name=x['trial_name'],task_id=x['task_id'],seconds=x.get('agent_phase_metadata',{}).get('completed_cli_wait_seconds')) for x in rows if x.get('agent_phase_metadata',{}).get('completion_marker_present') is True])
p=R/'checks'/('actual-active-agent-eight-and-backfill-r200-'+stamp+'.json')
with p.open('x') as f: json.dump(out,f,indent=2)
print(json.dumps(dict(proof=str(p),native_agent_phases=out['native_agent_phase_trials_at_snapshot'],provider_events_all_eight=out['all_eight_current_have_provider_events'],live_agent_slots=out['current_agent_execution_slots'],maximum=maximum,cycles=len(pairs),recent_gaps=[x['gap_seconds'] for x in pairs[-10:]],delayed=len(out['delayed_cycles']))))
