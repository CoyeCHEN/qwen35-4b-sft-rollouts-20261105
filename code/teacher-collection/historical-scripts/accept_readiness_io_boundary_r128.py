"""Compare exact Ready results and real asyncio responsiveness on current metadata."""
import ast
import asyncio
import copy
import json
from pathlib import Path
import time

import collection_readiness_r15 as n
from collection_attempts_r8 import attempt_counts
from collection_selection_r7 import active_rows


def functions(path,names):
    parent=next(x for x in ast.parse(path.read_bytes()).body if isinstance(x,ast.AsyncFunctionDef) and x.name=='main')
    result=[x for x in parent.body if isinstance(x,ast.FunctionDef) and x.name in names]
    if {x.name for x in result}!=set(names):raise ValueError('Frozen metadata functions changed')
    values=dict(read=lambda p:json.loads(p.read_text()),sha=n.sha,blocking_review=n.blocking_review,
        normalize_ready=n.normalize_ready,CONFIG_SHA=n.CONFIG_SHA,DEPLOYMENT=n.DEPLOYMENT,
        readiness_roots=n.readiness_roots,Path=Path,outcomes={},blocked_ready_receipts={})
    module=ast.Module(body=result,type_ignores=[]);ast.fix_missing_locations(module);exec(compile(module,str(path),'exec'),values)
    return values


async def heartbeat(operation):
    stop=False;gaps=[]
    async def tick():
        previous=time.monotonic()
        while not stop:
            await asyncio.sleep(.02);current=time.monotonic();gaps.append(current-previous);previous=current
    task=asyncio.create_task(tick());await asyncio.sleep(.04);begin=time.monotonic()
    try:await operation()
    finally:
        await asyncio.sleep(.04);stop=True;await task
    return dict(operation_seconds=time.monotonic()-begin,maximum_event_loop_tick_gap=max(gaps),ticks=len(gaps))


async def main():
    old_path=n.R/'scripts/run_collection_stream_r14.py';new_path=n.R/'scripts/run_collection_stream_r15.py'
    old=functions(old_path,['ready_paths','refresh']);new=functions(new_path,['ready_paths','scan_ready','apply_ready_updates'])
    rows=active_rows(attempt_counts());old['refresh'](rows)
    before=copy.deepcopy(new['outcomes']);updates=await asyncio.to_thread(new['scan_ready'],rows,{})
    if new['outcomes']!=before:raise ValueError('Background scan mutated live lifecycle outcomes')
    new['apply_ready_updates'](updates)
    if old['outcomes']!=new['outcomes']:raise ValueError('Background validation changed accepted Ready evidence')
    ident=next(iter(updates));item=updates[ident]
    new['outcomes'][ident]=dict(status='ENV_BLOCKED',reason='Simulated setup failure registered while scan was running')
    new['blocked_ready_receipts'][ident]={item['accepted_ready_receipt_sha256']}
    new['apply_ready_updates']({ident:item})
    if new['outcomes'][ident]['status']!='ENV_BLOCKED':raise ValueError('An in-flight stale Ready resurrected a new setup failure')
    new['blocked_ready_receipts'].clear();new['outcomes'][ident]=dict(status='ENV_READY',placement_sha256='different')
    try:new['apply_ready_updates']({ident:item})
    except ValueError:pass
    else:raise ValueError('A changed current placement was accepted')
    new['outcomes'][ident]=old['outcomes'][ident]
    async def synchronous():old['refresh'](rows)
    async def threaded():
        update=await asyncio.to_thread(new['scan_ready'],rows,{})
        new['apply_ready_updates'](update)
    baseline=await heartbeat(synchronous);candidate=await heartbeat(threaded)
    if candidate['maximum_event_loop_tick_gap']>=baseline['maximum_event_loop_tick_gap']/2:raise ValueError('Real event-loop responsiveness did not improve')
    if old['outcomes']!=new['outcomes']:raise ValueError('Accepted evidence changed during timing')
    proof=dict(passed=True,old_controller_sha256=n.sha(old_path),new_controller_sha256=n.sha(new_path),
        deployment_config_sha256=n.CONFIG_SHA,accepted_ready_tasks=len(updates),exact_ready_results_equal=True,
        background_scan_does_not_mutate_lifecycle_state=True,new_setup_failure_block_rechecked=True,
        changed_current_placement_rejected=True,baseline=baseline,candidate=candidate,
        model_calls=0,teacher_dispatches=0,task_or_reward_changes=0,source_sha256=n.sha(Path(__file__)))
    n.freeze(n.R/'checks/controller-r15-readiness-io-acceptance-r128.json',proof);print(json.dumps(proof),flush=True)


if __name__=='__main__':asyncio.run(main())
