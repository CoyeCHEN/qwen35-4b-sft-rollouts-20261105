"""Subordinate, admitted serving handoff only; never dispatches model Trials."""
import fcntl,hashlib,importlib,json,os,shlex,subprocess,time,urllib.request,urllib.parse
from pathlib import Path
R=Path('/ssd/chenkeyi/qwen35-sft-772-20261101');B=R/'synthetic32';C=Path('/data/chenkeyi/qwen35-sft-772-20261101/control')
phase=importlib.import_module('diagnostic150-phase18-r1');read=phase.read;write=phase.save;sha=phase.sha
def props(unit):return dict(x.split('=',1)for x in subprocess.check_output(['systemctl','--user','show',unit,'-p','MainPID','-p','ActiveState','-p','LoadState'],text=True).splitlines())
def get(port,path):
 opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
 with opener.open('http://127.0.0.1:'+str(port)+path,timeout=5)as response:return json.load(response)
def ancestors(pid):
 result=[]
 while pid>1 and pid not in result:
  result.append(pid);p=Path('/proc')/str(pid)/'stat';pid=int(p.read_text().rsplit(')',1)[1].split()[1])
 return result
def leases():
 remote='/home/chenkeyi/.local/share/harbor-rsi/qwen35-new772-tb21-20261101/checks/read-priority32-gpu-leases149-r1.py'
 result=subprocess.run(['/usr/bin/ssh','-F',str(R/'control-ssh/formal-engine149-r1.conf'),'127.0.0.1','python3 '+shlex.quote(remote)],capture_output=True,text=True,timeout=35,check=True)
 return json.loads(result.stdout)
def verify_public_probe_closure(admission,models,target):
 path=Path(admission['public_probe_closure_proof']);assert sha(path)==admission['public_probe_closure_sha256'];proof=read(path)
 expected={x['task_id']for x in read(R/'formal-native-eval-r1/manifests/DIAGNOSTIC30_SAMPLING_MANIFEST_R1.json')['selected_task_identities']}
 assert len(expected)==30 and {x['task_id']for x in proof['runtime_proofs']}==expected
 assert proof['all_current_public_probe_stages_closed']and proof['future_common30_preflights_use_updated_role_spec']and proof['new_torch_preflight_admission_requires_cold_roles_ready']
 for item in proof['runtime_proofs']:
  p=Path(item['runtime_proof_path']);assert sha(p)==item['runtime_proof_sha256'];runtime=read(p);assert runtime['passed']and runtime['task_id']==item['task_id']and runtime['model_generation_calls']==0
 # Check actual in-progress native common30 preparation, not just a summary flag.
 base=R/'environment-preflight30';paths=[base/'ACTUAL_NATIVE_TRIALS_R1.json'];registry=base/'RECHECK_REGISTRY_R1.json'
 if registry.exists():paths += [Path(p)for p in read(registry)['actual_trial_manifests']]
 for actual in paths:
  if not actual.exists():continue
  for cfg in read(actual)['trials']:
   trial=Path(cfg['trials_dir'])/cfg['trial_name']
   if trial.exists()and not(trial/'result.json').exists():
    runtime=trial/'agent/ENV_PREFLIGHT_RUNTIME.json';assert runtime.exists()and read(runtime)['passed'],'A common30 public probe may still run with old endpoint roles'
 torch_spec=Path(proof['future_torch_spec_path']);assert sha(torch_spec)==proof['future_torch_spec_sha256'];spec=read(torch_spec);actual={urllib.parse.urlsplit(x['url']).port:x for x in spec['model_endpoints']};expected_endpoints={}
 for model in models.values():
  for replica in model.get('replicas')or[dict(port=model['port'])]:expected_endpoints[replica['port']]=dict(model_path=model['model_path'],weight_version=model['weight_version'])
 for port in [18300,18309]:expected_endpoints[port]=dict(model_path=target['model_path'],weight_version=target['weight_version'])
 assert len(actual)==len(expected_endpoints)==8 and set(actual)==set(expected_endpoints)
 for port,item in expected_endpoints.items():assert actual[port]['model_path']==item['model_path']and actual[port]['weight_version']==item['weight_version']
 return dict(proof_path=str(path),proof_sha256=sha(path),verified_runtime_tasks=30,future_torch_spec_path=str(torch_spec),future_torch_spec_sha256=sha(torch_spec),common30_full_verifier_gate_not_required=True)
