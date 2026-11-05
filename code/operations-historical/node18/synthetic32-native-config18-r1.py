"""Frozen synthetic32 native configs; task files and official-for-this-dataset tests intact."""
import hashlib,importlib,json,os,sys
from pathlib import Path
from harbor.models.job.config import JobConfig
from harbor.models.trial.config import TaskConfig,EnvironmentConfig,VerifierConfig
R=Path('/ssd/chenkeyi/qwen35-sft-772-20261101');B=R/'synthetic32';E=R/'formal-native-eval-r1';C=Path('/data/chenkeyi/qwen35-sft-772-20261101/control');sys.path[:0]=[str(R),str(E/'scripts')]
native=importlib.import_module('run-formal-native-tb2118-r2')
def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,v):
 t=p.with_name(p.name+'.tmp');t.write_text(json.dumps(v,indent=2)+'\n');t.replace(p)
def configuration(stage):
 frozen=read(B/'FROZEN_USER_SYNTHETIC32_SOURCE_R2.json');cfg=JobConfig.model_validate_json(native.selected_config(read(E/'manifests/FORMAL_801_TRIAL_PLAN.json')).read_text());cfg.tasks=[TaskConfig(path=Path(x['runtime_task_path']))for x in frozen['tasks']]
 agent=cfg.agents[1].model_copy(deep=True);agent.model_name='openai/qwen35-new772-new-m1-epoch3-fixed';agent.kwargs['config']['model'].update(id='qwen35-new772-new-m1-epoch3-fixed',name='Qwen3.5-4B NEW-M1 Epoch3 synthetic32',baseUrl='http://172.17.0.1:18303/v1')
 if stage=='prep':agent.name=None;agent.import_path='env_preflight_shared_agent_r2:OpenHarnessPreflightNopAgent'
 cfg.agents=[agent];cfg.n_attempts=1;cfg.retry.max_retries=0;cfg.n_concurrent_trials=2 if stage=='prep'else 8;cfg.job_name='qwen35-user-synthetic32-'+stage+'-m1e3-n1-20261102-r1';cfg.jobs_dir=B/'jobs'
 return frozen,cfg

def configure_trials(job,stage,frozen):
 byid={x['task_id']:x for x in frozen['tasks']};profiles=read(E/'configs/environment-profiles-agent-deps-r2.json');template=profiles['terminal-bench/regex-log']
 for index,t in enumerate(job._trial_configs):
  item=byid[t.task.path.name];t.trial_name=item['task_id']+'__synthetic32-'+stage+'-m1e3-r1';t.agent=t.agent.model_copy(deep=True);t.agent.override_timeout_sec=max(item['original_agent'].get('timeout_sec',0),10800)
  env=EnvironmentConfig.model_validate(template['environment']);env.extra_docker_compose=[E/'configs/agent-deps-r1.compose.json',Path(item['overlays'][stage]['path'])];env.kwargs.update(endpoint=native.D['task_engine']['native_endpoint'],staging_root=native.D['task_engine']['staging_root'],transfer_timeout_sec=native.D['task_engine']['transfer_timeout_sec'],project_namespace='q35synth32'+stage+'r1');t.environment=env
  t.verifier=VerifierConfig(env=template['verifier']['env']);t.agent.env.update(template['agent_env'])
  if stage=='eval':t.agent.kwargs['config']['model']['baseUrl']='http://172.17.0.1:'+str([18303,18309,18300,18301][index%4])+'/v1'
 job._remaining_trial_configs=job._trial_configs

def make_specs(frozen):
 base=B/'env-runtime';(base/'specs').mkdir(parents=True,exist_ok=True)
 rg=E/'configs/agent-deps/rg';assert rg.is_file()
 for item in frozen['tasks']:
  write(base/'specs'/(item['task_id']+'.json'),dict(task_id=item['task_id'],identity=item,expected_image_id=None,original_environment=item['original_environment'],engine_id=native.D['task_engine']['id'],public_files=[dict(source=str(rg),target='/usr/local/bin/rg',sha256=sha(rg),bytes=rg.stat().st_size)],model_endpoints=[dict(url='http://172.17.0.1:18303/model_info',model_path=str(R/'epoch-models/new-m1-epoch3'),weight_version=frozen['model_manifest_sha256'])],wheel_sha256='1d27eef1ca6696275f306d8c653f7a266a4c7aea7321f0d47fd01b739c27fa18'))
