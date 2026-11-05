"""Exercise the actual bounded warm-loop AST without any native queue or API."""
import ast
import asyncio
from collections import Counter
import datetime
import hashlib
import json
from pathlib import Path
import textwrap

import run_collection_stream_r7 as old
import run_collection_stream_r8 as new

R=new.R


async def main():
    source=R/'scripts/run_collection_stream_r8.py';tree=ast.parse(source.read_text())
    function=next(n for n in tree.body if isinstance(n,ast.AsyncFunctionDef) and n.name=='main')
    loop=next(n for n in function.body if isinstance(n,ast.While))
    admission=next(n for n in loop.body if isinstance(n,ast.If) and ast.unparse(n.test)=='not draining')
    start=next(i for i,n in enumerate(admission.body) if isinstance(n,ast.If) and ast.unparse(n.test)=='candidates')
    resident=admission.body[start:start+2]
    cold=next(i for i,n in enumerate(admission.body) if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='cold' for t in n.targets))
    warming=admission.body[cold:cold+2]
    # Execute these exact production statements, with only image inspection
    # and zero-side-effect warm coroutines substituted. No copied algorithm.
    signature='candidates,ready,outcomes,owned,warming,resident_probe_cursor,next_warm_pool,image_info,warm'
    code='async def exercise('+signature+'):\n'+textwrap.indent('\n'.join(ast.unparse(n) for n in resident+warming),' ')+ '\n return resident_probe_cursor,next_warm_pool\n'
    namespace=dict(asyncio=asyncio,Counter=Counter);exec(compile(code,str(source)+':actual-resident-and-warm-branches','exec'),namespace)
    examples=[]
    for name,initial_ready,pools,resident_pools in [
        ('manifest_cf_first_tmax_cold',0,['calibforge']*500+['tmax']*500,{'calibforge'}),
        ('both_pools_cold',0,['calibforge']*500+['tmax']*500,set()),
        ('one_buffer_slot_left',23,['tmax']*500,set()),
        ('only_one_eligible_pool',0,['tmax']*500,{'tmax'}),
    ]:
        candidates=[dict(task_id='task_'+str(i),pool=pool,slot_id='slot_'+str(i)) for i,pool in enumerate(pools)]
        outcomes={x['task_id']:dict(pool=x['pool'],admitted_task=dict(x,image_id=x['task_id'])) for x in candidates}
        ready={'ready_'+str(i):dict(task_id='ready_'+str(i),pool='calibforge') for i in range(initial_ready)}
        warmed=[];inspected=[];active={}
        def inspect(image):
            inspected.append(image)
            return {'Id':image} if outcomes[image]['pool'] in resident_pools else None
        async def warm(row):warmed.append(row['task_id'])
        cursor,_=await namespace['exercise'](candidates,ready,outcomes,set(),active,0,'tmax',inspect,warm)
        if active:await asyncio.gather(*active.values())
        warm_pools=Counter(outcomes[x]['pool'] for x in warmed);ready_pools=Counter(x['pool'] for x in ready.values())
        assert len(inspected)<=16 and len(active)<=2 and len(ready)+len(active)<=24
        if name=='manifest_cf_first_tmax_cold':assert warm_pools=={'tmax':2} and ready_pools=={'calibforge':12}
        if name=='both_pools_cold':assert warm_pools=={'calibforge':1,'tmax':1}
        if name=='one_buffer_slot_left':assert warm_pools=={'tmax':1}
        if name=='only_one_eligible_pool':assert ready_pools['tmax']>12
        examples.append(dict(case=name,probes=len(inspected),next_probe_cursor=cursor,ready_by_pool=dict(ready_pools),warming_by_pool=dict(warm_pools)))
    assert old.native_config is new.native_config
    selected=new.selected_rows();assert selected==old.selected_rows() and len(selected)==1000
    assert new.attempt_counts()==old.attempt_counts()
    assert not any(isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute) and isinstance(n.func.value,ast.Name) and n.func.value.id=='c' and n.func.attr=='attempt_counts' for n in ast.walk(tree))
    assert 'while len(active)+len(inherited_active())>=8:await asyncio.sleep(.25)' in source.read_text()
    assert 'teacher_slots=asyncio.Semaphore(8)' in source.read_text()
    assert 'teacher_queue=TrialQueue(n_concurrent=12' in source.read_text()
    assert 'preparation_queue=TrialQueue(n_concurrent=8' in source.read_text()
    # Real17 Native Result/placement hashes are checked by the exact production
    # refresh and block functions. Metadata copies live only in this isolated
    # test namespace and are never published as Campaign Ready receipts.
    import tempfile
    base_file=next(p for p in [*sorted((new.READINESS_ROOT/'environment-outcomes').glob('*.json')),*sorted((new.READINESS_ROOT/'ready-revisions').glob('*/*.json'))] if new.read(p)['status']=='ENV_READY' and not new.blocking_review(new.read(p)['task_id']))
    base=new.read(base_file);ident=base['task_id']
    functions=[n for n in ast.walk(tree) if isinstance(n,ast.FunctionDef) and n.name in ['block_current_readiness','refresh']]
    with tempfile.TemporaryDirectory(prefix='controller-r8-readiness-test-',dir=R/'checks') as temporary:
        directory=Path(temporary);paths=[]
        for index in [1,2]:
            file=directory/(str(index)+'.json');file.write_text(json.dumps(dict(base,isolated_offline_revision=index)));paths.append(file)
        outcomes={ident:dict(status='ENV_FAILED')};blocked={}
        state=dict(ready_paths=lambda:paths,read=new.read,sha=new.sha,Path=Path,blocking_review=lambda _:False,DEPLOYMENT=new.DEPLOYMENT,CONFIG_SHA=new.CONFIG_SHA,outcomes=outcomes,blocked_ready_receipts=blocked)
        exec(compile(ast.fix_missing_locations(ast.Module(body=functions,type_ignores=[])),str(source)+':actual-readiness-functions','exec'),state)
        state['refresh']([{'task_id':ident}]);assert outcomes[ident]['status']=='ENV_READY'
        state['block_current_readiness'](ident);assert blocked[ident]=={new.sha(p) for p in paths}
        outcomes[ident]=dict(status='ENV_BLOCKED');state['refresh']([{'task_id':ident}]);assert outcomes[ident]['status']=='ENV_BLOCKED'
        file=directory/'3.json';file.write_text(json.dumps(dict(base,isolated_offline_revision=3)));paths.append(file)
        state['refresh']([{'task_id':ident}]);assert outcomes[ident]['status']=='ENV_READY' and outcomes[ident]['accepted_ready_receipt_sha256']==new.sha(file)
    for name in ['attempt-counter-r8-boundary-acceptance.json','incremental-export-r8-real-canonical-equivalence.json','qualification-reader-r8-validator-acceptance.json']:
        assert json.loads((R/'checks'/name).read_text())['passed']
    result=dict(passed=True,checked_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),controller_source_sha256=new.sha(source),
        unchanged_native_config_function=True,selected_unique_tasks=1000,selected_counts=dict(Counter(x['pool'] for x in selected)),
        actual_counter_current_parity=True,existing_attempt_boundary_acceptance=str(R/'checks/attempt-counter-r8-boundary-acceptance.json'),
        actual_production_branch_cases=examples,revision_only_ready_no_eager_missing_file=True,all_known_old_ready_proofs_remain_blocked=True,new_validated_ready_supersedes_failure=True,readiness_test_real_native_result_hashes=True,
        native_global8_staging12_preparation8_unchanged=True,model_calls=0,native_queue_submissions=0,teacher_controller_started=False,
        activation='Pending explicit native handoff fence; this acceptance has no dispatch authority')
    with (R/'checks/controller-r8-offline-acceptance-r3.json').open('x') as stream:json.dump(result,stream,indent=2)
    print(json.dumps(result),flush=True)


if __name__=='__main__':asyncio.run(main())
