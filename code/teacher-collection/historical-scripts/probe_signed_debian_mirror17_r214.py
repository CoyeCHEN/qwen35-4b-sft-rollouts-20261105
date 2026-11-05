"""One native public-dependency diagnostic; original image and tests stay frozen."""
import asyncio
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
import collection_readiness_r17 as n

BASE=n.R/'stream/signed-debian-mirror-diagnostic17-r214'
S=BASE
IDENT=None
EXPECTED={'data-processing_20260420_020307_002':0,'video-processing_20260414_211532_001':1}


async def main():
    S.mkdir(exist_ok=False)
    if attempt_counts().get(IDENT,0)!=EXPECTED[IDENT]:raise ValueError('Preserve a Task whose Teacher admission changed')
    row=next(x for x in active_rows(attempt_counts()) if x['task_id']==IDENT)
    admitted=n.prepare_identity(row);environment=None
    out=dict(task_id=IDENT,model_calls=0,official_verifier_runs=0,ready_publication=False,
        status='SIGNED_DEBIAN_MIRROR_DIAGNOSTIC_FAILED',original_image=admitted['image_id'],sources=[],steps=[])
    n.freeze(S/'PLAN.json',dict(task_id=IDENT,source_sha256=n.sha(Path(__file__)),engine_id=n.NODE['engine_id'],
        deployment_config_sha256=n.CONFIG_SHA,model_calls=0,official_verifier_runs=0,native_concurrency=1,
        scope='Explicit TUNA mirror of the same signed Debian suites in disposable diagnostics; original trusted APT keyring/signature checks retained. No Task/test/Reward changes, answers, proxy or Ready publication.'))
    try:
        n.freeze(S/'image.json',await asyncio.to_thread(n.ensure_resident,admitted))
        cfg=n.native_config(admitted,'install');task=Path(admitted['prepared_task_path'])
        network=S/'network.json'
        n.freeze(network,dict(networks=dict(default=dict(ipam=dict(config=[dict(subnet='10.252.58.0/28')])))))
        cfg.environment.extra_docker_compose=[network,*cfg.environment.extra_docker_compose[1:]]
        cfg.environment.kwargs['project_namespace']='cftmaxpublicmirror214'
        resources=TaskConfig.model_validate(tomllib.loads((task/'task.toml').read_text())).environment
        environment=EnvironmentFactory.create_environment_from_config(config=cfg.environment,environment_dir=task/'environment',
            environment_name=IDENT,session_id=uuid4().hex,trial_paths=TrialPaths(trial_dir=S/'probe'),task_env_config=resources)
        n.freeze(S/'environment.json',dict(identity=environment.identity,environment=cfg.environment.model_dump(mode='json'),
            original_resources=resources.model_dump(mode='json')))
        await environment.start(force_build=False)
        listing="from pathlib import Path;import json;p=Path('/etc/apt');files=[p/'sources.list',*sorted((p/'sources.list.d').glob('*.sources')),*sorted((p/'sources.list.d').glob('*.list'))];print(json.dumps({str(f):f.read_text() for f in files if f.is_file()}))"
        result=await environment.exec(shlex.join(['python3','-c',listing]),user='root',timeout_sec=30)
        if result.return_code:raise ValueError('Original public APT configuration could not be read')
        source_files=json.loads(result.stdout)
        for ordinal,(path,original) in enumerate(source_files.items()):
            if not Path(path).is_relative_to('/etc/apt'):raise ValueError('Unexpected public setup path')
            updated=original
            for origin in ['http://deb.debian.org/','https://deb.debian.org/','http://security.debian.org/','https://security.debian.org/']:
                updated=updated.replace(origin,'https://mirrors.tuna.tsinghua.edu.cn/')
            if updated==original:continue
            before=S/('apt-original-'+str(ordinal));before.write_text(original)
            after=S/('apt-https-'+str(ordinal));after.write_text(updated)
            out['sources'].append(dict(container_path=path,original=str(before),original_sha256=n.sha(before),
                candidate=str(after),candidate_sha256=n.sha(after),change='Explicit TUNA HTTPS mirror; same signed Debian suites/components and original trusted keyring'))
            await environment.upload_file(after,path)
        if not out['sources']:raise ValueError('No official Debian HTTP source matched; no speculative changes')
        script=(task/'tests/test.sh').read_text()
        if script.count('\nuvx ')!=1:raise ValueError('Original public bootstrap boundary differs')
        prefix=script.split('\nuvx ',1)[0]
        uvx_line=script.split('\nuvx ',1)[1].split('\n\n',1)[0].replace('\\\n',' ')
        dependency_tokens=shlex.split('uvx '+uvx_line)
        pytest_index=dependency_tokens.index('pytest')
        public_version_command='source \"$HOME/.local/bin/env\"; '+shlex.join(dependency_tokens[:pytest_index+1]+['--version'])
        if 'reward.txt' in prefix or 'test_outputs.py' in prefix:raise ValueError('No test/Reward execution during public dependency diagnosis')
        await environment.exec('mkdir -p /logs/public-diagnostic',user='root',timeout_sec=20)
        verifier_env=n.native_config(admitted,'nop').verifier.env
        if any(key.lower().endswith('_proxy') for key in verifier_env):raise ValueError('No proxy in this direct HTTPS diagnostic')
        for name,command,seconds in [('original_public_bootstrap_over_https','set -e\n'+prefix,220),
            ('original_public_pytest_dependencies',public_version_command,180)]:
            wrapped='timeout --kill-after=5s '+str(seconds)+'s bash -c '+shlex.quote(command)+' > /logs/public-diagnostic/'+name+'.txt 2>&1'
            result=await environment.exec(wrapped,user='root',env=verifier_env,timeout_sec=seconds+30)
            log=S/(name+'.txt');await environment.download_file('/logs/public-diagnostic/'+name+'.txt',log)
            out['steps'].append(dict(name=name,return_code=result.return_code,log=str(log),sha256=n.sha(log),bytes=log.stat().st_size))
            if result.return_code:raise ValueError('Public dependency diagnostic failed at '+name)
        out['status']='SIGNED_DEBIAN_MIRROR_DIAGNOSTIC_PASSED_NATIVE_INSTALL_NOP_STILL_REQUIRED'
    except Exception as error:out.update(error_type=type(error).__name__,reason=str(error)[-1000:])
    finally:
        if environment is not None:
            try:await environment.stop(delete=True);out['native_cleanup_complete']=True
            except Exception as error:out.update(native_cleanup_complete=False,cleanup_error=str(error)[-800:])
        n.freeze(S/'TERMINAL.json',out)
        target=n.NODE['ssd_root']+'/signed-debian-mirror-diagnostic-r214/'+IDENT
        subprocess.run([*n.DEPLOYMENT['ssh'],n.DEPLOYMENT['host'],'mkdir -p '+shlex.quote(target)],check=True,timeout=30)
        subprocess.run(['rsync','-a','-e',shlex.join(n.DEPLOYMENT['ssh']),str(S)+'/',n.DEPLOYMENT['host']+':'+target+'/'],check=True,timeout=180)
        try:n.freeze(S/'image-release.json',await asyncio.to_thread(n.release_cold_cache,admitted))
        except Exception as error:n.freeze(S/'image-release-error.json',dict(reason=str(error)[-600:]))
    print(json.dumps(out),flush=True)


