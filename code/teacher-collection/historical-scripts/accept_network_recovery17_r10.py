"""Finite native17 acceptance of unchanged original network-failure recoveries."""
import asyncio
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shlex
import subprocess
from uuid import uuid4
from harbor.models.job.config import RetryConfig
from harbor.trial.queue import TrialQueue
import collection_readiness_r7 as n
from collection_selection_r7 import active_rows
import run_collection_stream_r4 as c
from accept_original_registry_recovery149_r9 import REMOTE as OLD_REGISTRATION

S=n.R/'stream/private17-original-network-acceptance-r10'
REMOTE=OLD_REGISTRATION.replace('registry-auth-recovery-r9','registry-head-pip-recovery-r10').replace('registry-auth-r9','registry-head-pip-r10')
REMOTE=REMOTE.replace(", 'original_build_log':(old.parent/'build.log').read_text()",'')


async def main():
    S.mkdir(parents=True,exist_ok=True)
    lock=(S/'worker.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    plan_name='/home/chenkeyi/workspace/RSI/runtime-evidence/qwen35-new-cf500-tmax500-20261029/manifests/TMAX_ORIGINAL_NETWORK_EOF_RECOVERY_R10.json'
    response=await asyncio.to_thread(subprocess.run,[*n.DEPLOYMENT['ssh'],n.DEPLOYMENT['host'],'cat '+shlex.quote(plan_name)],capture_output=True,text=True,check=True,timeout=30)
    plan=json.loads(response.stdout)
    n.freeze(S/'PLAN.json',dict(original_plan=plan,source_sha256=n.sha(Path(__file__)),node='17',engine_id=n.NODE['engine_id'],
        native_preparation_concurrency=2,teacher_dispatches=0,model_calls=0,original_contexts_and_tests_unchanged=True))
    queue=TrialQueue(n_concurrent=2,retry_config=RetryConfig(max_retries=0))
    pending={x['task_id']:x for x in plan['tasks']};running={};results={}
    async def accept(ident,built):
        out=dict(task_id=ident,pool='tmax',status='ENV_FAILED',node='17',model_calls=0)
        try:
            if c.attempt_counts()[ident]:raise ValueError('Already attempted Task retained; no automatic new original-context acceptance')
            row=next(x for x in active_rows(c.attempt_counts()) if x['task_id']==ident)
            receipt=S/'source-evidence'/ident/'build.json';n.freeze(receipt,built)
            source=Path(row['task_path'])
            if n.sha(source/'task.toml')!=built['source_context']['source_task_toml_sha256']:raise ValueError('Original converted Task resource configuration changed')
            admitted=n.prepared(n.choose(row),(receipt,dict(image_id=built['native_manifest_digest'])))
            n.freeze(S/'image-materializations'/(ident+'.json'),await asyncio.to_thread(n.ensure_resident,admitted))
            n.freeze(S/'initial-outcomes'/(ident+'.json'),await asyncio.to_thread(n.initial,admitted))
            for kind in ['install','nop']:
                cfg=n.native_config(admitted,kind);cfg.trials_dir=S/'trials'
                if kind=='install':cfg.agent.env={}
                d=S/'dispatches'/str(uuid4());d.mkdir(parents=True);(d/'trial-config.json').write_text(cfg.model_dump_json(indent=2))
                n.freeze(d/'dispatch.json',dict(task_id=ident,kind=kind,trial_name=cfg.trial_name,config_sha256=n.sha(d/'trial-config.json'),model_calls=0))
                result=await queue.submit(cfg);trial=S/'trials'/cfg.trial_name
                out['native_'+kind+'_trial']=str(trial);out[kind+'_result_sha256']=n.sha(trial/'result.json')
                if result.exception_info or result.infrastructure_errors:raise ValueError('Native17 '+kind+' lifecycle failed: '+str(result.exception_info))
                if kind=='nop':out['nop_reward']=n.verify_nop(result,trial,admitted)
            out.update(status='ENV_READY',admitted_task=admitted,engine_id=n.NODE['engine_id'],deployment_config_sha256=n.CONFIG_SHA,
                placement=admitted['deployment_assignment'],placement_sha256=admitted['deployment_assignment_sha256'],teacher_success_not_implied=True,
                original_recovery_build=str(receipt),original_recovery_build_sha256=n.sha(receipt),original_task_replaced=False)
            digest=hashlib.sha256(json.dumps(out,sort_keys=True).encode()).hexdigest()
            n.freeze(n.D/'ready-revisions'/ident/(digest+'.json'),out)
        except Exception as error:out.update(error_type=type(error).__name__,reason=str(error)[-2000:])
        n.freeze(S/'environment-outcomes'/(ident+'.json'),out);results[ident]=out['status']
        print(json.dumps(dict(task_id=ident,status=out['status'],reason=out.get('reason'))),flush=True)
    while pending or running:
        for ident,task in list(running.items()):
            if task.done():task.result();del running[ident]
        for ident in list(pending):
            if len(running)>=2:break
            command=shlex.join([n.DEPLOYMENT['python17'],'-c',REMOTE,ident])
            response=await asyncio.to_thread(subprocess.run,[*n.DEPLOYMENT['ssh'],n.DEPLOYMENT['host'],command],capture_output=True,text=True,timeout=90,check=True)
            value=json.loads(response.stdout)
            if value.get('pending'):continue
            del pending[ident]
            if value.get('failed'):
                n.freeze(S/'build-failures'/(ident+'.json'),value);results[ident]='ENV_FAILED_ORIGINAL_BUILD';continue
            n.freeze(S/'registrations'/(ident+'.json'),value['registration'])
            running[ident]=asyncio.create_task(accept(ident,value['build']))
        value=dict(pid=os.getpid(),planned_tasks=len(plan['tasks']),observed_tasks=len(results),counts={x:list(results.values()).count(x) for x in set(results.values())},active_tasks=list(running),node='17',model_calls=0,teacher_dispatches=0)
        temporary=S/'state.tmp';temporary.write_text(json.dumps(value,indent=2));temporary.replace(S/'state.json')
        if pending or running:await asyncio.sleep(15)


if __name__=='__main__':
    for key in ['DEEPSEEK_API_KEY','GH_TOKEN','OPENAI_API_KEY']:os.environ.pop(key,None)
    os.environ['PATH']=str(n.R/'client-bin-v2')+':'+os.environ['PATH']
    asyncio.run(main())
