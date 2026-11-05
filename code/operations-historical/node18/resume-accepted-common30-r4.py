"""Native continuations of never-started model decisions; original Trials retained."""
import importlib,json,subprocess,time,urllib.request
from pathlib import Path
from environment_evidence_audit_r3 import read,write,sha
R=Path('/ssd/chenkeyi/qwen35-sft-772-20261101');E=R/'formal-native-eval-r1';C=Path('/data/chenkeyi/qwen35-sft-772-20261101/control');B=R/'environment-preflight30';PY=R/'env/harbor-native-eval-r1/bin/python'
def records():
 models=read(R/'configs/diagnostic150-five-model-r1.json')['models'];dirs={E/'jobs'/m['job_name']for m in models}
 dirs|={E/'jobs/qwen35-new772-new-m1-epoch3-fixed-diagnostic',E/'jobs/qwen35-new772-new-m1-epoch3-fixed-unstarted-continuation-r1'}
 for p in(E/'manifests').glob('PRE_MODEL_ENV_RECOVERY_PLAN_*_R1.json'):dirs.add(E/'jobs'/read(p)['model']['job_name'])
 rows=[]
 for parent in dirs:
  for p in parent.glob('*/config.json'):
   cfg=read(p);d=p.parent;a=cfg['agent']; model=(a.get('kwargs')or{}).get('config',{}).get('model',{}).get('id');raw=read(d/'result.json')if(d/'result.json').exists()else None
   markers=[str(x)for x in(d/'agent').rglob('*')if x.is_file()and x.stat().st_size and(x.name=='effective-config.json'or x.name.startswith('open-harness.stdout')or'session'in str(x.relative_to(d/'agent'))or'recorder'in str(x.relative_to(d/'agent')))]
   started=bool(markers or raw and(raw.get('agent_execution')or raw.get('agent_result')))
   rows.append(dict(model_id=model,task_id=Path(cfg['task']['path']).name,original_trial_path=str(d),config_sha256=sha(p),result_sha256=sha(d/'result.json')if raw else None,actual_or_conservatively_started=started,model_evidence=markers,agent_execution=raw.get('agent_execution')if raw else None,config=cfg))
 remote=E/'manifests/ORIGINAL149_MODEL_ATTEMPT_LEDGER_R1.json'
 if remote.exists():rows+=read(remote)['rows']
 # All three detached original executions are proven actual Agent executions.
 p=R/'detached-native-recovery-r1/ADMISSION_R1.json'
 if p.exists():
  for x in read(p)['trials']:
   cfg=read(Path(x['source_directory'])/'config.json');rows.append(dict(model_id=cfg['agent']['kwargs']['config']['model']['id'],task_id=x['task_id'],original_trial_path=x['original_trial_path'],actual_or_conservatively_started=True,detached_driver_loss=True))
 return models,rows
def advance(owner,state):
 assert read(C/'NATIVE_ADVANCE_OWNER.json')==owner and read(B/'ENV_PREFLIGHT_30_MANIFEST.json')['frozen']
 binding_path=B/'PUBLIC_VERIFIER_CACHE_BINDING_R1.json';binding=read(binding_path)
 assert all(k in binding for k in ['archive_receipt_sha256','materializer_sha256','archive_sha256','remote_materializer_path','runtime_spec_path','runtime_spec_sha256'])
 assert sha(Path(binding['runtime_spec_path']))==binding['runtime_spec_sha256']
 models,ledger=records();plan=read(E/'manifests/DIAGNOSTIC150_TRIAL_PLAN_R1.json');results=[]
 assert (E/'manifests/ORIGINAL149_MODEL_ATTEMPT_LEDGER_R1.json').exists(),'Read-only original149 attempt ledger required; do not guess absent results'
 write(B/'MODEL_ATTEMPT_LEDGER_BEFORE_RESUME_R1.json',dict(at=time.time(),rows=[{k:v for k,v in x.items()if k!='config'}for x in ledger],old_native_pending_admission_remains_physically_closed=True))
 opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
 for model in models:
  tag=model['tag'];registration=B/('ACCEPTED_CONTINUATION_'+tag+'_R3.json');unit='qwen35-accepted30-'+tag+'-20261102-r3.service'
  fresh_registration=not registration.exists()
  if fresh_registration:
   allrows=[x for x in ledger if x['model_id']==model['model_id']];started={x['task_id']for x in allrows if x['actual_or_conservatively_started']};items=[x for x in plan['trials']if x['tag']==tag and x['task_id']not in started]
   template=next((x['config']for x in allrows if x.get('config')),None);assert template is not None,'No accepted source Agent configuration for '+tag
   ports=[18301]if tag=='new-m2-e1-diag'else[18302,18308]if tag=='new-m2-e5-diag'else[model['port']]
   for port in ports:
    with opener.open('http://127.0.0.1:'+str(port)+'/model_info',timeout=3)as response:info=json.load(response)
    assert info['weight_version']==model['weight_version']and info['model_path']==model['model_path']
   write(registration,dict(at=time.time(),tag=tag,model=model,trials=items,retained_started_tasks=sorted(started),template_config=template,ports=ports,concurrency=2*len(ports),unique_controller_owner=owner,environment_manifest_sha256=sha(B/'ENV_PREFLIGHT_30_MANIFEST.json'),source_sha256=sha(R/'run-accepted-common30-native18-r3.py'),zero_started_model_attempts_retried=True,public_verifier_cache_binding=binding,public_verifier_cache_binding_sha256=sha(binding_path)))
  registered=read(registration);props=dict(x.split('=',1)for x in subprocess.check_output(['systemctl','--user','show',unit,'-p','MainPID','-p','LoadState','-p','ActiveState'],text=True).splitlines())
  dispatch=B/('ACCEPTED_NATIVE_DISPATCH_'+tag+'_R3.json')
  if registered['trials'] and props['LoadState']=='not-found' and fresh_registration and not dispatch.exists():
   write(dispatch,dict(at=time.time(),owner=owner,registration_sha256=sha(registration),unit=unit,registered_once_before_native_dispatch=True))
   assert registered['unique_controller_owner']==owner,'Controller handoff requires explicit unchanged-plan adoption before first launch'
   log=R/'logs'/(unit+'.log');subprocess.run(['systemd-run','--user','--unit='+unit,'--property=MemoryMax=16G','--property=StandardOutput=append:'+str(log),'--property=StandardError=append:'+str(log),'--setenv=PYTHONPATH='+str(R)+':'+str(E/'scripts'),str(PY),str(R/'run-accepted-common30-native18-r3.py'),tag],check=True,capture_output=True,text=True,timeout=8)
  p=B/('CONTINUATION_PROGRESS_'+tag+'_R3.json');results.append(dict(tag=tag,never_model_started_tasks_admitted=len(registered['trials']),prior_model_tasks_retained=len(registered['retained_started_tasks']),unit=unit,progress=read(p)if p.exists()else None))
 state.update(status='ENV30_FROZEN_FIVE_NATIVE_CONTINUATIONS_RUNNING',common30_native_continuations=results)
