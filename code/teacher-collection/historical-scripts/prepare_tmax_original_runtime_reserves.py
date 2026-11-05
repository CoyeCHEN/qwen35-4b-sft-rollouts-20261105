"""Prepare preregistered same-stratum reserves for untried original setup failures.

The active500-candidate manifest and all attempted tasks remain unchanged. This
writes replacement proposals; final manifest publication is a separate gate.
"""
from collections import defaultdict
import hashlib,json,os,subprocess,sys,zipfile
from pathlib import Path
import prepare_tmax_sources as preparation

R=preparation.ROOT
SLOTS=['task_000176_2b846a1b','task_000552_d7cc1243','task_000886_9c1067c9']
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def attempts():
 out=set()
 for p in (R/'jobs').glob('*/config.json'):
  cfg=json.loads(p.read_text())
  if cfg.get('install_only') or not any(a.get('name')=='open-harness' for a in cfg.get('agents',[])):continue
  out.update(Path(t['path']).name for t in cfg['tasks'])
 return out

def main():
 manifest=R/'manifests/TMAX_RUNTIME_CANDIDATES_V2.jsonl';selected=list(map(json.loads,manifest.open()))
 assert len(selected)==500 and not attempts().intersection(SLOTS)
 used={x['task_id'] for x in selected}
 # Every prior source/runtime candidate retains its identity even if not adopted.
 for p in (R/'manifests').glob('TMAX*REPLACEMENT*.jsonl'):
  for line in p.open():
   x=json.loads(line)
   for key in ['initial_task_id','task_id','candidate_task_id','replaced_task_id']:
    if x.get(key):used.add(x[key])
 used.update(x['task_id'] for x in map(json.loads,(R/'manifests/TMAX_500_TASKS.jsonl').open()))
 reserves=defaultdict(list)
 for row in map(json.loads,(R/'manifests/TMAX_RESERVES.jsonl').open()):
  if not row['exclusion_reasons']:reserves[tuple(row['stratum'])].append(row)
 for values in reserves.values():values.sort(key=lambda x:x['reserve_rank'])
 plan_path=R/'manifests/TMAX_ORIGINAL_RUNTIME_RESERVE_PLAN_R3.json'
 if plan_path.exists():raise FileExistsError('Reserve pass already registered; inspect exact prior state')
 failures={t:R/'checks/tmax-environments-runtime-r4'/(t+'.json') for t in SLOTS}
 plan=dict(source_candidate_manifest_sha256=sha(manifest),slots=[dict(task_id=t,failure_receipt=str(p),failure_sha256=sha(p)) for t,p in failures.items()],
  selection='Frozen exact-stratum reserve rank; no teacher outcomes used',model_calls=0,teacher_attempts=0)
 plan_path.write_text(json.dumps(plan,indent=2))
 evidence=R/'checks/tmax-original-runtime-reserves-r3';evidence.mkdir(exist_ok=False)
 ledger=R/'manifests/TMAX_ORIGINAL_RUNTIME_REPLACEMENT_LEDGER_R3.jsonl';ready=[]
 with zipfile.ZipFile(R/'sources/tmax/tasks.zip') as archive,ledger.open('x') as journal:
  members=defaultdict(list)
  for m in archive.infolist():members[m.filename.split('/')[0]].append(m)
  for old_id in SLOTS:
   old=next(x for x in selected if x['task_id']==old_id);replacement=None
   for candidate in reserves[tuple(old['stratum'])]:
    ident=candidate['task_id']
    if ident in used:continue
    used.add(ident)
    if old_id in attempts():raise ValueError('Attempted task can never be replaced')
    event=dict(replaced_task_id=old_id,initial_task_id=old.get('initial_task_id',old_id),candidate_task_id=ident,
      stratum=old['stratum'],reserve_rank=candidate['reserve_rank'],split=candidate['split'],family_id=candidate['family_id'],
      original_failure_sha256=sha(failures[old_id]),model_attempts_before_replacement=0)
    try:
     source=preparation.materialize(archive,ident,members[ident])
     if preparation.adapter.digest(source/'task.json')!=candidate['task_json_sha256']:raise ValueError('Preregistered source changed')
     converted=preparation.adapter.convert_task(source,R/'tasks/tmax',
      native_converter=R/'scripts/upstream-convert-to-harbor.py',intricate_base_definition=R/'scripts/base_intricate.def')
     row=dict(candidate,initial_task_id=old.get('initial_task_id',old_id),runtime_replaced_task_id=old_id,
      task_path=str(R/'tasks/tmax'/ident),source_status='SOURCE_ACCEPTED_BUILD_AND_VERIFIER_PENDING')
     one=evidence/(ident+'.candidate.jsonl')
     with one.open('x') as stream:stream.write(json.dumps(row)+'\n')
     event.update(source_conversion=converted,candidate_manifest_sha256=sha(one))
     result=subprocess.run([sys.executable,str(R/'scripts/prepare_tmax_images_v2.py'),'--task-id',ident,
       '--startup-recheck','--manifest',str(one),'--evidence-tag','preregistered-reserve-r3'],check=False)
     p=R/'checks/tmax-environments-preregistered-reserve-r3'/(ident+'.json')
     check=json.loads(p.read_text());event.update(preparation_returncode=result.returncode,preparation_receipt=str(p),preparation_receipt_sha256=sha(p))
     if check['status']=='IMAGE_AND_ORIGINAL_INITIAL_STATE_PASSED_FINAL_VERIFIER_PENDING':
      replacement=dict(row,prepared_task_path=check['prepared_task_path'],prepared_task_toml_sha256=check['prepared_task_toml_sha256'])
      event['status']='RESERVE_ORIGINAL_INITIAL_STATE_PASSED_FINAL_VERIFIER_PENDING'
     else:
      event['status']='RESERVE_ENVIRONMENT_NOT_ACCEPTED';event['reason']=check.get('error') or check.get('initial_state_stdout','')[-1500:]
      # A bare directory-name guard is not evidence that published input is invalid.
      if check['status']=='ORIGINAL_INITIAL_STATE_TEST_FAILED' and not check.get('initial_state_stderr') and 'test session starts' not in check.get('initial_state_stdout','') and 'passed' not in check.get('initial_state_stdout','') and 'failed' not in check.get('initial_state_stdout',''):
       event['status']='PUBLIC_INPUT_BOUNDARY_REVIEW_PENDING'
    except preparation.adapter.TaskPreparationError as error:
     event.update(status='RESERVE_SOURCE_NOT_ACCEPTED',reason=str(error))
    except (OSError,ValueError,RuntimeError,subprocess.SubprocessError) as error:
     event.update(status='RESERVE_PREPARATION_ERROR',error_type=type(error).__name__,reason=str(error)[:600])
    journal.write(json.dumps(event)+'\n');journal.flush();print(json.dumps({k:event.get(k) for k in ['replaced_task_id','candidate_task_id','status','reason']}),flush=True)
    if replacement is not None:ready.append(replacement);break
    if event['status']=='PUBLIC_INPUT_BOUNDARY_REVIEW_PENDING':break
   if replacement is None:print(json.dumps(dict(slot=old_id,status='SAME_STRATUM_REPLACEMENT_NOT_READY')),flush=True)
 path=R/'manifests/TMAX_RUNTIME_REPLACEMENTS_READY_R3.jsonl'
 with path.open('x') as stream:
  for row in ready:stream.write(json.dumps(row)+'\n')
 report=dict(status='REPLACEMENT_PROPOSALS_PREPARED_FINAL_VERIFIER_AND_MANIFEST_FREEZE_PENDING',planned_slots=3,ready_slots=len(ready),
  model_calls=0,teacher_attempts=0,active_candidate_manifest_unchanged=sha(manifest)==plan['source_candidate_manifest_sha256'],ledger_sha256=sha(ledger),ready_rows_sha256=sha(path))
 (R/'checks/tmax-original-runtime-replacements-r3.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))


if __name__=='__main__':
 os.environ['DOCKER_HOST']='ssh://chenkeyi@127.0.0.1:5102';os.environ['SSH_AUTH_SOCK']='/home/chenkeyi/.local/share/harbor-rsi/near-r3-20261015/auth.sock'
 os.environ['PATH']=str(R/'client-bin-v2')+':'+os.environ['PATH'];main()
