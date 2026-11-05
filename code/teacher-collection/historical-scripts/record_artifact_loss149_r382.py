"""Retain a raw reward-one artifact-transfer failure without inventing a Recorder."""
import datetime
import hashlib
import json
from pathlib import Path
import shlex
import subprocess

R=Path('/home/chenkeyi/.local/share/harbor-rsi/qwen35-new-cf500-tmax500-20261029')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
 trial=R/'stream/collection-r4/trials/task_007206_2ea22c7f__VqWALwx'
 path=trial/'result.json'; result=json.loads(path.read_text())
 assert result['id']=='fd716d1d-d77f-4d99-92a4-0bcdf99fff04'
 assert result['verifier_result']['rewards']['reward']==1 and result['verifier_result']['return_code']==0
 assert not result['exception_info'] and not result['infrastructure_errors']
 native,=trial.glob('remote-docker-*.jsonl')
 events=[json.loads(line) for line in native.open()]
 failures=[x for x in events if x['action']=='operation_interrupted' and 'transfer-' in x.get('operation','')]
 assert len(failures)==1 and failures[0]['error_type']=='TimeoutError'
 cleaned=[x for x in events if x['action']=='cleaned']; assert len(cleaned)==1
 assert failures[0]['time']<cleaned[0]['time']
 assert not (trial/'agent/openharness-rollout/events.jsonl').exists()
 cfg=result['config']['environment']['kwargs'];identity=failures[0]['identity']
 code="""import json,subprocess
from pathlib import Path
workspace=Path(WORKSPACE)
cli=['docker','--host','unix://'+SOCKET]
engine=subprocess.run(cli+['info','--format','{{.ID}}'],check=True,capture_output=True,text=True,timeout=20).stdout.strip()
out=dict(engine_id=engine,workspace_exists=workspace.exists())
for kind,args in [('matching_containers',['ps','-a','--filter','label=io.harbor.remote-docker.identity='+IDENTITY,'--format','{{.ID}}']),('matching_volumes',['volume','ls','--filter','label=io.harbor.remote-docker.identity='+IDENTITY,'--format','{{.Name}}'])]:
 out[kind]=subprocess.run(cli+args,check=True,capture_output=True,text=True,timeout=20).stdout.splitlines()
print(json.dumps(out))""".replace('WORKSPACE',repr(failures[0]['workspace'])).replace('SOCKET',repr(cfg['remote_socket_path'])).replace('IDENTITY',repr(identity))
 authority=json.loads((R/'checks/CURRENT_DISPATCH_AUTHORITY_R21.json').read_text())
 campaign=json.loads(Path(authority['manifest']).read_text())
 deployment=json.loads(Path(campaign['deployment_config']).read_text())
 reply=subprocess.run([*deployment['ssh'],deployment['host'],shlex.join(['python3','-c',code])],check=True,capture_output=True,text=True,timeout=80)
 scope=json.loads(reply.stdout)
 assert scope['engine_id']==deployment['runtime']['engine_id']
 assert not scope['workspace_exists'] and not scope['matching_containers'] and not scope['matching_volumes']
 found=[]
 for pool in ['CALIBFORGE','TMAX']:
  for kind in ['SUCCESS_INDEX','FAILURE_OR_PENDING_INDEX']:
   for line in (R/'indexes'/(pool+'_'+kind+'.jsonl')).open():
    row=json.loads(line)
    if row['trial_id']==result['id']:found.append(row)
 row,=found;assert not row['qualified_success'] and not row['is_primary_trajectory']
 value=dict(checked_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),trial_id=result['id'],
  task_id='task_007206_2ea22c7f',result_path=str(path),result_sha256=sha(path),raw_reward=1,
  raw_verifier_completed=True,raw_native_exception=None,raw_native_infrastructure_errors=[],
  qualified_success=False,is_primary_trajectory=False,
  evidence_classification='ARTIFACT_COLLECTION_FAILED_RECORDER_AND_NORMAL_CLOSURE_UNPROVED',
  current_index_classification=row['classification'],current_index_audit_error=row.get('audit_error'),
  interrupted_transfer_at=failures[0]['time'],native_cleaned_at=cleaned[0]['time'],native_events_path=str(native),native_events_sha256=sha(native),
  raw_agent_file_names=sorted(p.name for p in (trial/'agent').iterdir()),
  exact_owned_scope_recovery_probe=scope,known_owned_source_no_longer_present=True,
  normal_agent_closure_proved=False,recorder_complete=False,actual_model_call_count=None,actual_usage_or_cost_reconstructed=False,
  raw_result_reward_or_task_modified=False,model_or_teacher_retries=0,
  source_sha256=sha(Path(__file__)))
 target=R/'checks/ARTIFACT_LOSS_RAW_REWARD_ONE_R382.json'
 with target.open('x') as stream:json.dump(value,stream,indent=2)
 print(json.dumps(value))


if __name__=='__main__':main()
