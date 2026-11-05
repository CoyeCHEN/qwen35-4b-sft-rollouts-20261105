"""One native Harbor Job per checkpoint; no model attempt is retried."""
import asyncio,importlib,os,sys,time,urllib.request
from pathlib import Path
from harbor.job import Job
from harbor.models.job.config import JobConfig
from harbor.models.trial.config import TrialConfig
from environment_evidence_audit_r3 import read,write,sha
R=Path('/ssd/chenkeyi/qwen35-sft-772-20261101');E=R/'formal-native-eval-r1';B=R/'environment-preflight30';C=Path('/data/chenkeyi/qwen35-sft-772-20261101/control');sys.path[:0]=[str(R),str(E/'scripts')]
native=importlib.import_module('run-formal-native-tb2118-r2');prep=importlib.import_module('evaluation-preparation18-r1')
async def main(tag):
 p=B/('ACCEPTED_CONTINUATION_'+tag+'_R1.json');a=read(p);assert a['unique_controller_owner']==read(C/'NATIVE_ADVANCE_OWNER.json')and a['source_sha256']==sha(Path(__file__))
 manifest=read(B/'ENV_PREFLIGHT_30_MANIFEST.json');assert manifest['frozen']and manifest['passed']==30 and sha(B/'ENV_PREFLIGHT_30_MANIFEST.json')==a['environment_manifest_sha256']
 cfg=JobConfig.model_validate_json(native.selected_config(read(E/'manifests/FORMAL_801_TRIAL_PLAN.json')).read_text());names={x['task_id']for x in a['trials']};cfg.tasks=[t for t in cfg.tasks if t.path.name in names];cfg.agents=[TrialConfig.model_validate(a['template_config']).agent];cfg.job_name='qwen35-accepted30-'+tag+'-20261102-r1';cfg.jobs_dir=E/'jobs';cfg.n_concurrent_trials=a['concurrency'];cfg.n_attempts=1;cfg.retry.max_retries=0
 assert len(cfg.tasks)==len(names)==len(a['trials']);assert not(cfg.jobs_dir/cfg.job_name).exists();os.environ['PATH']=native.D['transport']['private_client_bin']+':'+os.environ['PATH'];os.environ['OPENAI_API_KEY']='node18-local';os.environ['TMPDIR']=str(R/'tmp')
 job=await Job.create(cfg);items=[dict(x,trial_name=x['task_id']+'__accepted30-'+tag+'-r1')for x in a['trials']];native.apply_trial_overrides(job._trial_configs,dict(trials=items),read(B/'environment-profiles-recheck-r2.json'),namespace='q35accepted30r1')
 for index,t in enumerate(job._trial_configs):
  prep.append_ipam(t,tag,t.task.path.name,1);t.agent.kwargs['config']['model']['baseUrl']='http://172.17.0.1:'+str(a['ports'][index%len(a['ports'])])+'/v1'
 job._remaining_trial_configs=job._trial_configs;write(B/('CONTINUATION_ACTUAL_TRIALS_'+tag+'_R1.json'),dict(at=time.time(),native_job_id=str(job.id),trials=[t.model_dump(mode='json')for t in job._trial_configs],registration_sha256=sha(p)))
 async def started(event):
  path=Path(event.config.trials_dir)/event.trial_name;write(path/'ACTUAL_AGENT_START_R1.json',dict(at=time.time(),native_trial_uuid=str(event.trial_id),task_id=event.config.task.path.name,model=a['model']['model_id'],environment_manifest_sha256=a['environment_manifest_sha256']))
 async def environment_started(event):
  # Same immutable official image and original resource identity as actual NOP.
  path=Path(event.config.trials_dir)/event.trial_name;events=list(path.glob('remote-docker-*.jsonl'));assert len(events)==1;identity=events[0].stem.removeprefix('remote-docker-');import subprocess,json
  ids=subprocess.check_output(['docker','--host',native.D['task_engine']['native_endpoint'],'ps','-q','--filter','label=io.harbor.remote-docker.identity='+identity],text=True,timeout=15).split();assert len(ids)==1;actual=json.loads(subprocess.check_output(['docker','--host',native.D['task_engine']['native_endpoint'],'inspect',ids[0]],text=True,timeout=15))[0];prepared=next(x for x in manifest['tasks']if x['task_id']==event.config.task.path.name)['attempts'][-1]['actual_runtime'];assert actual['Image']==prepared['actual_image_id'];write(path/'ACCEPTED_ENVIRONMENT_IMAGE_R1.json',dict(at=time.time(),image_id=actual['Image'],prepared_image_id=prepared['actual_image_id'],identity=identity))
 def progress():
  rows=[]
  for p in job.job_dir.glob('*/result.json'):
   x=read(p);rows.append(dict(task_id=Path(x['config']['task']['path']).name,trial_id=x['id'],path=str(p),sha256=sha(p),reward=(x.get('verifier_result')or{}).get('rewards'),exception=(x.get('exception_info')or{}).get('exception_type'),agent_execution=x.get('agent_execution')))
  write(B/('CONTINUATION_PROGRESS_'+tag+'_R1.json'),dict(at=time.time(),expected=len(names),terminal=len(rows),actual_agent_starts=len(list(job.job_dir.glob('*/ACTUAL_AGENT_START_R1.json'))),rows=rows,native_job_id=str(job.id),full_recorder_audit_required=True))
 async def ended(event):progress()
 job.on_environment_started(environment_started);job.on_agent_started(started);job.on_trial_ended(ended);progress();await job.run();progress()
if __name__=='__main__':asyncio.run(main(sys.argv[1]))
