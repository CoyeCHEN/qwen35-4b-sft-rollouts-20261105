"""One finite native original CLI/cache and official NOP recovery pass; no Teacher.

No Teacher admission, no model credentials, no Task replacement. New immutable
Ready evidence can supersede a setup block; every original failure is retained.
"""
import asyncio
from collections import Counter
import datetime
import fcntl
import json
import os
from pathlib import Path
from uuid import uuid4

from harbor.models.job.config import RetryConfig
from harbor.trial.queue import TrialQueue
from collection_attempts_r8 import attempt_counts
from collection_selection_r7 import active_rows
import collection_readiness_r21 as n
from cleanup_terminal_native_trial_r334 import cleanup

S = n.R / 'stream/public-cpython-native-setup-recovery17-r415'
OLD = n.R/'stream/collection-r4/deployment-r20'
REGISTRY_FILE=n.R/'checks/POST_NATIVE_CLEANUP_RECOVERY_SCOPE_R416.json'
if n.sha(REGISTRY_FILE)!='8e3020264ce35904daae1322962989784cd5d1625df464fae32b6b4c7126c67a':raise ValueError('Exact pre-Agent recovery scope changed')
REGISTRY=json.loads(REGISTRY_FILE.read_text())
NATIVE_PREPARATION_CONCURRENCY=2


def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def uncompleted(ident):
    for path in (n.R / 'stream/collection-r4/staging-dispatches').glob('*/setup.json'):
        value = json.loads(path.read_text())
        if value['task_id'] == ident and not (n.R / 'stream/collection-r4/trials' / value['trial_name'] / 'result.json').exists():
            return True
    return False


def plan():
    for proof in REGISTRY['terminal_cleanup'].values():
        if n.sha(Path(proof['path']))!=proof['sha256']:raise ValueError('Terminal cleanup proof changed')
        cleaned=json.loads(Path(proof['path']).read_text())
        if not cleaned['passed'] or any(cleaned['after'].values()):raise ValueError('Prior terminal namespace has not been cleaned')
    counts = attempt_counts()
    selected = {x['task_id']:x for x in active_rows(counts)}
    accepted=n.DEPLOYMENT['public_cli_bootstrap']
    if n.sha(Path(accepted['native_acceptance']))!=accepted['native_acceptance_sha256']:raise ValueError('Original setup prototype acceptance changed')
    admissions = {json.loads(line)['trial_name'] for line in (n.R / 'stream/collection-r4/teacher-lifecycle.jsonl').open()
                  if json.loads(line)['event'] == 'TEACHER_ADMITTED'}
    items = {}
    for path in sorted((OLD / 'setup-failures').glob('*.json')):
        value = json.loads(path.read_text())
        ident = value['task_id']
        if ident not in REGISTRY['cases']:continue
        case=REGISTRY['cases'][ident]
        if str(path)!=case['source_failure'] or n.sha(path)!=case['source_failure_sha256']:continue
        if value['native_result']!=case['native_result'] or n.sha(Path(value['native_result']))!=case['native_result_sha256']:raise ValueError('Pinned pre-Agent failure changed')
        result_path = Path(value['native_result'])
        result = json.loads(result_path.read_text())
        if result.get('agent_execution') or result_path.parent.name in admissions or (result_path.parent / 'agent/openharness-rollout/events.jsonl').exists():
            raise ValueError('Setup-only recovery contains Teacher/Recorder evidence')
        if not result.get('finished_at') or value.get('model_calls') != 0:
            raise ValueError('Original pre-Agent setup is not terminal')
        if selected[ident]['pool']!='tmax':raise ValueError('Exact recovery Task pool changed')
        if ident in items and items[ident]['failure_finished_at']>result['finished_at']:continue
        if counts.get(ident, 0) >= 2 or n.blocking_review(ident) or uncompleted(ident):
            continue
        items[ident] = dict(failure_finished_at=result['finished_at'], task_id=ident, pool=selected[ident]['pool'], source_failure=str(path),
            source_failure_sha256=n.sha(path), original_result=str(result_path), original_result_sha256=n.sha(result_path),
            existing_attempt_budget_used=counts.get(ident, 0), teacher_trials_unchanged=True)
    events=[json.loads(line) for line in (n.R/'stream/collection-r4/teacher-lifecycle.jsonl').open()]
    tasks=[]
    roots=n.readiness_roots()
    for item in items.values():
        failure=datetime.datetime.fromisoformat(json.loads(Path(item['original_result']).read_text())['finished_at'].replace('Z','+00:00'))
        ident=item['task_id']
        if any(e['event']=='TEACHER_ADMITTED' and e['task_id']==ident and datetime.datetime.fromisoformat(e['agent_admitted_at'])>failure for e in events):continue
        positive=False
        for root in roots:
            paths=[root/'environment-outcomes'/(ident+'.json'),*root.glob('ready-revisions/*/'+ident+'.json')]
            for path in paths:
                if not path.exists():continue
                value=json.loads(path.read_text())
                if value['status']=='ENV_READY' and datetime.datetime.fromisoformat(json.loads((Path(value['native_nop_trial'])/'result.json').read_text())['finished_at'].replace('Z','+00:00'))>failure:
                    positive=True
        if not positive:tasks.append(item)
    if not tasks or len(tasks)>2:raise ValueError('Unexpected finite setup-recheck scope')
    return dict(checked_at=now(), tasks=tasks, native_concurrency=NATIVE_PREPARATION_CONCURRENCY, model_calls=0, teacher_dispatches=0,
        source_sha256=n.sha(Path(__file__)), deployment_config_sha256=n.CONFIG_SHA,
        prototype_only=False,ready_publication='Validated new R21 receipt; original failures and the actual/conservative Teacher budget stay intact',cache_compose_sha256=n.sha(n.R/'configs/public-cpython-bootstrap-r273.compose.json'),cache_script_sha256=n.sha(n.R/'configs/public-cpython-bootstrap-r273.py'),provider_runtime_acceptance=str(n.R/'controller-runtime-r270/ACCEPTANCE.json'),provider_runtime_acceptance_sha256=n.sha(n.R/'controller-runtime-r270/ACCEPTANCE.json'),
        runtime_node='17', engine_id=n.NODE['engine_id'], original_failures_preserved=True,
        environment_passes_per_task_in_this_plan=1,exact_scope_sha256=n.sha(REGISTRY_FILE),resident_ready_images_retained_for_unique_controller=True, original_task_resources_and_verifier_timeouts=True)


