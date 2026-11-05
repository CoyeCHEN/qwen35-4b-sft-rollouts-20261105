"""Finite original-process startup translation and two unchanged native rechecks.

Only source-declared background processes are initialized. Original goal code,
tests, images, resource limits and deadlines stay unchanged. Runtime candidates
cannot publish Ready until their Campaign binding is separately approved.
"""
import asyncio
import datetime
import fcntl
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import shlex
import subprocess
import tomllib
from uuid import uuid4

from harbor.models.job.config import RetryConfig
from harbor.models.task.config import TaskConfig
from harbor.trial.queue import TrialQueue
import collection_readiness_r11 as n
from collection_attempts_r8 import attempt_counts
from collection_selection_r7 import active_rows

S=n.R/'stream/original-report-startup-native17-r78'
IDS=['task_004361_0d2c270d']


def startup(ident):
    source=n.R/'sources/tmax/original-tasks'/ident/'container.def'
    lines=source.read_text().splitlines()
    if ident=='task_004361_0d2c270d':
        if not all(s in source.read_text() for s in ['/home/user/.report_started','source /home/user/start_bg.sh','python3 report.py']):
            raise ValueError('Original deleted-process startup/marker contract changed')
        command='rm -f /home/user/.report_started\nsource /home/user/start_bg.sh'
        reason='Clear only the stale image-build process marker and invoke the original startup script. The original deleted report source/SQL remain unmodified.'
    else:return None
    return dict(command=['bash','-lc','cd /home/user\n'+command+'\nexec sleep infinity'],
        original_container_def=str(source),original_container_def_sha256=n.sha(source),reason=reason)


def initial(admitted,recipe):
    if recipe is None:return n.initial(admitted)
    original=n.R/'sources/tmax/original-tasks'/admitted['task_id']
    source=original/'test_initial_state.py'
    remote=n.NODE['ssd_root']+'/trusted-initial-r7/'+admitted['task_id']+'/test_initial_state.py'
    subprocess.run([*n.DEPLOYMENT['ssh'],n.DEPLOYMENT['host'],'mkdir -p '+shlex.quote(str(Path(remote).parent))],check=True,timeout=30)
    subprocess.run(['rsync','-a','-e',shlex.join(n.DEPLOYMENT['ssh']),str(source),n.DEPLOYMENT['host']+':'+remote],check=True,timeout=120)
    config=TaskConfig.model_validate(tomllib.loads((Path(admitted['task_path'])/'task.toml').read_text()))
    resources={key:getattr(config.environment,key) for key in ['cpus','memory_mb','storage_mb','gpus']}
    if resources['gpus']:raise ValueError('Unsupported original GPU requirement')
    helper=n.R/'scripts/campaign_image17_startup_readiness_r78.py'
    helper17=str(Path(n.DEPLOYMENT['image_helper']).parent/helper.name)
    request=dict(deployment=n.NODE,action='initial',row=admitted,helper_sha256=n.sha(helper),
        resources=resources,startup=recipe['command'],initial_test=dict(path=remote,sha256=n.sha(source)),
        startup_ready='pid1_sleep',workdir='/home/user',home='/home/user',initial_timeout=max(120,config.verifier.timeout_sec),probe_id=uuid4().hex)
    reply=subprocess.run([*n.DEPLOYMENT['ssh'],n.DEPLOYMENT['host'],shlex.join([n.DEPLOYMENT['python17'],helper17])],
        input=json.dumps(request),check=True,capture_output=True,text=True,timeout=1200)
    return json.loads(reply.stdout)



def prepare(row):
    ident=row['task_id']
    if ident in ['task_004361_0d2c270d']:
        plan=json.loads((n.R/'manifests/TMAX_UNATTEMPTED_INITIAL_FAILURE_CONTEXTS_R58.json').read_text())
        item=next(x for x in plan['tasks'] if x['task_id']==ident)
        old=Path(item['old_basic_receipt'])
        if n.sha(old)!=item['old_basic_receipt_sha256']:raise ValueError('Original failed source receipt changed')
        base=n.prepared(n.choose(row),(old,json.loads(old.read_text())))
        root=n.R/'stream/original-initial-failure-build17-r58'
        build=root/'build-receipts'/ident/'build.json';value=json.loads(build.read_text())
        task=root/'prepared-tasks'/ident
        expected=tomllib.loads((Path(base['prepared_task_path'])/'task.toml').read_text())
        expected['environment']['docker_image']=value['native_manifest_digest']
        if tomllib.loads((task/'task.toml').read_text())!=expected:raise ValueError('Original-context prepared image copy differs')
        for member in base['verifier_files']:
            if n.sha(task/member['path'])!=member['sha256']:raise ValueError('Official test bytes changed')
        return dict(base,prepared_task_path=str(task),prepared_task_toml_sha256=n.sha(task/'task.toml'),image_id=value['native_manifest_digest'],
            original_context_build=str(build),original_context_build_sha256=n.sha(build))
    return n.prepare_identity(row)