def main():
 admission=read(B/'PRIORITY_GPU_REPLICAS_ADMISSION_R1.json');owner=read(C/'NATIVE_ADVANCE_OWNER.json');assert admission['unique_controller_owner']==owner and admission['source_sha256']==sha(Path(__file__))
 config=read(R/'configs/diagnostic150-five-model-r1.json');models={x['tag']:x for x in config['models']};target=models['new-m1-e3-diag'];assert target['weight_version']==sha(Path(target['model_manifest']))
 public_closure=verify_public_probe_closure(admission,models,target)
 # Validate current, accepted future placements explicitly exclude the borrowed ports.
 future=read(Path(admission['future_placement_proof']));assert sha(Path(admission['future_placement_proof']))==admission['future_placement_sha256'];assert not({18300,18309}&set(future['common30_future_ports']))
 evidence=B/'priority-gpu-replicas-r1';evidence.mkdir(exist_ok=True)
 with(evidence/'handoff.lock').open('a')as lock:
  fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
  write(evidence/'PUBLIC_PROBE_CLOSURE_VERIFIED.json',public_closure);before=leases();write(evidence/'CLI_LEASES_BEFORE.json',before);assert before['complete']and not before['candidate_ports_in_use'],'Active/unknown CLI lease: preserve service'
  authorized=read(R/'new-sft/workspace/configs/runtime.json')['authorized_gpu_uuids'];rows=[]
  for tag,index,port in [('new-m2-e1-diag',0,18300),('new-m2-e5-diag',5,18309)]:
   previous=next(x for x in models[tag]['replicas']if x['gpu_index']==index);unit=previous['unit'];state=props(unit);assert state['ActiveState']=='active';pid=int(state['MainPID']);ticks=Path('/proc')/str(pid)/'stat';start_ticks=ticks.read_text().rsplit(')',1)[1].split()[19]
   assert previous['gpu_uuid']in authorized
   actual_gpu=subprocess.check_output(['nvidia-smi','-i',str(index),'--query-gpu=uuid','--format=csv,noheader'],text=True).strip();assert actual_gpu==previous['gpu_uuid']
   current_pids=[int(s)for s in subprocess.check_output(['nvidia-smi','-i',str(index),'--query-compute-apps=pid','--format=csv,noheader,nounits'],text=True).split()];assert current_pids and all(pid in ancestors(p)for p in current_pids),'Another GPU process owner: preserve all services'
   info=get(port,'/model_info');assert info['weight_version']==models[tag]['weight_version']and info['model_path']==models[tag]['model_path'];load=get(port,'/get_load');assert load and all(r['num_reqs']==0 and r['num_waiting_reqs']==0 for r in load)
   for old_unit in ['qwen35-new772-diag150-native-new-m2-e1-diag-20261102-r1.service','qwen35-new772-diag150-native-new-m2-e5-diag-20261102-r1.service']:assert props(old_unit)['ActiveState']=='inactive'
   verify_public_probe_closure(admission,models,target);observed=leases();assert observed['complete']and not observed['candidate_ports_in_use'];load=get(port,'/get_load');assert load and all(r['num_reqs']==0 and r['num_waiting_reqs']==0 for r in load);assert props(unit)['MainPID']==str(pid)and ticks.read_text().rsplit(')',1)[1].split()[19]==start_ticks
   row=dict(at=time.time(),gpu_index=index,gpu_uuid=actual_gpu,old_unit=unit,old_main_pid=pid,old_start_ticks=start_ticks,old_gpu_processes=current_pids,old_model_info=info,old_load=load,lease_evidence=observed,new_model_manifest_sha256=target['weight_version']);write(evidence/('gpu'+str(index)+'-before.json'),row)
   # Graceful stop of this project's verified idle service only; no kill/prune.
   subprocess.run(['systemctl','--user','stop',unit],check=True,timeout=60)
   model=dict(target,tag='synthetic32-m1e3-priority');replica=dict(gpu_index=index,gpu_uuid=actual_gpu,port=port,unit='qwen35-user-synthetic32-m1e3-gpu'+str(index)+'-20261102-r1.service')
   row['new_replica']=phase.start_replica(model,replica);row['at_after_launch']=time.time();write(evidence/('gpu'+str(index)+'-launched.json'),row);rows.append(row)
  write(evidence/'COLD_REPLICAS_LAUNCHED.json',dict(at=time.time(),replicas=rows,unique_controller_owner=owner,new_trial_dispatches=0,not_ready_until_actual_model_info_verified=True))
if __name__=='__main__':main()