async def main():
    import sys
    proof=json.loads((n.R/'controller-runtime-r270/ACCEPTANCE.json').read_text())
    if not proof['passed'] or sys.executable!=proof['interpreter']:
        raise ValueError('Prototype must use the isolated accepted native provider runtime')
    import harbor_remote_docker
    if not str(Path(harbor_remote_docker.__file__)).startswith(str(n.R/'controller-runtime-r270/venv')+'/'):
        raise ValueError('Prototype imported an old provider')
    S.mkdir(parents=True, exist_ok=True)
    lock = (S / 'worker.lock').open('a')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    if (S / 'PLAN.json').exists():
        raise FileExistsError('Inspect existing finite native pass; no implicit replay')
    frozen = plan()
    n.freeze(S / 'PLAN.json', frozen)
    queue = TrialQueue(n_concurrent=NATIVE_PREPARATION_CONCURRENCY, retry_config=RetryConfig(max_retries=0))
    terminal = {}
    active = {}
    semaphore=asyncio.Semaphore(NATIVE_PREPARATION_CONCURRENCY)

    def state(ident, stage):
        if ident is not None:
            if stage=='TASK_NATIVE_RECHECK_TERMINAL':active.pop(ident,None)
            else:active[ident]=stage
        value = dict(pid=os.getpid(), checked_at=now(), planned=len(frozen['tasks']), terminal=len(terminal),
            current_task_id=ident, stage=stage,active_task_stages=dict(active), native_concurrency=NATIVE_PREPARATION_CONCURRENCY, model_calls=0, teacher_dispatches=0,
            counts=dict(Counter(terminal.values())))
        temporary = S / 'state.pending'
        temporary.write_text(json.dumps(value, indent=2))
        temporary.replace(S / 'state.json')

    async def process(item):
        async with semaphore:
            ident = item['task_id']
            admitted = None
            out = dict(**item, status='ENV_FAILED', model_calls=0, teacher_dispatches=0,
                original_task_or_tests_modified=False, teacher_success_not_implied=True)
            try:
                for key in ['source_failure', 'original_result']:
                    if n.sha(Path(item[key])) != item[key + '_sha256']:
                        raise ValueError('Original pre-Agent failure identity changed')
                if uncompleted(ident):
                    out.update(status='EXISTING_NATIVE_TRIAL_PRESERVED', reason='No overlapping preparation for the same Task')
                    return
                counts = attempt_counts()
                if counts.get(ident, 0) != item['existing_attempt_budget_used']:
                    out.update(status='TASK_ADMISSION_CHANGED_PRESERVED', reason='Existing admission progressed; no recheck')
                    return
                row = next(x for x in active_rows(counts) if x['task_id'] == ident)
                n.freeze(S/'cleanup-recovery'/(ident+'.json'), await cleanup(Path(item['original_result']).parent, S/'native-cleanup'/ident))
                admitted = n.prepare_identity(row)
                state(ident, 'EXACT_ORIGINAL_IMAGE_AND_INITIAL_STATE_ON17')
                n.freeze(S / 'image-materializations' / (ident + '.json'), await asyncio.to_thread(n.ensure_resident, admitted))
                n.freeze(S / 'initial-outcomes' / (ident + '.json'), await asyncio.to_thread(n.initial, admitted))
                for kind in ['install', 'nop']:
                    state(ident, 'NATIVE_' + kind.upper() + '_ON17')
                    cfg = n.native_config(admitted, kind)
                    cfg.trials_dir = S / 'trials'
                    # Frozen R21 native_config attaches the accepted original public cache.
                    if kind == 'install':
                        cfg.agent.env = {}
                    directory = S / 'dispatches' / str(uuid4())
                    directory.mkdir(parents=True)
                    (directory / 'trial-config.json').write_text(cfg.model_dump_json(indent=2))
                    n.freeze(directory / 'dispatch.json', dict(task_id=ident, pool=row['pool'], kind=kind,
                        trial_name=cfg.trial_name, config_sha256=n.sha(directory / 'trial-config.json'),
                        model_calls=0, environment_recheck_only=True))
                    result = await queue.submit(cfg)
                    trial = S / 'trials' / cfg.trial_name
                    out['native_' + kind + '_trial'] = str(trial)
                    out[kind + '_result_sha256'] = n.sha(trial / 'result.json')
                    n.freeze(S / 'ssd-trial-archives' / (trial.name + '.json'), await asyncio.to_thread(n.archive_trial, trial))
                    if result.exception_info or result.infrastructure_errors:
                        raise ValueError('Native recheck lifecycle failed: ' + str(result.exception_info))
                    if kind == 'nop':
                        out['nop_reward'] = n.verify_nop(result, trial, admitted)
                if attempt_counts().get(ident, 0) != item['existing_attempt_budget_used']:
                    out.update(status='TASK_ADMISSION_CHANGED_PRESERVED', reason='No Ready publication after changed Teacher admission')
                    return
                out.update(status='ENV_READY', admitted_task=admitted, engine_id=n.NODE['engine_id'],
                    deployment_config_sha256=n.CONFIG_SHA, placement=admitted['deployment_assignment'],
                    placement_sha256=admitted['deployment_assignment_sha256'], source_sha256=frozen['source_sha256'])
            except Exception as error:
                out.update(error_type=type(error).__name__, reason=str(error)[-1800:])
            finally:
                path = S / 'environment-outcomes' / (ident + '.json')
                n.freeze(path, out)
                if out['status']=='ENV_READY':
                    n.freeze(n.D/'ready-revisions/public-cli-recovery-r415'/(ident+'.json'),out)
                if admitted is not None and out['status']!='ENV_READY':
                    try:
                        n.freeze(S / 'image-release' / (ident + '.json'), await asyncio.to_thread(n.release_cold_cache, admitted))
                    except Exception as error:
                        n.freeze(S / 'image-release-errors' / (ident + '.json'), dict(error_type=type(error).__name__, reason=str(error)[-800:]))
                terminal[ident] = out['status']
                state(ident, 'TASK_NATIVE_RECHECK_TERMINAL')
                print(json.dumps(dict(task_id=ident, status=out['status'], reason=out.get('reason'))), flush=True)
    await asyncio.gather(*(process(item) for item in frozen['tasks']))
    state(None, 'FINITE_NATIVE_RECHECK_TERMINAL')
    n.freeze(S / 'TERMINAL.json', json.loads((S / 'state.json').read_text()))


if __name__ == '__main__':
    os.environ['PATH'] = n.DEPLOYMENT['native_client_bin'] + ':' + str(n.R / 'client-bin-v2') + ':' + os.environ['PATH']
    os.environ['SSH_AUTH_SOCK'] = '/home/chenkeyi/.local/share/harbor-rsi/near-r3-20261015/auth.sock'
    for name in ['DEEPSEEK_API_KEY', 'OPENAI_API_KEY', 'GH_TOKEN']:
        os.environ.pop(name, None)
    asyncio.run(main())
