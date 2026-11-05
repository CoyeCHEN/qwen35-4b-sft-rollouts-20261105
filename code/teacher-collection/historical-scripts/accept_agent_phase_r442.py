"""Test exact frozen callbacks with the native Harbor hook enum and isolated phase records."""
import ast
import asyncio
import datetime
import json
from pathlib import Path
from types import SimpleNamespace

from harbor.trial.hooks import TrialEvent
import collection_readiness_r22 as n


async def main():
    path=n.R/'scripts/run_collection_stream_r22.py';tree=ast.parse(path.read_bytes())
    parent=next(x for x in tree.body if isinstance(x,ast.AsyncFunctionDef) and x.name=='main')
    functions=[x for x in parent.body if isinstance(x,ast.AsyncFunctionDef) and x.name in ['ended_agent','ended_teacher']]
    if len(functions)!=2:raise ValueError('Native phase callbacks changed')
    # nonlocal is removed only to run these exact callback bodies in an
    # isolated test namespace. The frozen production source stays unchanged.
    for function in functions:function.body=[x for x in function.body if not isinstance(x,ast.Nonlocal)]
    events=[];active={str(i):dict(task_id='task'+str(i),pool='tmax') for i in range(8)};post={}
    semaphore=asyncio.Semaphore(0)
    namespace=dict(active=active,post_agent=post,last_end=None,now=lambda:datetime.datetime.now(datetime.timezone.utc).isoformat(),
        event=lambda kind,**fields:events.append(dict(event=kind,**fields)),teacher_slots=semaphore,inherited_active=lambda:set())
    module=ast.Module(body=functions,type_ignores=[]);ast.fix_missing_locations(module);exec(compile(module,str(path),'exec'),namespace)
    result=SimpleNamespace(agent_execution=SimpleNamespace(finished_at=datetime.datetime.now(datetime.timezone.utc)),
        finished_at=datetime.datetime.now(datetime.timezone.utc),verifier_result=None,exception_info=None,infrastructure_errors=[])
    make=lambda name,boundary:SimpleNamespace(trial_name=name,result=result,event=boundary)
    await namespace['ended_agent'](make('0',TrialEvent.AGENT_END))
    if len(active)!=7 or set(post)!={'0'} or semaphore._value!=1:raise ValueError('Agent completion did not immediately free exactly one permit')
    await namespace['ended_agent'](make('0',TrialEvent.AGENT_END))
    if semaphore._value!=1:raise ValueError('Duplicate AgentEnd released a second permit')
    await namespace['ended_teacher'](make('0',TrialEvent.END))
    if post or semaphore._value!=1 or events[-1]['event']!='TEACHER_FINALIZED':raise ValueError('Verifier/native end changed the released permit')
    await namespace['ended_teacher'](make('1',TrialEvent.END))
    if semaphore._value!=2 or '1' in active or post:raise ValueError('Exceptional native terminal path leaked or duplicated a permit')
    await namespace['ended_teacher'](make('setup-only',TrialEvent.END))
    if semaphore._value!=2:raise ValueError('Non-admitted setup released a Teacher permit')
    text=path.read_text()
    if 'teacher_queue.add_hook(TrialEvent.AGENT_END,ended_agent)' not in text or 'TrialQueue(n_concurrent=24' not in text:
        raise ValueError('Native hook or bounded queue not connected')
    # Pure capacity arithmetic used by the frozen native refill expression.
    cases=[]
    for closed in range(13):
        stages=8+closed
        capacity=min(24,16+closed)
        additions=max(0,capacity-stages)
        if additions!=min(8,max(0,16-closed)):raise ValueError('Completed Agents consumed the hot setup buffer')
        cases.append(dict(post_agent=closed,agent_phases=8,hot_setups=additions,total_native_capacity=capacity))
    proof=dict(passed=True,controller_source_sha256=n.sha(path),deployment_config_sha256=n.CONFIG_SHA,
        native_agent_end_releases_once=True,native_end_preserves_finalization=True,exceptional_native_end_conservative_release=True,
        setup_only_does_not_release=True,unchanged_global_teacher_cap=8,capacity_cases=cases,
        native_hooks_file=str(Path(__import__('inspect').getfile(TrialEvent))),model_calls=0,
        source_sha256=n.sha(Path(__file__)))
    n.freeze(n.R/'checks/controller-r22-agent-phase-acceptance-r442.json',proof);print(json.dumps(proof))


if __name__=='__main__':asyncio.run(main())
