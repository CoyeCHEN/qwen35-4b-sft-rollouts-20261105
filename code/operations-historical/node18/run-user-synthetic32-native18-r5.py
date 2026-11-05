"""Native32 NOP preparation and separately gated M1E3 n1, no model retry."""
import argparse,asyncio,importlib,json,os,subprocess,time,urllib.request
from pathlib import Path
from harbor.job import Job
m=importlib.import_module('synthetic32-native-config18-r4');R=m.R;B=m.B;C=m.C;read=m.read;write=m.write;sha=m.sha
async def main(stage):
 admission=read(B/(stage+'-ADMISSION_R5.json'));assert admission['unique_controller_owner']==read(C/'NATIVE_ADVANCE_OWNER.json')and admission['source_sha256']==sha(Path(__file__))
 os.environ['PATH']=m.native.D['transport']['private_client_bin']+':'+os.environ['PATH'];os.environ['OPENAI_API_KEY']='node18-local';os.environ['TMPDIR']=str(R/'tmp');os.environ['RSI_ENV_PREFLIGHT_SPEC_BASE']=str(B/'env-runtime')
 frozen,cfg=m.configuration(stage)
 manifest=read(B/'ENV_PREFLIGHT_32_MANIFEST.json');assert manifest['frozen'] and manifest['passed']==32 and all(t['status']=='PASS'for t in manifest['tasks']) and manifest['deployment_manifest_sha256']==sha(B/'SYNTHETIC32_DEPLOYMENT_R3.json'),'Explicit image identity and complete own32 environment acceptance required'
 mapping=read(B/'EVAL_TASK_IMAGE_BINDING_R4.json');assert mapping['environment_manifest_sha256']==sha(B/'ENV_PREFLIGHT_32_MANIFEST.json')
 proof_path=Path(admission['pre_model_resume_proof_path']);assert sha(proof_path)==admission['pre_model_resume_proof_sha256'];resume_proof=read(proof_path);assert resume_proof['previous_actual_model_attempts']==0 and len(resume_proof['rows'])==32
 proven_tasks=set();proven_trials=set()
 for row in resume_proof['rows']:
  result_path=Path(row['result_path']);assert sha(result_path)==row['result_sha256'];previous=read(result_path);task=Path(previous['config']['task']['path']).name
  assert task not in proven_tasks and previous['id']not in proven_trials;proven_tasks.add(task);proven_trials.add(previous['id'])
  assert previous.get('agent_setup')is None and previous.get('agent_execution')is None and previous.get('agent_result')is None,'Previous Agent phase is not proven absent'
  assert previous['config']['agent']['kwargs']['config']['model']['id']==cfg.agents[0].kwargs['config']['model']['id']
  assert not(result_path.parent/'ACTUAL_AGENT_START_R4.json').exists()
  assert not any(f.is_file()and f.stat().st_size and any(marker in str(f.relative_to(result_path.parent)).lower()for marker in ['recorder','trajectory','payload','open-harness.stdout','effective-config.json'])for folder in ['agent','agent-logs']for f in(result_path.parent/folder).rglob('*')),'Previous model/Recorder evidence is not absent'
 assert proven_tasks=={x['task_id']for x in frozen['tasks']}
 assert cfg.job_name.endswith('-r4');cfg.job_name=cfg.job_name.removesuffix('-r4')+'-r5'
 assert not(cfg.jobs_dir/cfg.job_name).exists(),'Never recreate native32 jobs'
 job=await Job.create(cfg);m.configure_trials(job,stage,frozen);assert len(job._trial_configs)==32
 for trial in job._trial_configs:
  assert trial.trial_name.endswith('-r4');trial.trial_name=trial.trial_name.removesuffix('-r4')+'-r5';trial.environment.kwargs['project_namespace']='q35synth32evalr5'
 job._remaining_trial_configs=job._trial_configs
 write(B/(stage+'-ACTUAL_NATIVE_TRIALS_R5.json'),dict(at=time.time(),native_job_id=str(job.id),trials=[t.model_dump(mode='json')for t in job._trial_configs],source_manifest_sha256=sha(B/'FROZEN_USER_SYNTHETIC32_SOURCE_R2.json'),source_sha256=sha(Path(__file__)),image_binding_manifest_sha256=sha(B/'EVAL_TASK_IMAGE_BINDING_R4.json'),pre_model_resume_proof_path=str(proof_path),pre_model_resume_proof_sha256=sha(proof_path),previous_actual_model_attempts=0,actual_model_calls_before_run=0,stage=stage))
 async def gate(event):
  task=event.config.task.path.name;port=int(event.config.agent.kwargs['config']['model']['baseUrl'].split(':')[-1].split('/')[0]);opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
  while True:
   manifest=read(B/'ENV_PREFLIGHT_32_MANIFEST.json')if(B/'ENV_PREFLIGHT_32_MANIFEST.json').exists()else None
   ready=next((v for v in manifest['tasks']if v['task_id']==task and v['status']=='PASS'),None)if manifest else None
   if ready:
    try:
     with opener.open('http://127.0.0.1:'+str(port)+'/model_info',timeout=3)as r:info=json.load(r)
     if info['weight_version']==frozen['model_manifest_sha256']and info['model_path']==str(R/'epoch-models/new-m1-epoch3'):break
    except OSError:pass
   await asyncio.sleep(2)
  path=B/'model-admissions-r5';path.mkdir(exist_ok=True);write(path/(task+'.json'),dict(at=time.time(),task_id=task,env_manifest_sha256=sha(B/'ENV_PREFLIGHT_32_MANIFEST.json'),runtime_model_info=info,port=port,model_attempt_not_previously_started=True))
 image_query_budget=asyncio.Semaphore(4)
 def identity_check(event):
  task=event.config.task.path.name;before=next(x for x in read(B/'ENV_PREFLIGHT_32_MANIFEST.json')['tasks']if x['task_id']==task)['attempts'][-1]['actual_runtime'];d=Path(event.config.trials_dir)/event.trial_name;files=list(d.glob('remote-docker-*.jsonl'));assert len(files)==1;ident=files[0].stem.removeprefix('remote-docker-');args=['docker','--host',m.native.D['task_engine']['native_endpoint']];ids=subprocess.check_output(args+['ps','--filter','label=io.harbor.remote-docker.identity='+ident,'-q'],text=True,timeout=15).split();assert len(ids)==1;actual=json.loads(subprocess.check_output(args+['inspect',ids[0]],text=True,timeout=15))[0];assert actual['Image']==before['actual_image_id'],'Accepted source image changed before model attempt'
  write(d/'ENVIRONMENT_MATCHES_ACCEPTED_PREPARATION.json',dict(passed=True,image_id=actual['Image'],prepared_image_id=before['actual_image_id'],identity=ident,model_generation_calls_at_check=0))
 async def identity(event):
  async with image_query_budget:await asyncio.to_thread(identity_check,event)
 async def agent_started(event):
  assert event.event.value=='agent-start' and event.result.environment_setup.finished_at and event.result.agent_setup.finished_at and event.result.agent_execution is None,'Identity gate must precede native Agent.run after completed environment and CLI setup'
  await identity(event)
  d=Path(event.config.trials_dir)/event.trial_name;write(d/'ACTUAL_AGENT_START_R5.json',dict(at=time.time(),native_trial_uuid=str(event.trial_id),task_id=event.config.task.path.name,model='NEW-M1 Epoch3',env_manifest_sha256=sha(B/'ENV_PREFLIGHT_32_MANIFEST.json')))
  progress()
 job.on_trial_started(gate);job.on_agent_started(agent_started)
 def progress():
  rows=[]
  for p in job.job_dir.glob('*/result.json'):
   x=read(p);rows.append(dict(task_id=Path(x['config']['task']['path']).name,trial_id=x['id'],trial_name=x['trial_name'],result_path=str(p),result_sha256=sha(p),raw_reward=(x.get('verifier_result')or{}).get('rewards'),exception=(x.get('exception_info')or{}).get('exception_type'),failure_phase=x.get('failure_phase')))
  write(B/(stage+'-NATIVE_PROGRESS_R5.json'),dict(at=time.time(),expected=32,terminal=len(rows),actual_agent_starts=len(list(job.job_dir.glob('*/ACTUAL_AGENT_START_R5.json'))),native_job_id=str(job.id),rows=rows,model_checkpoint='NEW-M1 Epoch3',n1=True,not_official_tb21=True,model_generation_calls=0 if stage=='prep'else None,final_recorder_and_verifier_audit_required=True))
 async def ended(event):progress()
 job.on_trial_ended(ended);progress();result=await job.run();progress();assert len(result.trial_results)==32;write(B/(stage+'-NATIVE_ALL_TERMINAL_R5.json'),dict(at=time.time(),terminal=32,native_job_id=str(job.id),final_audit_required=True))
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('stage',choices=['eval']);args=p.parse_args();asyncio.run(main(args.stage))