async def main():
    S.mkdir(parents=True,exist_ok=True)
    lock=(S/'worker.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    if (S/'PLAN.json').exists():raise FileExistsError('Inspect existing finite native acceptance; no replay')
    previous=n.R/'stream/original-runtime-process-native17-r71/TERMINAL.json'
    if not previous.exists():raise ValueError('The existing independent preparation slot is still busy')
    n.freeze(S/'PLAN.json',dict(tasks=IDS,source_sha256=n.sha(Path(__file__)),deployment_config_sha256=n.CONFIG_SHA,
        node='17',engine_id=n.NODE['engine_id'],native_concurrency=1,model_calls=0,teacher_dispatches=0,
        startup_helper_sha256=n.sha(n.R/'scripts/campaign_image17_startup_readiness_r78.py'),
        prior_preparation_terminal=str(previous),prior_preparation_terminal_sha256=n.sha(previous)))
    queue=TrialQueue(n_concurrent=1,retry_config=RetryConfig(max_retries=0));terminal={}
    def state(ident,stage):
        v=dict(pid=os.getpid(),checked_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),current_task_id=ident,
            stage=stage,planned=len(IDS),terminal=len(terminal),outcomes=terminal,model_calls=0,teacher_dispatches=0)
        tmp=S/'state.tmp';tmp.write_text(json.dumps(v,indent=2));tmp.replace(S/'state.json')
    for index,ident in enumerate(IDS):
        admitted=None;recipe=startup(ident)
        out=dict(task_id=ident,pool='tmax',status='ENV_FAILED',model_calls=0,teacher_dispatches=0,
            startup_translation=recipe,official_task_test_image_resource_deadline_changes=0,teacher_success_not_implied=True)
        try:
            if attempt_counts().get(ident,0):
                out.update(status='ALREADY_STARTED_TASK_PRESERVED');continue
            row=next(x for x in active_rows(attempt_counts()) if x['task_id']==ident);admitted=prepare(row)
            state(ident,'ORIGINAL_IMAGE_AND_INITIAL_STATE_ON17')
            n.freeze(S/'image-materializations'/(ident+'.json'),await asyncio.to_thread(n.ensure_resident,admitted))
            n.freeze(S/'initial-outcomes'/(ident+'.json'),await asyncio.to_thread(initial,admitted,recipe))
            override=None
            if recipe:
                override=S/'runtime-bindings'/(ident+'.json');n.freeze(override,dict(services=dict(main=dict(command=recipe['command'],healthcheck=dict(test=['CMD','bash','-c','read -r task_process < /proc/1/comm; test "$$task_process" = sleep'],interval='1s',timeout='2s',retries=120)))))
                out.update(runtime_compose=str(override),runtime_compose_sha256=n.sha(override))
            network=S/'networks'/(ident+'.json')
            subnet=str(ipaddress.ip_network((int(ipaddress.ip_address('10.249.244.0'))+16*index,28)))
            n.freeze(network,dict(networks=dict(default=dict(ipam=dict(config=[dict(subnet=subnet)])))))
            for kind in ['install','nop']:
                state(ident,'NATIVE_'+kind.upper()+'_ON17');cfg=n.native_config(admitted,kind);cfg.trials_dir=S/'trials'
                if kind=='install':cfg.agent.env={}
                cfg.environment.extra_docker_compose=[network,*cfg.environment.extra_docker_compose[1:]]
                if override:cfg.environment.extra_docker_compose.append(override)
                d=S/'dispatches'/str(uuid4());d.mkdir(parents=True);(d/'trial-config.json').write_text(cfg.model_dump_json(indent=2))
                n.freeze(d/'dispatch.json',dict(task_id=ident,pool='tmax',kind=kind,trial_name=cfg.trial_name,config_sha256=n.sha(d/'trial-config.json'),model_calls=0))
                result=await queue.submit(cfg);trial=S/'trials'/cfg.trial_name
                out['native_'+kind+'_trial']=str(trial);out[kind+'_result_sha256']=n.sha(trial/'result.json')
                n.freeze(S/'ssd-trial-archives'/(trial.name+'.json'),await asyncio.to_thread(n.archive_trial,trial))
                if result.exception_info or result.infrastructure_errors:raise ValueError('Native lifecycle: '+str(result.exception_info))
                if kind=='nop':out['nop_reward']=n.verify_nop(result,trial,admitted)
            out.update(status='CANDIDATE_ENV_READY_PENDING_RUNTIME_BINDING' if recipe else 'ENV_READY',admitted_task=admitted,
                engine_id=n.NODE['engine_id'],deployment_config_sha256=n.CONFIG_SHA,placement=admitted['deployment_assignment'],placement_sha256=n.sha(Path(admitted['deployment_assignment'])))
        except Exception as error:out.update(error_type=type(error).__name__,reason=str(error)[-1700:])
        finally:
            if admitted:
                try:n.freeze(S/'image-release'/(ident+'.json'),await asyncio.to_thread(n.release_cold_cache,admitted))
                except Exception as error:n.freeze(S/'image-release-errors'/(ident+'.json'),dict(reason=str(error)[-800:]))
            p=S/'environment-outcomes'/(ident+'.json');n.freeze(p,out)
            if out['status']=='ENV_READY':
                ready=dict(out,raw_outcome=str(p),raw_outcome_sha256=n.sha(p));digest=hashlib.sha256(json.dumps(ready,sort_keys=True).encode()).hexdigest()
                n.freeze(n.D/'ready-revisions'/ident/(digest+'.json'),ready)
            terminal[ident]=out['status'];state(ident,'NATIVE_TASK_TERMINAL')
            print(json.dumps(dict(task_id=ident,status=out['status'],reason=out.get('reason'))),flush=True)
    state(None,'FINITE_ORIGINAL_PROCESS_NATIVE_ACCEPTANCE_TERMINAL')
    n.freeze(S/'TERMINAL.json',json.loads((S/'state.json').read_text()))


if __name__=='__main__':
    os.environ['PATH']=str(n.R/'client-bin-v2')+':'+os.environ['PATH']
    for key in ['DEEPSEEK_API_KEY','OPENAI_API_KEY','GH_TOKEN']:os.environ.pop(key,None)
    asyncio.run(main())
