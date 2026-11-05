"""Existing sole-controller leaf for shared59 NOP; combined89 gate is read-only."""
import importlib,json,shlex,subprocess,time
from pathlib import Path
base=importlib.import_module('environment_evidence_audit_r4');read=base.read;write=base.write;sha=base.sha
R=Path('/ssd/chenkeyi/qwen35-sft-772-20261101');B=R/'environment-preflight59-r1';E=R/'formal-native-eval-r1';C=Path('/data/chenkeyi/qwen35-sft-772-20261101/control')
UNIT='qwen35-env-preflight59-native18-20261102-r1.service'
def props():return dict(x.split('=',1)for x in subprocess.check_output(['systemctl','--user','show',UNIT,'-p','LoadState','-p','ActiveState','-p','MainPID'],text=True,timeout=5).splitlines())
def selected267_environment_gate():
 path=B/'ENV_PREFLIGHT_89_MANIFEST_R1.json'
 if not path.exists():return dict(ready=False,status='WAIT_REAL_SHARED59_AND_COMBINED89_FREEZE',manifest_path=str(path))
 combined=read(path);plan=read(B/'SAMPLING_MANIFEST_59_REMAINDER_R1.json');shared=R/'environment-preflight30/ENV_PREFLIGHT_30_MANIFEST.json';remaining=B/'ENV_PREFLIGHT_59_MANIFEST.json'
 assert combined['frozen']and combined['passed']==combined['expected_unique_tasks']==89
 assert combined['shared30_manifest_sha256']==sha(shared)==plan['shared30_manifest_sha256']and combined['remaining59_manifest_sha256']==sha(remaining)
 assert combined['sampling_manifest59_sha256']==sha(B/'SAMPLING_MANIFEST_59_REMAINDER_R1.json')==read(remaining)['sampling_manifest_sha256']
 assert read(shared)['frozen']and read(shared)['passed']==30 and read(remaining)['frozen']and read(remaining)['passed']==59
 assert sha(E/'manifests/OFFICIAL_89_TASK_IDENTITIES.json')==combined['official89_manifest_sha256']==plan['official89_manifest_sha256']
 assert len(combined['tasks'])==len({x['task_id']for x in combined['tasks']})==89 and {x['task_id']for x in combined['tasks']}==set(plan['all89_task_ids'])
 return dict(ready=True,status='REAL_SHARED89_ENVIRONMENT_FROZEN',manifest_path=str(path),manifest_sha256=sha(path),passed=89,agent_generation_calls=0)

def freeze_combined(owner):
 target=B/'ENV_PREFLIGHT_89_MANIFEST_R1.json'
 if target.exists():return selected267_environment_gate()
 a=R/'environment-preflight30/ENV_PREFLIGHT_30_MANIFEST.json';b=B/'ENV_PREFLIGHT_59_MANIFEST.json'
 if not b.exists():return dict(ready=False,status='WAIT_REMAINING59_NATIVE_NOP')
 first,second=read(a),read(b)
 if not(first.get('frozen')and first['passed']==30 and second.get('frozen')and second['passed']==59):return dict(ready=False,status='WAIT_REAL_SHARED59_VERIFIER_RUNTIME_AND_CLEANUP',passed30=first.get('passed'),passed59=second.get('passed'),failed59=second.get('failed'),unknown59=second.get('unknown'))
 if props()['ActiveState']in['active','activating','deactivating']:return dict(ready=False,status='WAIT_SHARED59_NATIVE_WORKER_CLOSED')
 plan=read(B/'SAMPLING_MANIFEST_59_REMAINDER_R1.json');assert sha(a)==plan['shared30_manifest_sha256']and second['sampling_manifest_sha256']==sha(B/'SAMPLING_MANIFEST_59_REMAINDER_R1.json')and second['agent_generation_calls']==0
 assert {x['task_id']for x in first['tasks']}==set(plan['excluded_shared30_task_ids'])and{x['task_id']for x in second['tasks']}=={x['task_id']for x in plan['rows']}
 identities={x['task_id']:x for x in read(E/'manifests/OFFICIAL_89_TASK_IDENTITIES.json')['tasks']}
 rows=[]
 for source,manifest in[(a,first),(b,second)]:
  for item in manifest['tasks']:
   for key in['task_toml_sha256','instruction_sha256','image_id']:assert item['official_identity'][key]==identities[item['task_id']][key]
   assert item['status']=='PASS';attempt=item['attempts'][-1];assert attempt['status']=='PASS'and attempt['cleanup']['complete']and attempt['actual_runtime']['engine_id']=='c6e16cdf-e878-4cc5-84c8-78a56c54b5c5'
   rows.append(dict(task_id=item['task_id'],status='PASS',source_manifest_path=str(source),source_manifest_sha256=sha(source),native_trial_id=attempt['native_trial_id'],result_sha256=attempt['result_sha256'],runtime_proof_sha256=attempt['runtime_proof_sha256']))
 assert len(rows)==len({r['task_id']for r in rows})==len({r['native_trial_id']for r in rows})==89
 write(target,dict(kind='REAL_SHARED30_PLUS_REMAINDER59_ENVIRONMENT_FREEZE89_R1',at=time.time(),frozen=True,expected_unique_tasks=89,passed=89,tasks=rows,shared30_manifest_sha256=sha(a),remaining59_manifest_sha256=sha(b),official89_manifest_sha256=plan['official89_manifest_sha256'],sampling_manifest59_sha256=sha(B/'SAMPLING_MANIFEST_59_REMAINDER_R1.json'),unique_controller_owner=owner,agent_generation_calls=0,official_verifier_rewards_not_model_scores=True,official_resources_and_verifier_limits_unchanged=True))
 return selected267_environment_gate()

