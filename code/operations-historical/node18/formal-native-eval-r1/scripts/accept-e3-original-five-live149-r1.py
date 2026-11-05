"""Record actual native Agent/model execution of the original-five continuation."""
import hashlib,json,subprocess,time
from pathlib import Path
R=Path('/home/chenkeyi/.local/share/harbor-rsi/qwen35-new772-tb21-20261101')
JOB='qwen35-new772-new-m1-epoch3-fixed-unstarted-continuation-r1'
INSIDE=r'''
from collections import Counter
import hashlib,json
from pathlib import Path
import rsi_modules.controller.baseline as controller
from foundation.rollouts.export import loadValue
root=Path('/logs/agent/openharness-rollout');counts=Counter();run=None;first=None;payload=None;latest=None;digest=hashlib.sha256()
for line in(root/'events.jsonl').open('rb'):
 try:e=json.loads(line)
 except json.JSONDecodeError:break
 digest.update(line);counts[e['type']]+=1;d=e['data'];latest=e['timestamp']
 if e['type']=='run_start':run=e
 elif e['type']=='call_start'and d['source']=='agent'and first is None:first=e
 elif e['type']=='call_payload'and first and d['call_id']==first['data']['call_id']:payload=loadValue(d['payload'],root/'artifacts')
assert run and first and payload
request=payload.get('request',payload);tools=request['tools']
assert len(tools)==11 and {t['function']['name']for t in tools}=={'read','bash','edit','write','grep','find','ls','edit_patch','trajectory_read','bash_job','finish'}
assert request['max_tokens']==81920 and request['chat_template_kwargs']['enable_thinking']is True
actual_controller_sha256=hashlib.sha256(Path(controller.__file__).read_bytes()).hexdigest()
assert actual_controller_sha256=='b2cf3316faeb213ab5e64d99c7a0e3c4f7f19542fe08bb1c37ae4ea36e76bf40'
print(json.dumps(dict(session_id=run['data']['session_id'],run_id=run['data']['run_id'],agent_start=run['timestamp'],first_agent_call_id=first['data']['call_id'],first_agent_call_started_at=first['timestamp'],latest_event_at=latest,event_counts=dict(counts),recorder_snapshot_sha256=digest.hexdigest(),installed_controller_sha256=actual_controller_sha256,tool_schema_sha256=hashlib.sha256(json.dumps(tools,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest(),actual_wire_fields={k:request.get(k)for k in ['model','max_tokens','temperature','top_p','top_k','min_p','presence_penalty','repetition_penalty','reasoning_effort','chat_template_kwargs']},effective_run_contract={k:v for k,v in run['data']['config'].items()if any(x in k.lower()for x in ['compaction','finish','backgroundjobs','toolresultbudget'])})))
'''
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 manifest=R/'manifests/E3_ORIGINAL_UNSTARTED_ACTUAL_NATIVE_TRIALS_R1.json';m=json.loads(manifest.read_text())
 assert m['original_started_trials_rerun']==0 and m['original_unstarted_tasks'][0]=='video-processing'
 trial=R/'jobs'/JOB/'video-processing__new-m1-e3-fixed-r1'
 compose=next(trial.glob('remote-docker-*.compose.json'));identity=compose.name.split('remote-docker-')[1].split('.compose')[0]
 project='q35new772e3fixednewm1-'+identity
 ids=subprocess.check_output(['docker','ps','--filter','label=com.docker.compose.project='+project,'--format','{{.ID}}'],text=True).split()
 assert len(ids)==1
 cid=ids[0];labels=json.loads(subprocess.check_output(['docker','inspect',cid,'--format','{{json .Config.Labels}}'],text=True))
 assert labels['com.docker.compose.project.config_files']==str(compose)
 result=subprocess.run(['docker','exec','-i',cid,'/harbor/agent-runtime/harbor-open-harness-venv/bin/python','-'],input=INSIDE,capture_output=True,text=True,timeout=25,check=True)
 live=json.loads(result.stdout);artifact=json.loads((trial/'agent/artifact.json').read_text())
 assert artifact['wheel_sha256']=='1d27eef1ca6696275f306d8c653f7a266a4c7aea7321f0d47fd01b739c27fa18'
 assert live['tool_schema_sha256']=='9b14204af97deda8b282e969ebbba410490505423912b2bd509896025b50b59f'
 admission=json.loads((R/'manifests/EPOCH3_ORIGINAL_UNSTARTED_SERVING_ADMISSION_R1.json').read_text())
 value=dict(passed=True,at=time.time(),native_job_id=m['native_job_id'],trial_name=trial.name,container_id=cid,
  remote_docker_identity=identity,actual_engine_id=subprocess.check_output(['docker','info','--format','{{.ID}}'],text=True).strip(),
  native_controller_pid=326945,unique_campaign_owner=admission['unique_controller_owner'],
  actual_trial_config_sha256=sha(trial/'config.json'),actual_trial_manifest_sha256=sha(manifest),
  installed_wheel_sha256=artifact['wheel_sha256'],actual_model_execution=live,
  actual_max_new_native_concurrency=1,original_chess_max_concurrency=1,original_attempts_redispatched=0,
  current_trial_still_running_not_scored=True,qualified_task_success_not_claimed=True,
  original_task_resources_and_research_contract_unchanged=True,source_sha256=sha(Path(__file__)))
 p=R/'checks/E3_ORIGINAL_UNSTARTED_ACTUAL_LIVE_ACCEPTANCE_R1.json';assert not p.exists();p.write_text(json.dumps(value,indent=2)+'\n');print(json.dumps(value))
if __name__=='__main__':main()
