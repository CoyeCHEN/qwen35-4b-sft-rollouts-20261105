"""Explicit published images or explicitly labelled original-recipe rebuilds."""
import importlib,json,os,urllib.request
from pathlib import Path
from harbor.models.trial.config import EnvironmentConfig,VerifierConfig,TaskConfig
base=importlib.import_module('synthetic32-native-config18-r2');R=base.R;B=base.B;E=base.E;C=base.C;native=base.native;read=base.read;write=base.write;sha=base.sha
def deployment():
 p=B/'SYNTHETIC32_DEPLOYMENT_R3.json';d=read(p);assert d['source_manifest_sha256']==sha(B/'FROZEN_USER_SYNTHETIC32_SOURCE_R2.json') and len(d['tasks'])==32;return d
def configuration(stage):
 frozen,cfg=base.configuration(stage);cfg.job_name='qwen35-user-synthetic32-'+stage+'-m1e3-n1-20261102-r4'
 if stage=='eval':
  mapping=read(B/'EVAL_TASK_IMAGE_BINDING_R4.json');assert mapping['environment_manifest_sha256']==sha(B/'ENV_PREFLIGHT_32_MANIFEST.json') and mapping['deployment_manifest_sha256']==sha(B/'SYNTHETIC32_DEPLOYMENT_R3.json');byid={x['task_id']:x for x in mapping['tasks']};assert len(byid)==17
  for index,t in enumerate(cfg.tasks):
   if t.path.name in byid:
    row=byid[t.path.name];path=Path(row['eval_task_path']);assert sha(path/'task.toml')==row['derived_eval_task_toml_sha256'];cfg.tasks[index]=TaskConfig(path=path)
 if stage=='prep':cfg.agents[0].import_path='env_preflight_synthetic32_agent_r3:OpenHarnessPreflightNopAgent'
 return frozen,cfg
def configure_trials(job,stage,frozen):
 d=deployment();byid={x['task_id']:x for x in d['tasks']};profiles=read(E/'configs/environment-profiles-agent-deps-r2.json');template=profiles['terminal-bench/regex-log'];ports=[];opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
 for port in [18303,18300,18309]:
  try:
   with opener.open('http://127.0.0.1:'+str(port)+'/model_info',timeout=2)as response:live=json.load(response)
   if live['weight_version']==frozen['model_manifest_sha256']and live['model_path']==str(R/'epoch-models/new-m1-epoch3'):ports.append(port)
  except OSError:pass
 assert ports,'No verified M1E3 service'
 if stage=='eval':write(B/'EVAL_SERVING_BINDING_R4.json',dict(ports=ports,weight_version=frozen['model_manifest_sha256'],model_path=str(R/'epoch-models/new-m1-epoch3'),deployment_manifest_sha256=sha(B/'SYNTHETIC32_DEPLOYMENT_R3.json')))
 original={x['task_id']:x for x in frozen['tasks']}
 for index,t in enumerate(job._trial_configs):
  item=byid[t.task.path.name];src=original[t.task.path.name];t.trial_name=t.task.path.name+'__synthetic32-'+stage+'-m1e3-r4';t.agent=t.agent.model_copy(deep=True);t.agent.override_timeout_sec=max(src['original_agent'].get('timeout_sec',0),10800)
  env=EnvironmentConfig.model_validate(template['environment']);env.extra_docker_compose=[E/'configs/agent-deps-r1.compose.json',Path(item['overlays'][stage]['path'])];env.force_build=item['force_build_by_stage'][stage];env.kwargs.update(endpoint=d['endpoint'],staging_root=native.D['task_engine']['staging_root'],transfer_timeout_sec=native.D['task_engine']['transfer_timeout_sec'],project_namespace='q35synth32'+stage+'r4');t.environment=env
  if stage=='eval' and item['mode']!='ORIGINAL_DOCKERFILE_UNIQUE_CONTEXT':
   accepted=read(B/'ENV_PREFLIGHT_32_MANIFEST.json');assert accepted['frozen'] and accepted['deployment_manifest_sha256']==sha(B/'SYNTHETIC32_DEPLOYMENT_R3.json')
   prior=next(x for x in accepted['tasks']if x['task_id']==item['task_id']);assert prior['status']=='PASS';image_id=prior['attempts'][-1]['actual_runtime']['actual_image_id']
   pin=dict(services=dict(main=dict(image=image_id)));path=B/'eval-image-pins-r4'/item['task_id']/'image.compose.json';path.parent.mkdir(parents=True,exist_ok=True)
   if path.exists():assert read(path)==pin
   else:write(path,pin)
   t.environment.extra_docker_compose.append(path)
  if stage=='eval' and item['mode']=='ORIGINAL_DOCKERFILE_UNIQUE_CONTEXT':
   mapping=read(B/'EVAL_TASK_IMAGE_BINDING_R4.json');row=next(x for x in mapping['tasks']if x['task_id']==item['task_id']);assert t.task.path==Path(row['eval_task_path']);t.environment.force_build=False;t.environment.extra_docker_compose=[E/'configs/agent-deps-r1.compose.json',Path(row['overlay']['path'])];assert sha(Path(row['overlay']['path']))==row['overlay']['sha256']
  t.verifier=VerifierConfig(env=template['verifier']['env']);t.agent.env.update(template['agent_env'])
  if stage=='eval':t.agent.kwargs['config']['model']['baseUrl']='http://172.17.0.1:'+str(ports[index%len(ports)])+'/v1'
  for overlay in item['overlays'].values():assert sha(Path(overlay['path']))==overlay['sha256']
 job._remaining_trial_configs=job._trial_configs
def make_specs(frozen,task_ids):
 d=deployment();byid={x['task_id']:x for x in d['tasks']};base=B/'env-runtime-r3';(base/'specs').mkdir(parents=True,exist_ok=True)
 for task in task_ids:
  original=read(B/'env-runtime/specs'/(task+'.json'));row=byid[task];spec=dict(original,deployment_manifest_sha256=sha(B/'SYNTHETIC32_DEPLOYMENT_R3.json'),image_identity_mode=row['mode'],expected_image_id=(row.get('expected_image_identity')or{}).get('image_id'),expected_private_image_tag=row.get('private_image_tag'),expected_base_rootfs=(row.get('base_image_identity')or{}).get('rootfs'),image_public_files=row.get('image_public_files',[]),original_recipe_sha256=row['recipe_sha256'])
  if task.startswith('fix-git'):spec['required_image_directories']=['/app/personal-site/.git']
  write(base/'specs'/(task+'.json'),spec)
