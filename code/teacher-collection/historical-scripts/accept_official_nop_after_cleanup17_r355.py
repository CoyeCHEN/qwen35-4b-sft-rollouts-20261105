"""One original official NOP after exact cleanup; reuse the successful CLI install."""
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
from collection_selection_r7 import active_rows
from cleanup_terminal_native_trial_r354 import cleanup
import collection_readiness_r21 as n

IDENT = 'task_004229_60792e8f'
S = n.R / 'stream/official-nop-after-cleanup17-r355'
OLD = n.R / 'stream/public-cpython-native-setup-recovery17-r346'


async def main():
    S.mkdir(exist_ok=False)
    lock = (S / 'worker.lock').open('a')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    prior_path = OLD / 'environment-outcomes' / (IDENT + '.json')
    prior = json.loads(prior_path.read_text())
    if prior['status'] != 'ENV_FAILED' or prior['model_calls'] or attempt_counts().get(IDENT) != 1:
        raise ValueError('Preserve changed original environment failure or Teacher budget')
    installed = Path(prior['native_install_trial'])
    nop_failed = Path(prior['native_nop_trial'])
    for kind, trial in [('install', installed), ('nop', nop_failed)]:
        if n.sha(trial / 'result.json') != prior[kind + '_result_sha256']:
            raise ValueError('Original immutable native Result changed')
    install_result = json.loads((installed / 'result.json').read_text())
    failed = json.loads((nop_failed / 'result.json').read_text())
    if install_result['exception_info'] or install_result['infrastructure_errors'] or not install_result['finished_at']:
        raise ValueError('Original CLI installation was not accepted')
    if failed['failure_phase'] != 'cleanup' or not failed['verifier']['finished_at'] or failed['verifier_result']['rewards']['reward'] != 0:
        raise ValueError('Scope is not the observed completed NOP with cleanup failure')
    row = n.prepare_identity(next(x for x in active_rows(attempt_counts()) if x['task_id'] == IDENT))
    n.freeze(S / 'PLAN.json', dict(task_id=IDENT, admitted_task=row, source_sha256=n.sha(Path(__file__)),
        cleanup_helper_sha256=n.sha(Path(__file__).with_name('cleanup_terminal_native_trial_r354.py')),
        deployment_config_sha256=n.CONFIG_SHA, prior_outcome=str(prior_path), prior_outcome_sha256=n.sha(prior_path),
        original_successful_install=str(installed), original_install_result_sha256=prior['install_result_sha256'],
        original_failed_nop=str(nop_failed), original_failed_nop_result_sha256=prior['nop_result_sha256'],
        native_concurrency=1, model_calls=0, teacher_dispatches=0, teacher_attempt_budget_used=1,
        passes=1, original_task_resources_and_verifier_timeouts=True, original_results_not_rewritten=True))
    def state(stage):
        value = dict(stage=stage, checked_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
            pid=os.getpid(), task_id=IDENT, model_calls=0, teacher_dispatches=0)
        temp = S / 'state.pending'
        temp.write_text(json.dumps(value, indent=2))
        temp.replace(S / 'state.json')
    out = dict(task_id=IDENT, pool='tmax', status='ENV_FAILED', model_calls=0, teacher_dispatches=0,
        teacher_success_not_implied=True, original_failed_nop=str(nop_failed), original_failed_nop_result_sha256=prior['nop_result_sha256'],
        native_install_trial=str(installed), install_result_sha256=prior['install_result_sha256'])
    try:
        state('EXACT_NATIVE_ZERO_MODEL_SCOPE_CLEANUP')
        await cleanup(nop_failed, S / 'previous-nop-native-cleanup')
        n.freeze(S / 'image.json', await asyncio.to_thread(n.ensure_resident, row))
        state('ONE_ORIGINAL_OFFICIAL_NOP_ON17')
        cfg = n.native_config(row, 'nop')
        cfg.trials_dir = S / 'trials'
        directory = S / 'dispatches' / str(uuid4())
        directory.mkdir(parents=True)
        (directory / 'trial-config.json').write_text(cfg.model_dump_json(indent=2))
        n.freeze(directory / 'dispatch.json', dict(task_id=IDENT, kind='nop', trial_name=cfg.trial_name,
            config_sha256=n.sha(directory / 'trial-config.json'), model_calls=0))
        queue = TrialQueue(n_concurrent=1, retry_config=RetryConfig(max_retries=0))
        result = await queue.submit(cfg)
        trial = S / 'trials' / cfg.trial_name
        out.update(native_nop_trial=str(trial), nop_result_sha256=n.sha(trial / 'result.json'))
        n.freeze(S / 'ssd-trial-archive.json', await asyncio.to_thread(n.archive_trial, trial))
        if result.exception_info or result.infrastructure_errors:
            raise ValueError('New original official NOP lifecycle failed: ' + str(result.exception_info))
        reward = n.verify_nop(result, trial, row)
        if attempt_counts().get(IDENT) != 1:
            raise ValueError('Teacher admission changed during the isolated NOP')
        out.update(status='ENV_READY', nop_reward=reward, admitted_task=row, engine_id=n.NODE['engine_id'],
            deployment_config_sha256=n.CONFIG_SHA, placement=row['deployment_assignment'],
            placement_sha256=row['deployment_assignment_sha256'], prior_cleanup_recovery=str(S / 'previous-nop-native-cleanup/ACCEPTANCE.json'),
            prior_cleanup_recovery_sha256=n.sha(S / 'previous-nop-native-cleanup/ACCEPTANCE.json'))
    except Exception as error:
        out.update(error_type=type(error).__name__, reason=str(error)[-1800:])
    finally:
        n.freeze(S / 'environment-outcomes' / (IDENT + '.json'), out)
        if out['status'] == 'ENV_READY':
            n.freeze(n.D / 'ready-revisions/official-nop-after-cleanup-r355' / (IDENT + '.json'), out)
        try:
            n.freeze(S / 'image-release.json', await asyncio.to_thread(n.release_cold_cache, row))
        except Exception as error:
            n.freeze(S / 'image-release-error.json', dict(reason=str(error)[-600:]))
        state('FINITE_ORIGINAL_NOP_TERMINAL')
        n.freeze(S / 'TERMINAL.json', out)
    print(json.dumps(dict(status=out['status'], task_id=IDENT, reason=out.get('reason'), model_calls=0)))


if __name__ == '__main__':
    os.environ['PATH'] = n.DEPLOYMENT['native_client_bin'] + ':' + str(n.R / 'client-bin-v2') + ':' + os.environ['PATH']
    os.environ['SSH_AUTH_SOCK'] = '/home/chenkeyi/.local/share/harbor-rsi/near-r3-20261015/auth.sock'
    for key in ['DEEPSEEK_API_KEY', 'OPENAI_API_KEY', 'GH_TOKEN']:
        os.environ.pop(key, None)
    asyncio.run(main())
