"""One zero-model original CLI/NOP acceptance; hold Teacher admission throughout."""
import asyncio
import datetime
import fcntl
import json
import os
from pathlib import Path
from uuid import uuid4

from harbor.models.job.config import RetryConfig
from harbor.trial.queue import TrialQueue
from collection_attempts_r8 import attempt_counts
import collection_readiness_r20 as old
import collection_readiness_r21 as n

IDENT = 'machine-learning_20260419_065313_002'
S = n.R / 'stream/signed-debian-native-acceptance17-r317'
BLOCK = n.R / 'checks/task-source-boundary-reviews-r7' / (IDENT + '.json')
BLOCK_SHA = '843e8962f68655677f1cdcaebd76092e1a622d07a06dc02026057d4e04f13820'


def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


async def main():
    S.mkdir(exist_ok=False)
    lock = (S / 'worker.lock').open('a'); fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    if attempt_counts().get(IDENT) != 1 or n.sha(BLOCK) != BLOCK_SHA:
        raise ValueError('Preserve changed Teacher admission or review identity')
    receipts = [p for root in old.readiness_roots() for p in [*sorted((root/'environment-outcomes').glob('*.json')), *sorted((root/'ready-revisions').glob('*/*.json'))] if p.stem == IDENT]
    accepted = [(path, old.normalize_ready(json.loads(path.read_text()), path)) for path in receipts if json.loads(path.read_text())['status'] == 'ENV_READY']
    if not accepted:
        raise ValueError('Original native acceptance missing')
    original, prior = accepted[-1]
    for kind in ['install', 'nop']:
        if n.sha(Path(prior['native_'+kind+'_trial'])/'result.json') != prior[kind+'_result_sha256']:
            raise ValueError('Original native acceptance Result changed')
    row = n.choose(prior['admitted_task'])
    task = Path(row['prepared_task_path'])
    if n.sha(task/'task.toml') != row['prepared_task_toml_sha256'] or n.sha(task/'instruction.md') != row['instruction_sha256']:
        raise ValueError('Frozen Task changed')
    for item in row['verifier_files']:
        if n.sha(task/item['path']) != item['sha256']:
            raise ValueError('Official verifier changed')
    n.freeze(S/'PLAN.json', dict(checked_at=now(), task_id=IDENT, admitted_task=row, source_sha256=n.sha(Path(__file__)), deployment_config_sha256=n.CONFIG_SHA, native_concurrency=1, model_calls=0, teacher_attempt_budget_used=1, admission_block=str(BLOCK), admission_block_sha256=BLOCK_SHA, previous_ready=str(original), previous_ready_sha256=n.sha(original), teacher_success_not_implied=True))
    def state(stage):
        value=dict(checked_at=now(), pid=os.getpid(), stage=stage, task_id=IDENT, model_calls=0, teacher_dispatches=0, original_teacher_admission_still_blocked=True)
        temp=S/'state.pending';temp.write_text(json.dumps(value,indent=2));temp.replace(S/'state.json')
    out = dict(task_id=IDENT, pool='calibforge', status='ENV_FAILED', model_calls=0, teacher_dispatches=0, teacher_success_not_implied=True)
    try:
        state('ORIGINAL_IMAGE_AND_INITIAL_STATE')
        n.freeze(S/'image.json', await asyncio.to_thread(n.ensure_resident,row))
        n.freeze(S/'initial.json', await asyncio.to_thread(n.initial,row))
        queue=TrialQueue(n_concurrent=1,retry_config=RetryConfig(max_retries=0))
        for kind in ['install','nop']:
            state('NATIVE_'+kind.upper())
            cfg=n.native_config(row,kind);cfg.trials_dir=S/'trials'
            if kind=='install':cfg.agent.env={}
            directory=S/'dispatches'/str(uuid4());directory.mkdir(parents=True)
            config=directory/'trial-config.json';config.write_text(cfg.model_dump_json(indent=2))
            n.freeze(directory/'dispatch.json',dict(task_id=IDENT,kind=kind,trial_name=cfg.trial_name,config_sha256=n.sha(config),model_calls=0))
            result=await queue.submit(cfg);trial=S/'trials'/cfg.trial_name
            out['native_'+kind+'_trial']=str(trial);out[kind+'_result_sha256']=n.sha(trial/'result.json')
            n.freeze(S/'ssd-trial-archives'/(trial.name+'.json'),await asyncio.to_thread(n.archive_trial,trial))
            if result.exception_info or result.infrastructure_errors:
                raise ValueError('Original native lifecycle failed: '+str(result.exception_info))
            if kind=='nop':out['nop_reward']=n.verify_nop(result,trial,row)
        if attempt_counts().get(IDENT)!=1 or n.sha(BLOCK)!=BLOCK_SHA:
            raise ValueError('Teacher admission or block changed during native check')
        out.update(status='ENV_READY',admitted_task=row,engine_id=n.NODE['engine_id'],deployment_config_sha256=n.CONFIG_SHA,placement=row['deployment_assignment'],placement_sha256=row['deployment_assignment_sha256'],teacher_admission_release_still_requires_r21=True)
    except Exception as error:
        out.update(error_type=type(error).__name__,reason=str(error)[-1800:])
    finally:
        path=S/'environment-outcomes'/(IDENT+'.json');n.freeze(path,out)
        if out['status']=='ENV_READY':n.freeze(n.D/'ready-revisions/signed-debian-r317'/(IDENT+'.json'),out)
        try:n.freeze(S/'image-release.json',await asyncio.to_thread(n.release_cold_cache,row))
        except Exception as error:n.freeze(S/'image-release-error.json',dict(reason=str(error)[-600:]))
        state('FINITE_NATIVE_ACCEPTANCE_TERMINAL');n.freeze(S/'TERMINAL.json',out)
    print(json.dumps(dict(status=out['status'],reason=out.get('reason'),nop_reward=out.get('nop_reward'),teacher_admission_released=False)),flush=True)


if __name__ == '__main__':
    os.environ['PATH']=n.DEPLOYMENT['native_client_bin']+':'+str(n.R/'client-bin-v2')+':'+os.environ['PATH']
    os.environ['SSH_AUTH_SOCK']='/home/chenkeyi/.local/share/harbor-rsi/near-r3-20261015/auth.sock'
    for key in ['DEEPSEEK_API_KEY','OPENAI_API_KEY','GH_TOKEN']:os.environ.pop(key,None)
    asyncio.run(main())
