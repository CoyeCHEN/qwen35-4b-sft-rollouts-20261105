"""Recheck exact original archives that arrived after earlier cold-image failures.

Keep original failures and all research inputs. Use existing RemoteDocker and
TrialQueue, original deadlines/resources, one additional preparation slot.
"""
import asyncio
import datetime
import fcntl
import hashlib
import ipaddress
import json
import os
from pathlib import Path
from uuid import uuid4

from harbor.models.job.config import RetryConfig
from harbor.trial.queue import TrialQueue
import collection_readiness_r7 as n
from collection_attempts_r8 import attempt_counts
from collection_selection_r7 import active_rows

S = n.R / 'stream/native-exact-archive-recheck17-r29'
def plan():
    path=n.R/'manifests/TMAX_READY_ORIGINAL_ARCHIVES_RECHECK_R29.json'
    value=json.loads(path.read_text())
    if value['runtime_engine_id']!=n.NODE['engine_id'] or value['deployment_config_sha256']!=n.CONFIG_SHA:
        raise ValueError('Exact archive recovery belongs to another deployment')
    if not value['tasks'] or len(value['tasks'])>50:
        raise ValueError('Unexpected finite original-archive recovery scope')
    return dict(tasks=value['tasks'],source_plan=str(path),source_plan_sha256=n.sha(path),
        source_sha256=n.sha(Path(__file__)),native_concurrency=1,native_retry_max=0,
        node='17',engine_id=n.NODE['engine_id'],model_calls=0,teacher_dispatches=0,
        image_rebuilds=0,image_identity_changes=0,official_task_or_test_changes=0,
        reason='Earlier exact-image failures are preserved; original archived images are now on17. Repeat only zero-model native acceptance, never an existing teacher Trial.')


def qualified_tasks():
    path=n.R/'indexes/TMAX_SUCCESS_INDEX.jsonl'
    return {x['task_id'] for x in map(json.loads,path.open())} if path.exists() else set()


