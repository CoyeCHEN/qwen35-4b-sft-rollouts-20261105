"""Finite unmodified native initial/CLI/Verifier test of an SSH client candidate."""
import asyncio
import datetime
import fcntl
import json
import os
from pathlib import Path
import time
from uuid import uuid4

from harbor.models.job.config import RetryConfig
from harbor.trial.queue import TrialQueue
import collection_readiness_r13 as n
from collection_attempts_r8 import attempt_counts

S=n.R/'stream/native-ssh-pool-candidate17-r120'
IDENT='task_004361_0d2c270d'


def save(stage,**extra):
    value=dict(pid=os.getpid(),checked_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),stage=stage,
        task_id=IDENT,teacher_dispatches=0,model_calls=0,**extra)
    p=S/'state.pending';p.write_text(json.dumps(value,indent=2));p.replace(S/'state.json')


async def main():
    S.mkdir();lock=(S/'worker.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    pool=n.R/'checks/native-ssh-preseed-pool-r119.json';accepted=json.loads(pool.read_text())
    client=Path(accepted['native_client_bin'])/'ssh'
    if not accepted['passed'] or n.sha(client)!=accepted['native_client_sha256']:raise ValueError('Exact native SSH candidate changed')
    old=n.R/'stream/original-process-format-native17-r109/environment-outcomes'/(IDENT+'.json')
    prior=json.loads(old.read_text());row=n.choose(prior['admitted_task'])
    n.freeze(S/'PLAN.json',dict(tasks=[IDENT],engine_id=n.NODE['engine_id'],deployment_config_sha256=n.CONFIG_SHA,
        source_sha256=n.sha(Path(__file__)),native_client=str(client),native_client_sha256=n.sha(client),
        pool_acceptance=str(pool),pool_acceptance_sha256=n.sha(pool),prior_native_acceptance=str(old),prior_native_acceptance_sha256=n.sha(old),
        teacher_attempt_budget_at_registration=attempt_counts().get(IDENT,0),teacher_dispatches=0,model_calls=0,native_concurrency=1,
        original_task_test_image_resource_and_deadline_changes=0,ready_published=False))
    queue=TrialQueue(n_concurrent=1,retry_config=RetryConfig(max_retries=0))
    outcome=dict(task_id=IDENT,status='NATIVE_SSH_POOL_CANDIDATE_FAILED',native_results={},teacher_dispatches=0,model_calls=0,ready_published=False)
    try:
        save('EXACT_IMAGE_AND_ORIGINAL_INITIAL_TESTS_ON17')
        n.freeze(S/'image.json',await asyncio.to_thread(n.ensure_resident,row))
        n.freeze(S/'initial.json',await asyncio.to_thread(n.initial,row))
        network=S/'network.json';n.freeze(network,dict(networks=dict(default=dict(ipam=dict(config=[dict(subnet='10.249.248.0/28')])))))
        for kind in ['install','nop']:
            save('NATIVE_'+kind.upper()+'_ON17');cfg=n.native_config(row,kind);cfg.trials_dir=S/'trials'
            cfg.environment.extra_docker_compose=[network,*cfg.environment.extra_docker_compose[1:]]
            if kind=='install':cfg.agent.env={}
            directory=S/'dispatches'/uuid4().hex;directory.mkdir(parents=True)
            n.freeze(directory/'trial-config.json',cfg.model_dump(mode='json'))
            n.freeze(directory/'dispatch.json',dict(task_id=IDENT,kind=kind,trial_name=cfg.trial_name,config_sha256=n.sha(directory/'trial-config.json'),model_calls=0))
            begin=time.monotonic();result=await queue.submit(cfg);trial=S/'trials'/cfg.trial_name
            entry=dict(trial=str(trial),result_sha256=n.sha(trial/'result.json'),seconds=time.monotonic()-begin)
            outcome['native_results'][kind]=entry
            n.freeze(S/'ssd-trial-archives'/(trial.name+'.json'),await asyncio.to_thread(n.archive_trial,trial))
            if result.exception_info or result.infrastructure_errors:raise ValueError('Native lifecycle/infrastructure failure')
            if kind=='nop':entry['official_nop_reward']=n.verify_nop(result,trial,row)
        outcome.update(status='NATIVE_SSH_POOL_CANDIDATE_ACCEPTED',admitted_task=row,
            engine_id=n.NODE['engine_id'],native_client=str(client),native_client_sha256=n.sha(client),
            original_task_test_image_resource_and_deadline_changes=0,teacher_contract_or_prompt_changes=0)
    except Exception as error:outcome.update(error_type=type(error).__name__,reason=str(error)[-1600:])
    finally:
        n.freeze(S/'release.json',await asyncio.to_thread(n.release_cold_cache,row))
    n.freeze(S/'OUTCOME.json',outcome);save('FINITE_NATIVE_SSH_ACCEPTANCE_TERMINAL',outcome=outcome['status'])
    n.freeze(S/'TERMINAL.json',dict(outcome=outcome['status'],pid=os.getpid(),model_calls=0,teacher_dispatches=0))
    print(json.dumps(outcome),flush=True)


if __name__=='__main__':
    for key in ['DEEPSEEK_API_KEY','OPENAI_API_KEY','GH_TOKEN']:os.environ.pop(key,None)
    os.environ['PATH']=str(n.R/'client-bin-native-r119')+':'+str(n.R/'client-bin-v2')+':'+os.environ['PATH']
    asyncio.run(main())
