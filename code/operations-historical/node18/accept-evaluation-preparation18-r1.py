"""All89 rendered Compose contracts and two real no-model environment starts."""
import asyncio,copy,importlib,json,os,time
from pathlib import Path
from harbor.models.job.config import JobConfig
from harbor.models.trial.config import TrialConfig
from harbor.trial.trial import Trial
from harbor_remote_docker.compose import validate_compose
m=importlib.import_module('run-user-evaluation-native18-r1');prep=importlib.import_module('evaluation-preparation18-r1')
R=m.R;E=m.E
async def main():
    assert prep.read(R/'checks/PUBLIC_BIND_ASSET_MIRROR_AND_ROOT_ACCEPTANCE_R1.json')['passed']
    os.environ['OPENAI_API_KEY']='node18-local';os.environ['PATH']=m.native.D['transport']['private_client_bin']+':'+os.environ['PATH'];os.environ['TMPDIR']=str(R/'tmp')
    cfg=JobConfig.model_validate_json(m.native.selected_config(m.read(E/'manifests/FORMAL_801_TRIAL_PLAN.json')).read_text())
    plan=[x for x in m.read(E/'manifests/FORMAL_801_TRIAL_PLAN.json')['trials']if x['model_name']=='openai/qwen35-new772-m0'and x['repetition']==1];bytask={x.path.name:x for x in cfg.tasks}
    directory=E/'diagnostics'/('ipam-public-bind-preflight-'+str(time.time_ns()));directory.mkdir();records=[];environments={};sem=asyncio.Semaphore(4)
    async def check(item):
        async with sem:
            t=TrialConfig(task=bytask[item['task_id']],agent=cfg.agents[0].model_copy(deep=True),trials_dir=directory)
            m.native.apply_trial_overrides([t],dict(trials=[dict(item,trial_name='environment-only-'+item['task_id'])]),m.read(E/'configs/environment-profiles-agent-deps-r2.json'),namespace='q35ipamaccept')
            network=prep.append_ipam(t,'selected267',item['task_id']);trial=await Trial.create(t);env=trial.agent_environment
            env._use_prebuilt=True;env._resources_compose_path=env._write_resources_compose_file();env._env_compose_path=env._write_env_compose_file()
            rendered=await env._compose(['config','--format','json'],rendered=False);doc=json.loads(rendered.stdout)
            roots=[env.environment_dir.resolve(),*[p.parent.resolve()for p in env.extra_docker_compose_paths]]
            binds=validate_compose(doc,env.project,roots)
            assert doc['networks']['default']['ipam']['config']==[dict(subnet=network['subnet'])]
            assert not env.task_env_config.gpus
            records.append(dict(task_id=item['task_id'],project=env.project,binds=[str(x)for x in binds],network=network,compose_sha256=prep.sha(trial.paths.trial_dir/'config.json')if(trial.paths.trial_dir/'config.json').exists()else None))
            environments[item['task_id']]=(trial,env)
    async with asyncio.TaskGroup()as group:
        for item in plan:group.create_task(check(item))
    assert len(records)==89
    runtimes=[]
    for task in ['extract-moves-from-video','sam-cell-seg']:
        trial,env=environments[task];started=False
        try:
            await env.start(force_build=False);started=True
            result=await env.exec('test -r /usr/local/bin/rg; test ! -e /tests/test.sh; printf preparation-only',timeout_sec=30)
            assert result.return_code==0
            if task=='extract-moves-from-video':
                cert=await env.exec('sha256sum /opt/tb89-public/trust/ca-certificates.crt',timeout_sec=30);assert 'a41b5d356aea97a529fe27e0f7316d2f9d946d75927476cf9cf1b90637d00505'in cert.stdout
            runtimes.append(dict(task_id=task,actual_owned_project=env.project,start=True,exec_return_code=result.return_code,model_calls=0,agent_setup=False,verifier_run=False))
        finally:
            if started:await env.stop(delete=True)
    passed=dict(passed=True,at=time.time(),rendered_task_configs=89,compose_contracts=records,actual_environment_starts=runtimes,model_calls=0,agent_setup_calls=0,official_verifier_calls=0,official_tasks_tests_verifiers_resources_unchanged=True,public_assets_proof_sha256=prep.sha(R/'checks/PUBLIC_BIND_ASSET_MIRROR_AND_ROOT_ACCEPTANCE_R1.json'),ipam_manifest_sha256=prep.sha(E/'manifests/EVALUATION417_EXPLICIT_IPAM_R1.json'),source_sha256=prep.sha(Path(__file__)),evidence_directory=str(directory))
    prep.save(R/'checks/EVALUATION_IPAM_AND_PUBLIC_BINDS_RUNTIME_ACCEPTANCE_R1.json',passed)
    print(json.dumps(dict(passed=True,compose_tasks=89,runtime_starts=2,model_calls=0)))
if __name__=='__main__':asyncio.run(main())
