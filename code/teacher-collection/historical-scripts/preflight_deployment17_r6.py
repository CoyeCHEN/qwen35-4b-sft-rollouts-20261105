"""Finite native17 buffer acceptance before changing dispatch ownership."""
import asyncio
import datetime
import fcntl
import json
import os
from pathlib import Path
from uuid import uuid4
from harbor.models.job.config import RetryConfig
from harbor.trial.queue import TrialQueue
import collection_readiness_r6 as n
import run_collection_stream_r4 as c


async def main():
    n.D.mkdir(parents=True, exist_ok=True)
    lock = (n.D / 'preflight.lock').open('a')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    plan = n.D / 'PREFLIGHT_PLAN.json'
    if plan.exists():
        raise FileExistsError('Observe existing finite preflight; no replay')
    counts = c.attempt_counts()
    state = json.loads((n.R / 'campaign-state.json').read_text())
    owned = set(state['active_task_pipelines']) | set(state['preparing_environments']) | set(state['warming_images'])
    rows = []
    for pool in ['calibforge', 'tmax']:
        candidates = [r for r in c.frozen_rows() if r['pool'] == pool and not counts[r['task_id']]
            and r['task_id'] not in owned and not n.blocking_review(r['task_id']) and n.find_basic(r)]
        rows += candidates[:4]
    n.freeze(plan, dict(tasks=rows, model_calls=0, teacher_dispatches=0, native_concurrency=2,
        deployment_config_sha256=n.CONFIG_SHA, source_sha256=n.sha(Path(__file__))))
    queue = TrialQueue(n_concurrent=2, retry_config=RetryConfig(max_retries=0))
    native_root = n.R / 'stream/collection-r4'
    async def one(row):
        ident = row['task_id']
        out = dict(task_id=ident, pool=row['pool'], status='ENV_FAILED', model_calls=0)
        admitted = None
        try:
            admitted = n.prepare_identity(row)
            material = await asyncio.to_thread(n.ensure_resident, admitted)
            n.freeze(n.D / 'preflight-materializations' / (ident + '.json'), material)
            initial = await asyncio.to_thread(n.initial, admitted)
            n.freeze(n.D / 'initial-outcomes' / (ident + '.json'), initial)
            for kind in ['install', 'nop']:
                cfg = n.native_config(admitted, kind)
                if kind == 'install':
                    cfg.agent.env = {}
                path = native_root / 'dispatches' / str(uuid4())
                path.mkdir(parents=True)
                (path / 'trial-config.json').write_text(cfg.model_dump_json(indent=2))
                n.freeze(path / 'dispatch.json', dict(task_id=ident, pool=row['pool'], kind=kind,
                    trial_name=cfg.trial_name, config_sha256=n.sha(path / 'trial-config.json'), model_calls=0, controller_revision='r6-preflight'))
                result = await queue.submit(cfg)
                trial = native_root / 'trials' / cfg.trial_name
                out['native_' + kind + '_trial'] = str(trial)
                out[kind + '_result_sha256'] = n.sha(trial / 'result.json')
                if result.exception_info or result.infrastructure_errors:
                    raise ValueError('Native17 ' + kind + ' lifecycle failure: ' + str(result.exception_info))
                if kind == 'nop':
                    out['nop_reward'] = n.verify_nop(result, trial, admitted)
            out.update(status='ENV_READY', admitted_task=admitted, engine_id=n.NODE['engine_id'],
                deployment_config_sha256=n.CONFIG_SHA, placement=admitted['deployment_assignment'],
                placement_sha256=admitted['deployment_assignment_sha256'], teacher_success_not_implied=True)
            n.freeze(n.D / 'environment-outcomes' / (ident + '.json'), out)
        except Exception as error:
            out.update(error_type=type(error).__name__, reason=str(error)[-2400:])
            n.freeze(n.D / 'preflight-failures' / (ident + '.json'), out)
        print(json.dumps(dict(task_id=ident, status=out['status'], reason=out.get('reason'))), flush=True)
    iterator = iter(rows)
    async def worker():
        while True:
            row = next(iterator, None)
            if row is None:
                return
            await one(row)
    async with asyncio.TaskGroup() as group:
        for _ in range(2):
            group.create_task(worker())
    n.freeze(n.D / 'PREFLIGHT_TERMINAL.json', dict(finished_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        observed_tasks=len(rows), ready=len(list((n.D / 'environment-outcomes').glob('*.json'))), model_calls=0))


if __name__ == '__main__':
    for key in ['DEEPSEEK_API_KEY', 'GH_TOKEN', 'OPENAI_API_KEY']:
        os.environ.pop(key, None)
    os.environ['PATH'] = str(n.R / 'client-bin-v2') + ':' + os.environ['PATH']
    os.environ['SSH_AUTH_SOCK'] = '/home/chenkeyi/.local/share/harbor-rsi/near-r3-20261015/auth.sock'
    asyncio.run(main())