if __name__=='__main__':
    os.environ['PATH']=n.DEPLOYMENT['native_client_bin']+':'+str(n.R/'client-bin-v2')+':'+os.environ['PATH']
    os.environ['SSH_AUTH_SOCK']='/home/chenkeyi/.local/share/harbor-rsi/near-r3-20261015/auth.sock'
    for key in ['DEEPSEEK_API_KEY','OPENAI_API_KEY','GH_TOKEN']:os.environ.pop(key,None)
    async def run_finite_pair():
        global S,IDENT
        BASE.mkdir(exist_ok=False)
        deployment_snapshot=dict(tasks=EXPECTED,source_sha256=n.sha(Path(__file__)),engine_id=n.NODE['engine_id'],model_calls=0,official_verifier_runs=0,native_concurrency=1,public_reference=dict(original_and_mirror_bookworm_InRelease_sha256='77737fa4b34f2693e982cc9ee35736816c35a7778fc2d326cc1bbf5b301fe1aa',observed_on_node17=True),ready_publication=False)
        n.freeze(BASE/'PLAN.json',deployment_snapshot)
        outcomes=[]
        for ident in EXPECTED:
            IDENT=ident;S=BASE/ident
            await main()
            outcomes.append(json.loads((S/'TERMINAL.json').read_text()))
        n.freeze(BASE/'TERMINAL.json',dict(outcomes=outcomes,model_calls=0,official_verifier_runs=0,ready_publication=False))
    asyncio.run(run_finite_pair())
