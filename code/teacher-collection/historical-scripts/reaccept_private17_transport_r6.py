"""Finite zero-model reacceptance after the proved SSH session-capacity fix."""
import asyncio
import fcntl
import hashlib
import json
import os
from pathlib import Path
from uuid import uuid4
from harbor.models.job.config import RetryConfig
from harbor.trial.queue import TrialQueue
import collection_readiness_r6 as n
import run_collection_stream_r4 as c

S=n.R/'stream/private17-transport-reacceptance-r6'


async def main():
    S.mkdir(parents=True,exist_ok=True)
    lock=(S/'worker.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    auth=n.R/'checks/native17-ssh-session-client-promotion-r6.json'
    assert json.loads(auth.read_text())['actual_engine_id']==n.NODE['engine_id']
    ids=['task_007016_4f9de434','task_009816_25751511']
    n.freeze(S/'PLAN.json',dict(task_ids=ids,source_sha256=n.sha(Path(__file__)),transport_acceptance=str(auth),
        transport_acceptance_sha256=n.sha(auth),native_concurrency=2,model_calls=0,teacher_dispatches=0))
    queue=TrialQueue(n_concurrent=2,retry_config=RetryConfig(max_retries=0))
    async def one(ident):
        out=dict(task_id=ident,pool='tmax',status='ENV_FAILED',model_calls=0)
        try:
            assert not c.attempt_counts()[ident]
            row=next(x for x in c.frozen_rows() if x['task_id']==ident)
            admitted=n.prepare_identity(row)
            material=await asyncio.to_thread(n.ensure_resident,admitted)
            n.freeze(S/'image-materializations'/(ident+'.json'),material)
            initial=await asyncio.to_thread(n.initial,admitted)
            n.freeze(S/'initial-outcomes'/(ident+'.json'),initial)
            for kind in ['install','nop']:
                cfg=n.native_config(admitted,kind);cfg.trials_dir=S/'trials'
                if kind=='install':cfg.agent.env={}
                d=S/'dispatches'/str(uuid4());d.mkdir(parents=True)
                (d/'trial-config.json').write_text(cfg.model_dump_json(indent=2))
                n.freeze(d/'dispatch.json',dict(task_id=ident,kind=kind,trial_name=cfg.trial_name,config_sha256=n.sha(d/'trial-config.json'),model_calls=0))
                result=await queue.submit(cfg);trial=S/'trials'/cfg.trial_name
                out['native_'+kind+'_trial']=str(trial);out[kind+'_result_sha256']=n.sha(trial/'result.json')
                if result.exception_info or result.infrastructure_errors:raise ValueError('Native '+kind+' failed: '+str(result.exception_info))
                if kind=='nop':out['nop_reward']=n.verify_nop(result,trial,admitted)
            out.update(status='ENV_READY',admitted_task=admitted,engine_id=n.NODE['engine_id'],deployment_config_sha256=n.CONFIG_SHA,
                placement=admitted['deployment_assignment'],placement_sha256=admitted['deployment_assignment_sha256'],
                prior_readiness=str(n.D/'environment-outcomes'/(ident+'.json')),prior_readiness_sha256=n.sha(n.D/'environment-outcomes'/(ident+'.json')),
                transport_acceptance=str(auth),transport_acceptance_sha256=n.sha(auth),teacher_success_not_implied=True)
            digest=hashlib.sha256(json.dumps(out,sort_keys=True).encode()).hexdigest()
            n.freeze(n.D/'ready-revisions'/ident/(digest+'.json'),out)
        except Exception as error:
            out.update(error_type=type(error).__name__,reason=str(error)[-2000:])
        n.freeze(S/'environment-outcomes'/(ident+'.json'),out)
        print(json.dumps(dict(task_id=ident,status=out['status'],reason=out.get('reason'))),flush=True)
    async with asyncio.TaskGroup() as group:
        for ident in ids:group.create_task(one(ident))


if __name__=='__main__':
    for key in ['DEEPSEEK_API_KEY','GH_TOKEN','OPENAI_API_KEY']:os.environ.pop(key,None)
    os.environ['PATH']=str(n.R/'client-bin-v2')+':'+os.environ['PATH']
    os.environ['SSH_AUTH_SOCK']='/home/chenkeyi/.local/share/harbor-rsi/near-r3-20261015/auth.sock'
    asyncio.run(main())
