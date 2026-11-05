"""Freeze the preregistered14x8 old-protocol configurations; never dispatch."""
import copy
import hashlib
import json
from pathlib import Path
import tomllib
from harbor.models.job.config import JobConfig
from harbor.agents.installed.open_harness import OpenHarnessAgent

B=Path('/home/chenkeyi/.local/share/harbor-rsi')
NEW=B/'qwen35-new772-tb21-20261101'
R=B/'qwen35-old-m2-four-arm-20261101'
SOURCE=B/'qwen35-m1-m2-tb21-20261026/jobs/qwen35-m2-r1-20261026/config.json'
PREREG=NEW/'manifests/OLD_BEHAVIOR_PREREGISTRATION_ORIGINAL.json'
EXPECTED_WHEEL='f84f810e8a61545d685fb6722593886a0c88cc829b2ab9ca7c3476fe11e1209e'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,v):
    raw=json.dumps(v,ensure_ascii=False,indent=2)+'\n'
    if p.exists():
        if p.read_text()!=raw:raise ValueError('Preserve prior old112 freeze: '+str(p))
    else:p.write_text(raw)


def main():
    for name in ['configs','manifests','checks','scripts','jobs','logs','staging']:(R/name).mkdir(parents=True,exist_ok=True)
    (R/'staging').chmod(0o700)
    prereg=json.loads(PREREG.read_text());original=json.loads(SOURCE.read_text())
    tags=prereg['models'];selected=[r['task_id']for r in prereg['tasks']]
    if len(tags)!=14 or len(selected)!=8:raise ValueError('Old preregistered scope differs')
    taskmap={Path(t['path']).name:t for t in original['tasks']}
    allidentities=json.loads((NEW/'manifests/OFFICIAL_89_TASK_IDENTITIES.json').read_text())
    originaltasks={x['task_id']:x for x in allidentities['tasks']}
    tasks=[]
    for name in selected:
        row=taskmap[name];path=Path(row['path']);source=tomllib.loads((path/'task.toml').read_text())
        if sha(path/'task.toml')!=originaltasks[name]['task_toml_sha256']or sha(path/'instruction.md')!=originaltasks[name]['instruction_sha256']:
            raise ValueError('Original old-task identity differs: '+name)
        if not originaltasks[name]['image_present']:raise ValueError('Missing old-task image')
        tasks.append(dict(task_id=name,path=str(path),task_toml_sha256=sha(path/'task.toml'),
            instruction_sha256=sha(path/'instruction.md'),original_agent_timeout_sec=source['agent']['timeout_sec'],
            original_verifier=source['verifier'],original_environment=source['environment']))
    base=original['agents'][0];contract=base['kwargs']['config']
    if isinstance(contract,str):contract=json.loads(contract)if contract.lstrip().startswith('{')else json.loads(Path(contract).read_text())
    if set(contract['tools'])!=set(prereg['fixed_protocol']['tools'])or contract['finish']['enabled']:
        raise ValueError('Preserve historical10 tools and Finishoff')
    wheel=Path(base['kwargs']['wheel_path'])
    if sha(wheel)!=EXPECTED_WHEEL or base['kwargs']['wheel_sha256']!=EXPECTED_WHEEL:
        raise ValueError('Original old-protocol wheel changed')
    plan=[];configfiles={}
    for tag in tags:
        cfg=copy.deepcopy(original);agent=copy.deepcopy(base);config=copy.deepcopy(contract)
        model_id='qwen35-old-study-'+tag.lower()
        config['model'].update(id=model_id,name='Qwen3.5 old-study '+tag,baseUrl='http://172.17.0.1:18303/v1')
        config['model'].pop('apiKey',None)
        agent.update(model_name='openai/'+model_id,override_timeout_sec=None,max_timeout_sec=None,
            env={'OPENAI_API_KEY':'${OPENAI_API_KEY}'})
        agent['kwargs']['config']=config
        OpenHarnessAgent.preflight(agent['kwargs'],env={'OPENAI_API_KEY':'node18-local'})
        cfg.update(job_name='qwen35-old-four-'+tag.lower()+'-8tasks',jobs_dir=str(R/'jobs'),
            tasks=[taskmap[name]for name in selected],agents=[agent],n_attempts=1,n_concurrent_trials=2,
            timeout_multiplier=1.,agent_timeout_multiplier=None,verifier_timeout_multiplier=None,
            agent_setup_timeout_multiplier=None,environment_build_timeout_multiplier=None,quiet=True)
        cfg.setdefault('retry',{})['max_retries']=0
        cfg['environment'].update(force_build=False)
        cfg['environment']['kwargs'].update(staging_root=str(R/'staging'),project_namespace='q35old112'+tag.lower().replace('-',''))
        parsed=JobConfig.model_validate(cfg)
        if parsed.n_attempts!=1 or parsed.n_concurrent_trials!=2 or parsed.agents[0].override_timeout_sec is not None:
            raise ValueError('Native original-task timeout or single-trial scope changed')
        path=R/'configs'/(tag+'.json');save(path,parsed.model_dump(mode='json'));configfiles[tag]=dict(path=str(path),sha256=sha(path))
        for task in tasks:
            plan.append(dict(trial_name=task['task_id']+'__old-'+tag.lower()+'-n1',task_id=task['task_id'],
                model_tag=tag,model_id=model_id,model_name=agent['model_name'],task_path=task['path'],
                original_agent_timeout_sec=task['original_agent_timeout_sec'],sampling_seed=None,
                seed_pairing_claimed=False))
    if len(plan)!=112 or len({x['trial_name']for x in plan})!=112:raise ValueError('Old112 membership is not unique')
    save(R/'manifests/OLD112_NATIVE_DEPLOYMENT_PLAN_R1.json',dict(kind='OLD_M2_PREREGISTERED14_MODELS_8_TASKS',
        original_old_job_config_sha256=sha(SOURCE),original_behavior_preregistration_sha256=sha(PREREG),
        original_old_wheel_path=str(wheel),original_old_wheel_sha256=sha(wheel),
        configurations=configfiles,tasks=tasks,trials=plan,actual_trials_started=0,
        native_job_concurrency_per_model=2,models_execute_serially_with_independent_cold_start=True,
        original_task_agent_and_verifier_limits_unchanged=True,finish_off_historical_ten_tools=True,
        forbidden_before_new_formal801_completed=True,old_results_not_rewritten=True,
        source_sha256=sha(Path(__file__))))
    print(json.dumps(dict(passed=True,frozen_trials=112,models=14,tasks=8,actual_trials_started=0,
        original_wheel_sha256=EXPECTED_WHEEL,plan_sha256=sha(R/'manifests/OLD112_NATIVE_DEPLOYMENT_PLAN_R1.json'))))


if __name__=='__main__':main()
