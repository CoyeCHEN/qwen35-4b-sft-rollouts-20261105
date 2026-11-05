"""One fixed original-context registry EOF recovery on17, then native checks."""
import asyncio
import datetime
import fcntl
import json
import os
from pathlib import Path
import shlex
import subprocess
from uuid import uuid4

from harbor.models.job.config import RetryConfig
from harbor.trial.queue import TrialQueue
import collection_readiness_r12 as n
from collection_attempts_r8 import attempt_counts
from collection_selection_r7 import active_rows

S=n.R/'stream/original-registry-eof-native17-r88'
IDENT='task_007206_2ea22c7f'


def remote(code,request=None,timeout=180):
    reply=subprocess.run([*n.DEPLOYMENT['ssh'],n.DEPLOYMENT['host'],shlex.join([n.DEPLOYMENT['python17'],'-c',code])],
        input=json.dumps(request),check=True,capture_output=True,text=True,timeout=timeout)
    return json.loads(reply.stdout)


async def main():
    S.mkdir(parents=True,exist_ok=True)
    lock=(S/'worker.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    if (S/'PLAN.json').exists():raise FileExistsError('Observe existing original recovery; never replay implicitly')
    if attempt_counts().get(IDENT,0):raise ValueError('Already attempted; preserve image identity')
    row=next(x for x in active_rows(attempt_counts()) if x['task_id']==IDENT)
    builder=n.R/'scripts/build_original_registry_eof17_r87.py';builder17=str(Path(n.DEPLOYMENT['image_helper']).parent/builder.name)
    old=n.NODE['ssd_root']+'/buildkit-rootless-r2/archives/'+IDENT+'/client-proxy-r3/build.json'
    observe="import json,sys,hashlib;from pathlib import Path;v=json.load(sys.stdin);p=Path(v['path']);print(json.dumps({'value':json.loads(p.read_text()),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}))"
    prior=await asyncio.to_thread(remote,observe,dict(path=old))
    if prior['value']['status']!='NATIVE_SSD_BUILD_FAILED':raise ValueError('Preserve any completed original build')
    n.freeze(S/'original-failed-build.json',prior)
    source=prior['value']['source_context']
    n.freeze(S/'PLAN.json',dict(tasks=[IDENT],source_sha256=n.sha(Path(__file__)),builder_sha256=n.sha(builder),
        node='17',engine_id=n.NODE['engine_id'],original_failure_sha256=prior['sha256'],source_context=source,
        original_build_timeout_sec=600,actual_buildctl_timeout_sec=600,native_concurrency=1,model_calls=0,teacher_dispatches=0))
    def state(stage):
        p=S/'state.tmp';p.write_text(json.dumps(dict(pid=os.getpid(),checked_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
            current_task_id=IDENT,stage=stage,model_calls=0,teacher_dispatches=0),indent=2));p.replace(S/'state.json')
    subprocess.run(['rsync','-a','-e',shlex.join(n.DEPLOYMENT['ssh']),str(builder),n.DEPLOYMENT['host']+':'+builder17],check=True,timeout=120)
    state('UNCHANGED_ORIGINAL_CONTEXT_PRIVATE17_REGISTRY_RECOVERY')
    with (S/'native-build.log').open('x') as log:
        await asyncio.to_thread(subprocess.run,[*n.DEPLOYMENT['ssh'],n.DEPLOYMENT['host'],shlex.join([n.DEPLOYMENT['python17'],builder17,IDENT,source['source_manifest_sha256']])],
            check=True,stdout=log,stderr=subprocess.STDOUT,timeout=700)
    new=str(Path(old).parent.parent/'network-recovery-r5/build.json')
    built=await asyncio.to_thread(remote,observe,dict(path=new))
    if built['value']['status']!='ORIGINAL_NATIVE_OCI_ARCHIVE_BUILT_INITIAL_AND_VERIFIER_TESTS_PENDING' or built['value']['source_context']!=source:
        raise ValueError('Original-context recovery did not complete with identical inputs')
    register="import json,sys;from pathlib import Path;v=json.load(sys.stdin);p=Path(v.pop('path'));p.parent.mkdir(parents=True,exist_ok=True);assert not p.exists();p.write_text(json.dumps(v,indent=2));print(json.dumps({'registered':str(p)}))"
    registry=str(Path(n.DEPLOYMENT['image_helper']).parent.parent/'checks/tmax-original-build-network-recovery-r5'/ (IDENT+'.json'))
    binding=dict(path=registry,kind='EXPLICIT_ORIGINAL_CONTEXT_NETWORK_RECOVERY',task_id=IDENT,
        original_failed_build_sha256=prior['sha256'],recovery_build_receipt=new,recovery_build_receipt_sha256=built['sha256'])
    n.freeze(S/'archive-registration.json',await asyncio.to_thread(remote,register,binding))
    receipt=S/'build.json';n.freeze(receipt,built['value'])
    admitted=n.prepared(n.choose(row),(receipt,dict(image_id=built['value']['native_manifest_digest'])))
    state('ORIGINAL_IMAGE_INITIAL_RESOURCES_ON_PRIVATE17')
    n.freeze(S/'image-materialization.json',await asyncio.to_thread(n.ensure_resident,admitted))
    n.freeze(S/'initial.json',await asyncio.to_thread(n.initial,admitted))
    out=dict(task_id=IDENT,pool='tmax',status='ENV_FAILED',model_calls=0,teacher_dispatches=0,
        original_build_failure=str(S/'original-failed-build.json'),original_build_failure_sha256=n.sha(S/'original-failed-build.json'))
    queue=TrialQueue(n_concurrent=1,retry_config=RetryConfig(max_retries=0))
    try:
        network=S/'network.json';n.freeze(network,dict(networks=dict(default=dict(ipam=dict(config=[dict(subnet='10.249.252.0/28')])))))
        for kind in ['install','nop']:
            state('NATIVE_'+kind.upper()+'_ON17');cfg=n.native_config(admitted,kind);cfg.trials_dir=S/'trials'
            if kind=='install':cfg.agent.env={}
            cfg.environment.extra_docker_compose=[network,*cfg.environment.extra_docker_compose[1:]]
            d=S/'dispatches'/str(uuid4());d.mkdir(parents=True);(d/'trial-config.json').write_text(cfg.model_dump_json(indent=2))
            n.freeze(d/'dispatch.json',dict(task_id=IDENT,pool='tmax',kind=kind,trial_name=cfg.trial_name,config_sha256=n.sha(d/'trial-config.json'),model_calls=0))
            result=await queue.submit(cfg);trial=S/'trials'/cfg.trial_name
            out['native_'+kind+'_trial']=str(trial);out[kind+'_result_sha256']=n.sha(trial/'result.json')
            n.freeze(S/'ssd-trial-archives'/(trial.name+'.json'),await asyncio.to_thread(n.archive_trial,trial))
            if result.exception_info or result.infrastructure_errors:raise ValueError('Native lifecycle: '+str(result.exception_info))
            if kind=='nop':out['nop_reward']=n.verify_nop(result,trial,admitted)
        out.update(status='ENV_READY',admitted_task=admitted,engine_id=n.NODE['engine_id'],deployment_config_sha256=n.CONFIG_SHA,
            placement=admitted['deployment_assignment'],placement_sha256=n.sha(Path(admitted['deployment_assignment'])))
    except Exception as error:out.update(error_type=type(error).__name__,reason=str(error)[-1700:])
    path=S/'environment-outcomes'/(IDENT+'.json');n.freeze(path,out)
    if out['status']=='ENV_READY':
        import hashlib
        ready=dict(out,raw_outcome=str(path),raw_outcome_sha256=n.sha(path));digest=hashlib.sha256(json.dumps(ready,sort_keys=True).encode()).hexdigest()
        n.freeze(n.D/'ready-revisions'/IDENT/(digest+'.json'),ready)
    state('FINITE_REGISTRY_RECOVERY_NATIVE_TERMINAL');n.freeze(S/'TERMINAL.json',out)
    print(json.dumps(dict(task_id=IDENT,status=out['status'],reason=out.get('reason'))),flush=True)


if __name__=='__main__':
    os.environ['PATH']=str(n.R/'client-bin-v2')+':'+os.environ['PATH']
    for key in ['DEEPSEEK_API_KEY','OPENAI_API_KEY','GH_TOKEN']:os.environ.pop(key,None)
    try:
        asyncio.run(main())
    except Exception as error:
        state_path=S/'state.json'
        if state_path.exists() and json.loads(state_path.read_text()).get('pid')==os.getpid():
            failure=dict(task_id=IDENT,pool='tmax',status='ENV_FAILED',pid=os.getpid(),
                error_type=type(error).__name__,reason=str(error)[-1800:],model_calls=0,teacher_dispatches=0,
                raw_source_or_build_logs_preserved=True,failed_stage=json.loads(state_path.read_text())['stage'])
            n.freeze(S/'environment-outcomes'/(IDENT+'.json'),failure)
            n.freeze(S/'TERMINAL.json',failure)
        raise
