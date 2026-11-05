"""Freeze one native Harbor campaign and explicit per-Trial research-timeout overrides."""
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import tomllib
from harbor.models.job.config import JobConfig
from harbor.agents.installed.open_harness import OpenHarnessAgent

B=Path('/home/chenkeyi/.local/share/harbor-rsi')
R=B/'qwen35-new772-tb21-20261101'
OLD=B/'qwen35-m1-m2-tb21-20261026'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,value):
    text=json.dumps(value,ensure_ascii=False,indent=2)+'\n'
    if p.exists():assert p.read_text()==text,'Frozen candidate already exists with another identity: '+str(p)
    else:p.write_text(text)


def main():
    for n in ['configs','manifests','checks','jobs','staging','scripts']:(R/n).mkdir(exist_ok=True)
    old=json.loads((OLD/'configs/m1-r2-r5.json').read_text())
    previous=json.loads((OLD/'manifests/eval-manifest-final.json').read_text())
    paths=[Path(x['path'])for x in old['tasks']]
    assert len(paths)==len(set(paths))==89
    frozen={Path(t['path']).name:t for t in previous['tasks']}
    tasks=[]
    for path in paths:
        assert sha(path/'task.toml')==frozen[path.name]['task_toml_sha256']
        assert sha(path/'instruction.md')==frozen[path.name]['instruction_sha256']
        cfg=tomllib.loads((path/'task.toml').read_text())
        test_files=[dict(path=str(p.relative_to(path)),sha256=sha(p),bytes=p.stat().st_size)
            for p in sorted((path/'tests').rglob('*'))if p.is_file()and '__pycache__'not in p.parts]
        image=cfg['environment']['docker_image']
        probe=subprocess.run(['docker','image','inspect',image,'--format','{{json .}}'],capture_output=True,text=True,timeout=15)
        value=json.loads(probe.stdout)if probe.returncode==0 else None
        tasks.append(dict(task_id=path.name,path=str(path),instruction_sha256=sha(path/'instruction.md'),
            task_toml_sha256=sha(path/'task.toml'),official_tests=test_files,official_tests_modified=False,
            original_agent_timeout_sec=cfg['agent']['timeout_sec'],
            effective_agent_timeout_sec=max(cfg['agent']['timeout_sec'],10800),
            original_verifier=cfg['verifier'],original_environment=cfg['environment'],
            image=image,image_present=bool(value),image_id=value['Id']if value else None,
            image_repo_digests=value.get('RepoDigests',[])if value else []))
    wheel=next((R/'wheels').glob('*.whl'))
    assert sha(wheel)=='3eaeafa4397d5a3284576b8b739a7f79f52311b724fdffc90e8b6f6ccc6e21b4'
    base=json.loads((R/'checks/ORIGINAL_TEACHER_11TOOLS_CONFIG.json').read_text())
    base.update(thinkingLevel='high',sessionDir='/logs/agent/openharness-sessions',
        recording=dict(enabled=True,directory='/logs/agent/openharness-rollout'),
        requestOptions=dict(maxTokens=81920,temperature=1.,timeout=120,topP=.95,topK=20,minP=0.,
            presencePenalty=1.5,repetitionPenalty=1.,chatTemplateKwargs={'enable_thinking':True}))
    for key in ['compaction','branchSummary']:base[key]['summaryThinkingLevel']='high'
    # Finish is registered by its native feature switch, separate from the ten base tools.
    assert base['finish']['enabled'] and base['toolResultBudget']['enabled']
    assert set(base['tools'])=={'read','bash','edit','write','grep','find','ls','edit_patch','trajectory_read','bash_job'}
    aliases=['m0','new-m1-e5','new-m2-e5'];ports=[18300,18301,18302]
    agents=[]
    for tag,port in zip(aliases,ports):
        agent=copy.deepcopy(old['agents'][0]);model_id='qwen35-new772-'+tag
        config=copy.deepcopy(base)
        config['model']=dict(id=model_id,name='Qwen3.5-4B frozen772 '+tag,api='openai-completions',
            provider='openai',baseUrl='http://172.17.0.1:'+str(port)+'/v1',reasoning=True,reasoningContent=True,
            input=['text','image'],thinkingLevelMap={'high':'high','max':'high'},contextWindow=262144,
            maxTokens=81920,cost=dict(input=0,output=0,cacheRead=0,cacheWrite=0))
        agent.update(model_name='openai/'+model_id,override_timeout_sec=None,max_timeout_sec=None,
            n_concurrent=None,concurrency_group=None,env={'OPENAI_API_KEY':'${OPENAI_API_KEY}'})
        agent['kwargs'].update(wheel_path=str(wheel),wheel_sha256=sha(wheel),config=config)
        OpenHarnessAgent.preflight(agent['kwargs'],env={'OPENAI_API_KEY':'node18-local'})
        agents.append(agent)
    config=copy.deepcopy(old)
    config.update(job_name='qwen35-new772-tb21-n3',jobs_dir=str(R/'jobs'),n_attempts=3,
        n_concurrent_trials=8,agents=agents,quiet=True,timeout_multiplier=1.,agent_timeout_multiplier=None,
        verifier_timeout_multiplier=None,agent_setup_timeout_multiplier=None,environment_build_timeout_multiplier=None)
    config['retry']['max_retries']=0
    config['environment']['kwargs'].update(staging_root=str(R/'staging'),project_namespace='q35new772n3')
    config['environment']['force_build']=False
    parsed=JobConfig.model_validate(config)
    plan=[]
    for repetition in range(1,4):
        for task in tasks:
            for tag,agent in zip(aliases,agents):
                plan.append(dict(trial_name=task['task_id']+'__'+tag+'-r'+str(repetition),
                    repetition=repetition,task_id=task['task_id'],task_path=task['path'],model_name=agent['model_name'],
                    agent_override_timeout_sec=task['effective_agent_timeout_sec'],
                    sampling_seed=None,seed_pairing_claimed=False))
    assert len(plan)==len(set(x['trial_name']for x in plan))==801
    save(R/'configs/formal-native-job.json',parsed.model_dump(mode='json'))
    save(R/'manifests/FORMAL_801_TRIAL_PLAN.json',dict(kind='FROZEN_NATIVE_HARBOR_801_TRIAL_PLAN',trials=plan,
        task_count=89,models=aliases,trials_per_model_task=3,sampling_seed_semantics='Unpaired native stochastic trials; no claim that service applies a seed',
        timeout_policy='Each native TrialConfig.agent.override_timeout_sec=max(original,10800); original task/verifier/resources unchanged',
        main_checkpoint='Epoch5 preselected; no score-based selection',diagnostic_epoch3_trials_excluded=True,
        config_sha256=sha(R/'configs/formal-native-job.json'),wheel_sha256=sha(wheel)))
    save(R/'manifests/OFFICIAL_89_TASK_IDENTITIES.json',dict(tasks=tasks,source_task_paths_preserved=True,
        all_images_present=all(t['image_present']for t in tasks),official_resources_unchanged=True,
        docker_engine_id=subprocess.check_output(['docker','info','--format','{{.ID}}'],text=True).strip(),
        historical_harbor_runtime=previous['harbor_runtime']))
    print(json.dumps(dict(frozen_trials=len(plan),tasks=len(tasks),images_present=sum(t['image_present']for t in tasks),
        longest_original_timeout=max(t['original_agent_timeout_sec']for t in tasks),
        trial_plan_sha256=sha(R/'manifests/FORMAL_801_TRIAL_PLAN.json'),actual_trials_started=0)))


if __name__=='__main__':main()