async def main():
    S.mkdir(parents=True, exist_ok=True)
    lock = (S / 'worker.lock').open('a')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    if (S / 'PLAN.json').exists():
        raise FileExistsError('Inspect the preserved native recovery; never replay automatically')
    frozen = plan()
    n.freeze(S / 'PLAN.json', frozen)
    queue = TrialQueue(n_concurrent=1, retry_config=RetryConfig(max_retries=0))
    terminal = {}

    def state(ident, stage):
        value = dict(pid=os.getpid(), checked_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
            planned=len(frozen['tasks']), terminal=len(terminal), current_task_id=ident, stage=stage,
            native_concurrency=1, model_calls=0, teacher_dispatches=0,
            counts={status:list(terminal.values()).count(status) for status in set(terminal.values())})
        tmp = S / 'state.tmp'
        tmp.write_text(json.dumps(value, indent=2))
        tmp.replace(S / 'state.json')

    for index, item in enumerate(frozen['tasks']):
        ident = item['task_id']
        out = dict(task_id=ident, pool=item['pool'], status='ENV_FAILED',
            model_calls=0, teacher_dispatches=0, original_failure=item,
            original_task_or_tests_modified=False, teacher_success_not_implied=True)
        admitted = None
        try:
            if attempt_counts().get(ident,0)>=2 or ident in qualified_tasks():
                out.update(status='ALREADY_QUALIFIED_OR_ATTEMPT_CAPPED_TASK_PRESERVED',reason='No teacher replay and no image identity change')
                continue
            for key in ['original_failure', 'original_basic_receipt']:
                if n.sha(Path(item[key])) != item[key + '_sha256']:
                    raise ValueError('Original native failure changed')
            row = next(x for x in active_rows(attempt_counts()) if x['task_id'] == ident)
            admitted = n.prepare_identity(row)
            if admitted['image_id']!=item['image_id'] or admitted['prepared_task_toml_sha256']!=item['prepared_task_toml_sha256']:
                raise ValueError('Original prepared Task/image identity changed')
            state(ident, 'EXACT_ORIGINAL_IMAGE_AND_INITIAL_STATE_ON17')
            n.freeze(S / 'image-materializations' / (ident + '.json'), await asyncio.to_thread(n.ensure_resident, admitted))
            n.freeze(S / 'initial-outcomes' / (ident + '.json'), await asyncio.to_thread(n.initial, admitted))
            subnet = str(ipaddress.ip_network((int(ipaddress.ip_address('10.246.0.0')) + index * 16, 28)))
            network = S / 'networks' / (ident + '.json')
            n.freeze(network, dict(networks=dict(default=dict(ipam=dict(config=[dict(subnet=subnet)])))))
            for kind in ['install', 'nop']:
                state(ident, 'NATIVE_' + kind.upper() + '_ON17')
                cfg = n.native_config(admitted, kind)
                cfg.trials_dir = S / 'trials'
                if kind == 'install':
                    cfg.agent.env = {}
                cfg.environment.extra_docker_compose = [network, *cfg.environment.extra_docker_compose[1:]]
                dispatch_dir = S / 'dispatches' / str(uuid4())
                dispatch_dir.mkdir(parents=True)
                (dispatch_dir / 'trial-config.json').write_text(cfg.model_dump_json(indent=2))
                n.freeze(dispatch_dir / 'dispatch.json', dict(task_id=ident, pool=row['pool'], kind=kind,
                    trial_name=cfg.trial_name, config_sha256=n.sha(dispatch_dir / 'trial-config.json'),
                    model_calls=0, environment_recheck_only=True, precheck_only_subnet=subnet))
                result = await queue.submit(cfg)
                trial = S / 'trials' / cfg.trial_name
                out['native_' + kind + '_trial'] = str(trial)
                out[kind + '_result_sha256'] = n.sha(trial / 'result.json')
                n.freeze(S / 'ssd-trial-archives' / (trial.name + '.json'), await asyncio.to_thread(n.archive_trial, trial))
                if result.exception_info or result.infrastructure_errors:
                    raise ValueError('Native recheck lifecycle failed: ' + str(result.exception_info))
                if kind == 'nop':
                    out['nop_reward'] = n.verify_nop(result, trial, admitted)
            out.update(status='ENV_READY', admitted_task=admitted, engine_id=n.NODE['engine_id'],
                deployment_config_sha256=n.CONFIG_SHA, placement=admitted['deployment_assignment'],
                placement_sha256=admitted['deployment_assignment_sha256'], source_sha256=frozen['source_sha256'])
        except Exception as error:
            out.update(error_type=type(error).__name__, reason=str(error)[-1800:])
        finally:
            path = S / 'environment-outcomes' / (ident + '.json')
            n.freeze(path, out)
            if out['status'] == 'ENV_READY':
                ready = dict(out, raw_outcome=str(path), raw_outcome_sha256=n.sha(path))
                digest = hashlib.sha256(json.dumps(ready, sort_keys=True).encode()).hexdigest()
                n.freeze(n.D / 'ready-revisions' / ident / (digest + '.json'), ready)
            if admitted is not None:
                try:
                    n.freeze(S / 'image-release' / (ident + '.json'), await asyncio.to_thread(n.release_cold_cache, admitted))
                except Exception as error:
                    n.freeze(S / 'image-release-errors' / (ident + '.json'), dict(error_type=type(error).__name__, reason=str(error)[-800:]))
            terminal[ident] = out['status']
            state(ident, 'TASK_NATIVE_RECHECK_TERMINAL')
            print(json.dumps(dict(task_id=ident, status=out['status'], reason=out.get('reason'))), flush=True)
    state(None, 'FINITE_EXACT_ORIGINAL_ARCHIVE_RECHECK_TERMINAL')
    n.freeze(S / 'TERMINAL.json', json.loads((S / 'state.json').read_text()))


if __name__ == '__main__':
    os.environ['PATH'] = str(n.R / 'client-bin-v2') + ':' + os.environ['PATH']
    for name in ['DEEPSEEK_API_KEY', 'OPENAI_API_KEY', 'GH_TOKEN']:
        os.environ.pop(name, None)
    asyncio.run(main())
