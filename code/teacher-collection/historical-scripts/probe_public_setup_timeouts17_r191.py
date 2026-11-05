"""Finite native public-dependency diagnostics for two pre-Teacher timeouts."""
import asyncio
import datetime
import fcntl
import json
import os
from pathlib import Path
import shlex
import subprocess
import tomllib
from uuid import uuid4

from harbor.environments.factory import EnvironmentFactory
from harbor.models.task.config import TaskConfig
from harbor.models.trial.paths import TrialPaths
from collection_attempts_r8 import attempt_counts
from collection_selection_r7 import active_rows
import collection_readiness_r16 as n

S=n.R/'stream/public-setup-timeout-diagnostics17-r191'
IDS=['task_001587_0949d03f','data-processing_20260420_020307_002']


def state(task,stage):
    value=dict(pid=os.getpid(),task_id=task,stage=stage,checked_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        model_calls=0,official_verifier_runs=0,native_concurrency=1)
    tmp=S/'state.pending';tmp.write_text(json.dumps(value,indent=2));tmp.replace(S/'state.json')


async def main():
    S.mkdir(exist_ok=False)
    lock=(S/'worker.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    rows={row['task_id']:row for row in active_rows(attempt_counts())}
    if any(attempt_counts().get(ident,0) for ident in IDS):raise ValueError('Diagnostic restricted to unattempted Tasks')
    n.freeze(S/'PLAN.json',dict(tasks=IDS,model_calls=0,official_verifier_runs=0,source_sha256=n.sha(Path(__file__)),
        deployment_config_sha256=n.CONFIG_SHA,engine_id=n.NODE['engine_id'],task_resources_unchanged=True,
        scope='Exact original image, public package/bootstrap commands only. No private tests, reward generation, answers or solution repair.'))
    outcomes=[]
    for ordinal,ident in enumerate(IDS):
        directory=S/ident;directory.mkdir()
        env=None;admitted=None
        out=dict(task_id=ident,model_calls=0,official_verifier_runs=0,steps=[])
        try:
            if attempt_counts().get(ident,0):raise ValueError('Task has started; preserve it')
            admitted=n.prepare_identity(rows[ident]);state(ident,'EXACT_ORIGINAL_IMAGE')
            n.freeze(directory/'image.json',await asyncio.to_thread(n.ensure_resident,admitted))
            cfg=n.native_config(admitted,'install')
            network=directory/'network.json'
            n.freeze(network,dict(networks=dict(default=dict(ipam=dict(config=[dict(subnet='10.252.56.'+str(ordinal*16)+'/28')])))))
            cfg.environment.extra_docker_compose=[network,*cfg.environment.extra_docker_compose[1:]]
            cfg.environment.kwargs['project_namespace']='cftmaxpublicdiag191'
            task=Path(admitted['prepared_task_path'])
            task_config=TaskConfig.model_validate(tomllib.loads((task/'task.toml').read_text()))
            env=EnvironmentFactory.create_environment_from_config(config=cfg.environment,environment_dir=task/'environment',
                environment_name=ident,session_id=uuid4().hex,trial_paths=TrialPaths(trial_dir=directory),task_env_config=task_config.environment)
            n.freeze(directory/'environment.json',dict(identity=env.identity,environment=cfg.environment.model_dump(mode='json'),
                task_resources=task_config.environment.model_dump(mode='json')))
            await env.start(force_build=False)
            await env.exec('mkdir -p /logs/public-diagnostic',user='root',timeout_sec=20)
            if ident.startswith('task_'):
                uv=Path(cfg.agent.kwargs['bootstrap_uv_path'])
                assert n.sha(uv)==cfg.agent.kwargs['bootstrap_uv_sha256']
                await env.upload_file(uv,'/tmp/public-uv')
                command='chmod 755 /tmp/public-uv; /tmp/public-uv -vv venv --clear --managed-python --python 3.12.12 /tmp/public-probe-venv'
                steps=[('original_managed_python_bootstrap',command,180)]
            else:
                script=(task/'tests/test.sh').read_text()
                if script.count('\nuvx ')!=1:raise ValueError('Unexpected public bootstrap boundary')
                prefix=script.split('\nuvx ',1)[0]
                if any(x in prefix for x in ['reward.txt','test_outputs.py']):raise ValueError('No official test/Reward execution in diagnostic')
                steps=[('original_public_verifier_bootstrap',prefix,220),
                    ('original_public_pytest_dependencies','source "$HOME/.local/bin/env"; uvx -vv -p 3.13 -w pytest==8.4.1 -w pytest-json-ctrf==0.3.5 pytest --version',180)]
            for name,command,seconds in steps:
                state(ident,name)
                wrapped='timeout --kill-after=5s '+str(seconds)+'s bash -c '+shlex.quote(command)+' > /logs/public-diagnostic/'+name+'.txt 2>&1'
                result=await env.exec(wrapped,user='root',timeout_sec=seconds+30)
                log=directory/(name+'.txt')
                await env.download_file('/logs/public-diagnostic/'+name+'.txt',log)
                out['steps'].append(dict(name=name,return_code=result.return_code,log=str(log),sha256=n.sha(log),bytes=log.stat().st_size))
            out['status']='PUBLIC_DEPENDENCY_DIAGNOSTIC_COMPLETE_NOT_ENV_READY'
        except Exception as error:
            out.update(status='PUBLIC_DEPENDENCY_DIAGNOSTIC_FAILED',error_type=type(error).__name__,reason=str(error)[-800:])
        finally:
            if env is not None:
                try:await env.stop(delete=True);out['native_cleanup_complete']=True
                except Exception as error:out.update(native_cleanup_complete=False,cleanup_error=str(error)[-800:])
            n.freeze(directory/'PROBE.json',out);outcomes.append(out)
            if admitted is not None:
                try:n.freeze(directory/'image-release.json',await asyncio.to_thread(n.release_cold_cache,admitted))
                except Exception as error:n.freeze(directory/'image-release-error.json',dict(error=str(error)[-800:]))
    target=n.NODE['ssd_root']+'/public-setup-timeout-diagnostics-r191'
    subprocess.run([*n.DEPLOYMENT['ssh'],n.DEPLOYMENT['host'],'mkdir -p '+shlex.quote(target)],check=True,timeout=30)
    subprocess.run(['rsync','-a','-e',shlex.join(n.DEPLOYMENT['ssh']),str(S)+'/',n.DEPLOYMENT['host']+':'+target+'/'],check=True,timeout=180)
    n.freeze(S/'TERMINAL.json',dict(outcomes=outcomes,ssd_log_root=target,model_calls=0,official_verifier_runs=0))
    state(None,'FINITE_PUBLIC_DIAGNOSTIC_TERMINAL')


if __name__=='__main__':
    os.environ['PATH']=n.DEPLOYMENT['native_client_bin']+':'+str(n.R/'client-bin-v2')+':'+os.environ['PATH']
    os.environ['SSH_AUTH_SOCK']='/home/chenkeyi/.local/share/harbor-rsi/near-r3-20261015/auth.sock'
    for key in ['DEEPSEEK_API_KEY','OPENAI_API_KEY','GH_TOKEN']:os.environ.pop(key,None)
    asyncio.run(main())
