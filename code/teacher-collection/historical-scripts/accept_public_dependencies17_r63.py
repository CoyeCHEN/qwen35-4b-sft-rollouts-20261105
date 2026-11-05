"""Two bounded native initial/install/NOP checks; no teacher/model dispatch."""
import asyncio
import datetime
import fcntl
import hashlib
import json
import os
from pathlib import Path
from uuid import uuid4

from harbor.models.job.config import RetryConfig
from harbor.trial.queue import TrialQueue
import collection_readiness_r10 as n
from collection_attempts_r8 import attempt_counts
from collection_selection_r7 import active_rows

S = n.R / 'stream/public-dependency-native17-r63'
TASKS = ['task_007141_26892089', 'task_009221_2c5f3e9f']


async def main():
    S.mkdir(parents=True, exist_ok=True)
    lock = (S/'worker.lock').open('a')
    fcntl.flock(lock, fcntl.LOCK_EX|fcntl.LOCK_NB)
    if (S/'PLAN.json').exists():
        raise FileExistsError('Inspect previous native results; no implicit replay')
    n.freeze(S/'PLAN.json', dict(tasks=TASKS, source_sha256=n.sha(Path(__file__)),
        deployment_config=str(n.CONFIG), deployment_config_sha256=n.CONFIG_SHA,
        node='17', engine_id=n.NODE['engine_id'], native_concurrency=1,
        model_calls=0, teacher_dispatches=0, official_task_test_image_resource_deadline_changes=0))
    queue=TrialQueue(n_concurrent=1, retry_config=RetryConfig(max_retries=0))
    terminal={}
    def state(ident, stage):
        value=dict(pid=os.getpid(), checked_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
            current_task_id=ident, stage=stage, planned=len(TASKS), terminal=len(terminal),
            outcomes=terminal, native_concurrency=1, model_calls=0, teacher_dispatches=0)
        tmp=S/'state.tmp';tmp.write_text(json.dumps(value,indent=2));tmp.replace(S/'state.json')
    for index, ident in enumerate(TASKS):
        admitted=None
        out=dict(task_id=ident,pool='tmax',status='ENV_FAILED',model_calls=0,teacher_dispatches=0,
            original_task_or_tests_modified=False,teacher_success_not_implied=True)
        try:
            if attempt_counts().get(ident,0):
                raise ValueError('Already started; do not change a running Task binding')
            row=next(x for x in active_rows(attempt_counts()) if x['task_id']==ident)
            if ident=='task_007141_26892089':
                plan=json.loads((n.R/'manifests/TMAX_UNACCEPTED_ORIGINAL_ARCHIVES_R56.json').read_text())
                item=next(x for x in plan['tasks'] if x['task_id']==ident)
                path=Path(item['original_basic_receipt'])
                if n.sha(path)!=item['original_basic_receipt_sha256']:raise ValueError('Original image/source candidate changed')
                admitted=n.prepared(n.choose(row),(path,json.loads(path.read_text())))
            else:
                admitted=n.prepare_identity(row)
            state(ident,'ORIGINAL_IMAGE_INITIAL_RESOURCES_ON17')
            n.freeze(S/'image-materializations'/(ident+'.json'),await asyncio.to_thread(n.ensure_resident,admitted))
            n.freeze(S/'initial-outcomes'/(ident+'.json'),await asyncio.to_thread(n.initial,admitted))
            network=S/'networks'/(ident+'.json')
            n.freeze(network,dict(networks=dict(default=dict(ipam=dict(config=[dict(subnet='10.249.'+str(224+index)+'.0/28')])))))
            for kind in ['install','nop']:
                state(ident,'NATIVE_'+kind.upper()+'_ON17')
                cfg=n.native_config(admitted,kind);cfg.trials_dir=S/'trials'
                if kind=='install':cfg.agent.env={}
                cfg.environment.extra_docker_compose=[network,*cfg.environment.extra_docker_compose[1:]]
                d=S/'dispatches'/str(uuid4());d.mkdir(parents=True)
                (d/'trial-config.json').write_text(cfg.model_dump_json(indent=2))
                n.freeze(d/'dispatch.json',dict(task_id=ident,pool='tmax',kind=kind,trial_name=cfg.trial_name,
                    config_sha256=n.sha(d/'trial-config.json'),model_calls=0,environment_recheck_only=True))
                result=await queue.submit(cfg);trial=S/'trials'/cfg.trial_name
                out['native_'+kind+'_trial']=str(trial);out[kind+'_result_sha256']=n.sha(trial/'result.json')
                n.freeze(S/'ssd-trial-archives'/(trial.name+'.json'),await asyncio.to_thread(n.archive_trial,trial))
                if result.exception_info or result.infrastructure_errors:raise ValueError('Native lifecycle: '+str(result.exception_info))
                if kind=='nop':out['nop_reward']=n.verify_nop(result,trial,admitted)
            out.update(status='ENV_READY',admitted_task=admitted,engine_id=n.NODE['engine_id'],
                deployment_config_sha256=n.CONFIG_SHA,placement=admitted['deployment_assignment'],
                placement_sha256=n.sha(Path(admitted['deployment_assignment'])),source_sha256=n.sha(Path(__file__)))
        except Exception as error:
            out.update(error_type=type(error).__name__,reason=str(error)[-1800:])
        finally:
            if admitted:
                try:n.freeze(S/'image-release'/(ident+'.json'),await asyncio.to_thread(n.release_cold_cache,admitted))
                except Exception as error:n.freeze(S/'image-release-errors'/(ident+'.json'),dict(reason=str(error)[-800:]))
            path=S/'environment-outcomes'/(ident+'.json');n.freeze(path,out)
            if out['status']=='ENV_READY':
                ready=dict(out,raw_outcome=str(path),raw_outcome_sha256=n.sha(path))
                digest=hashlib.sha256(json.dumps(ready,sort_keys=True).encode()).hexdigest()
                n.freeze(n.D/'ready-revisions'/ident/(digest+'.json'),ready)
            terminal[ident]=out['status'];state(ident,'NATIVE_TASK_TERMINAL')
            print(json.dumps(dict(task_id=ident,status=out['status'],reason=out.get('reason'))),flush=True)
    state(None,'FINITE_NATIVE_ACCEPTANCE_TERMINAL')
    n.freeze(S/'TERMINAL.json',json.loads((S/'state.json').read_text()))


if __name__=='__main__':
    os.environ['PATH']=str(n.R/'client-bin-v2')+':'+os.environ['PATH']
    for key in ['DEEPSEEK_API_KEY','OPENAI_API_KEY','GH_TOKEN']:os.environ.pop(key,None)
    asyncio.run(main())
