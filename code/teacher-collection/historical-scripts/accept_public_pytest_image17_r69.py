"""One exact public-library candidate, then native initial/CLI/official NOP."""
import asyncio
import datetime
import fcntl
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import toml
import tomllib
from uuid import uuid4

from harbor.models.job.config import RetryConfig
from harbor.trial.queue import TrialQueue
import collection_readiness_r9 as n
from collection_attempts_r8 import attempt_counts
from collection_selection_r7 import active_rows

S=n.R/'stream/public-pytest-image-native17-r69'
IDENT='task_007141_26892089'


async def main():
    S.mkdir(parents=True,exist_ok=True)
    lock=(S/'worker.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    if (S/'PLAN.json').exists():raise FileExistsError('Inspect existing candidate; no implicit replay')
    builder=n.R/'scripts/prepare_public_pytest_image17_r68.py'
    builder17='/home/chenkeyi/workspace/RSI/runtime-evidence/'+n.R.name+'/scripts/'+builder.name
    n.freeze(S/'PLAN.json',dict(tasks=[IDENT],source_sha256=n.sha(Path(__file__)),builder_sha256=n.sha(builder),
        node='17',engine_id=n.NODE['engine_id'],model_calls=0,teacher_dispatches=0,native_concurrency=1,
        active_controller_ready_publications=0))
    def state(stage):
        v=dict(pid=os.getpid(),checked_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
            current_task_id=IDENT,stage=stage,model_calls=0,teacher_dispatches=0)
        p=S/'state.tmp';p.write_text(json.dumps(v,indent=2));p.replace(S/'state.json')
    # The existing builder/preparer owns its slot until its native work ends.
    previous=n.R/'stream/original-initial-failure-build17-r58/TERMINAL.json'
    while not previous.exists():
        state('WAITING_FOR_EXISTING_R58_PREPARATION_SLOT_NATIVE_TERMINAL')
        await asyncio.sleep(20)
    terminal=json.loads(previous.read_text())
    if terminal['observed_tasks']!=4 or terminal['planned_tasks']!=4:raise ValueError('Prior bounded preparation incomplete')
    n.freeze(S/'SLOT_HANDOFF.json',dict(previous_terminal=str(previous),previous_terminal_sha256=n.sha(previous),
        teacher_or_verifier_signals=0,preparation_concurrency=1))
    if attempt_counts().get(IDENT,0):raise ValueError('Already attempted; preserve original identity')
    row=next(x for x in active_rows(attempt_counts()) if x['task_id']==IDENT)
    plan=json.loads((n.R/'manifests/TMAX_UNACCEPTED_ORIGINAL_ARCHIVES_R56.json').read_text())
    item=next(x for x in plan['tasks'] if x['task_id']==IDENT);path=Path(item['original_basic_receipt'])
    if n.sha(path)!=item['original_basic_receipt_sha256']:raise ValueError('Original source/image candidate changed')
    original=n.prepared(n.choose(row),(path,json.loads(path.read_text())))
    state('MATERIALIZING_EXACT_ORIGINAL_IMAGE_ON17')
    n.freeze(S/'original-image-materialization.json',await asyncio.to_thread(n.ensure_resident,original))
    subprocess.run(['rsync','-a','-e',shlex.join(n.DEPLOYMENT['ssh']),str(builder),n.DEPLOYMENT['host']+':'+builder17],check=True,timeout=120)
    state('ADDING_ONLY_HASH_LOCKED_PUBLIC_PYTEST_FILES_ON17')
    with (S/'public-image-build.log').open('x') as log:
        await asyncio.to_thread(subprocess.run,[*n.DEPLOYMENT['ssh'],n.DEPLOYMENT['host'],shlex.join([n.DEPLOYMENT['python17'],builder17])],check=True,stdout=log,stderr=subprocess.STDOUT,timeout=2400)
    remote=n.NODE['ssd_root']+'/public-pytest-image-r68/build.json';local=S/'build.json'
    subprocess.run(['rsync','-a','-e',shlex.join(n.DEPLOYMENT['ssh']),n.DEPLOYMENT['host']+':'+remote,str(local)],check=True,timeout=120)
    built=json.loads(local.read_text())
    if built['original_image_id']!=original['image_id'] or built['engine_id']!=n.NODE['engine_id'] or built['source_sha256']!=n.sha(builder):
        raise ValueError('Candidate source/Engine/base image changed')
    old=Path(original['prepared_task_path']);prepared=S/'prepared-task';shutil.copytree(old,prepared)
    config=tomllib.loads((old/'task.toml').read_text());config['environment']['docker_image']=built['image_id']
    (prepared/'task.toml').write_text(toml.dumps(config))
    for p in old.rglob('*'):
        if p.is_file() and p.relative_to(old)!=Path('task.toml') and n.sha(p)!=n.sha(prepared/p.relative_to(old)):
            raise ValueError('Original Task/test bytes changed')
    admitted=dict(original,prepared_task_path=str(prepared),prepared_task_toml_sha256=n.sha(prepared/'task.toml'),
        image_id=built['image_id'],original_published_image_id=original['image_id'])
    state('ORIGINAL_INITIAL_TEST_WITH_PUBLIC_PYTEST_ON17')
    n.freeze(S/'initial.json',await asyncio.to_thread(n.initial,admitted))
    queue=TrialQueue(n_concurrent=1,retry_config=RetryConfig(max_retries=0))
    out=dict(task_id=IDENT,pool='tmax',status='CANDIDATE_ENV_FAILED',admitted_task=admitted,
        original_image_id=original['image_id'],image_id=built['image_id'],build_receipt=str(local),build_receipt_sha256=n.sha(local),
        model_calls=0,teacher_dispatches=0,published_current_controller_ready=False)
    try:
        for kind in ['install','nop']:
            state('NATIVE_'+kind.upper()+'_ON17')
            cfg=n.native_config(admitted,kind);cfg.trials_dir=S/'trials'
            if kind=='install':cfg.agent.env={}
            network=S/'network.json';n.freeze(network,dict(networks=dict(default=dict(ipam=dict(config=[dict(subnet='10.249.228.0/28')])))))
            cfg.environment.extra_docker_compose=[network,*cfg.environment.extra_docker_compose[1:]]
            d=S/'dispatches'/str(uuid4());d.mkdir(parents=True);(d/'trial-config.json').write_text(cfg.model_dump_json(indent=2))
            n.freeze(d/'dispatch.json',dict(task_id=IDENT,pool='tmax',kind=kind,trial_name=cfg.trial_name,model_calls=0,config_sha256=n.sha(d/'trial-config.json')))
            result=await queue.submit(cfg);trial=S/'trials'/cfg.trial_name
            out['native_'+kind+'_trial']=str(trial);out[kind+'_result_sha256']=n.sha(trial/'result.json')
            n.freeze(S/'ssd-trial-archives'/(trial.name+'.json'),await asyncio.to_thread(n.archive_trial,trial))
            if result.exception_info or result.infrastructure_errors:raise ValueError('Native candidate lifecycle failure: '+str(result.exception_info))
            if kind=='nop':out['nop_reward']=n.verify_nop(result,trial,admitted)
        out['status']='CANDIDATE_ENV_READY_PENDING_IMAGE_BINDING_APPROVAL'
    except Exception as error:out.update(error_type=type(error).__name__,reason=str(error)[-1500:])
    n.freeze(S/'candidate-outcomes'/(IDENT+'.json'),out)
    state('PUBLIC_LIBRARY_IMAGE_NATIVE_ACCEPTANCE_TERMINAL')
    n.freeze(S/'TERMINAL.json',out)
    print(json.dumps(dict(task_id=IDENT,status=out['status'],reason=out.get('reason'))),flush=True)


if __name__=='__main__':
    os.environ['PATH']=str(n.R/'client-bin-v2')+':'+os.environ['PATH']
    for key in ['DEEPSEEK_API_KEY','OPENAI_API_KEY','GH_TOKEN']:os.environ.pop(key,None)
    asyncio.run(main())