def verify_public_cache_materializer(owner,plan):
 path=B/'PUBLIC_CACHE_MATERIALIZER_DEPLOYMENT_R1.json';binding=plan['public_cache_binding']
 if path.exists():
  proof=read(path);assert proof['source_sha256']==binding['materializer_sha256']and proof['archive_receipt_sha256']==binding['archive_receipt_sha256'];return path
 code="from pathlib import Path;import hashlib,json;script=Path("+repr(binding['remote_materializer_path'])+");receipt=Path('/home/chenkeyi/.local/share/harbor-rsi/qwen35-new772-tb21-20261101/public-verifier-cache/torch270-cp313-r1/PUBLIC_DEPENDENCY_ARCHIVE_READY_R1.json');print(json.dumps(dict(source_sha256=hashlib.sha256(script.read_bytes()).hexdigest(),archive_receipt_sha256=hashlib.sha256(receipt.read_bytes()).hexdigest())))"
 result=subprocess.run(['/usr/bin/ssh','-F',str(R/'control-ssh/formal-engine149-r1.conf'),'127.0.0.1',shlex.join(['python3','-c',code])],capture_output=True,text=True,timeout=20);assert result.returncode==0,result.stderr[-2000:]
 proof=json.loads(result.stdout);assert proof['source_sha256']==binding['materializer_sha256']and proof['archive_receipt_sha256']==binding['archive_receipt_sha256'];write(path,dict(**proof,at=time.time(),unique_controller_owner=owner,agent_generation_calls=0,no_archive_or_model_or_checkpoint_bytes_rehashed=True));return path

def advance(owner,state,launch):
 assert read(C/'NATIVE_ADVANCE_OWNER.json')==owner
 release=B/'EXECUTION_RELEASE_R1.json'
 if not release.exists():state['environment59']=dict(status='WAIT_FROZEN59_PREFLIGHT_DEPLOYMENT',missing=str(release));return
 frozen=read(release)
 for path,digest in frozen['required_source_sha256'].items():assert sha(Path(path))==digest,path
 plan=read(B/'SAMPLING_MANIFEST_59_REMAINDER_R1.json');assert sha(B/'SAMPLING_MANIFEST_59_REMAINDER_R1.json')==frozen['sampling_manifest_sha256']
 deployment=verify_public_cache_materializer(owner,plan);extra=dict(frozen,public_cache_materializer_deployment_sha256=sha(deployment))
 state['environment59']=dict(status='NATIVE_SHARED59_ZERO_GENERATION_PREFLIGHT',expected=59,concurrency=2,agent_generation_calls=0,native=launch(UNIT,'run-env-preflight59-native18-r1.py',[],B/'ADMISSION_R1.json',owner,extra))
 if(B/'ENV_PREFLIGHT_59_MANIFEST.json').exists():
  progress=read(B/'ENV_PREFLIGHT_59_MANIFEST.json');state['environment59']['progress']={k:progress.get(k)for k in['passed','failed','unknown','running','pending','terminal','frozen']}
 state['environment89']=freeze_combined(owner)
if __name__=='__main__':raise SystemExit('Only existing unique advance may call this leaf')
