"""Validate only the declared original-process and trusted ps formatting change."""
import json
from pathlib import Path
import collection_readiness_r12 as old
import collection_readiness_r13 as new
from collection_attempts_r8 import attempt_counts
from collection_selection_r7 import active_rows


def main():
    ident='task_004361_0d2c270d';R=new.R
    if new.NODE!=old.NODE or new.DEPLOYMENT['environment']!=old.DEPLOYMENT['environment']:
        raise ValueError('Runtime Engine, storage or environment changed')
    for key in ['task_public_dependencies','task_runtime_initialization']:
        a=old.DEPLOYMENT[key];b=new.DEPLOYMENT[key]
        if set(b)!=set(a)|{ident} or any(b[k]!=v for k,v in a.items()):raise ValueError('An existing accepted binding changed')
    if new.DEPLOYMENT['task_public_dependencies'][ident]['verifier_env']!={'COLUMNS':'4096'}:
        raise ValueError('Unexpected trusted Verifier environment override')
    if new.DEPLOYMENT['task_runtime_initialization'][ident]['initial_env']!={'COLUMNS':'4096'}:
        raise ValueError('Unexpected trusted initial environment override')
    if new.DEPLOYMENT['new_native_acceptance_required_task_ids']!=[ident]:raise ValueError('Unexpected newly required acceptance')
    client=Path(new.DEPLOYMENT['native_client_bin'])/'ssh'
    proof=Path(new.DEPLOYMENT['native_client_acceptance'])
    if new.sha(client)!=new.DEPLOYMENT['native_client_ssh_sha256'] or new.sha(proof)!=new.DEPLOYMENT['native_client_acceptance_sha256']:
        raise ValueError('Native SSH deployment binding changed')
    accepted=json.loads(proof.read_text())
    if not accepted['passed'] or accepted['source_client_sha256']!=new.sha(client) or accepted['concurrency']!=8:
        raise ValueError('Eight independent same-Engine native SSH calls were not accepted')
    if new.sha(R/'client-bin-v2/rsync')!='8f9b3942d5be0d89e5d5822d94027e5ed8273c39e96a759abfacefbe8bd38c21':raise ValueError('Existing unlimited rsync changed')
    counts=attempt_counts();selected=active_rows(counts);normalized={};examples={}
    for root in old.readiness_roots():
        for p in [*sorted((root/'environment-outcomes').glob('*.json')),*sorted((root/'ready-revisions').glob('*/*.json'))]:
            value=json.loads(p.read_text())
            if value['status']=='ENV_READY' and value['task_id']!=ident:normalized[value['task_id']]=new.normalize_ready(value,p)
    for pool in ['calibforge','tmax']:
        for row in [x for x in selected if x['pool']==pool and x['task_id'] in normalized][:3]:
            examples[row['task_id']]=normalized[row['task_id']]['admitted_task']
    for task in set(old.DEPLOYMENT['task_public_dependencies'])|set(old.DEPLOYMENT['task_runtime_initialization']):
        if task in normalized:examples[task]=normalized[task]['admitted_task']
    runtime=new.DEPLOYMENT['task_runtime_initialization'][ident]
    raw=json.loads(Path(runtime['native_acceptance']).read_text());examples[ident]=new.choose(raw['admitted_task'])
    for task,row in examples.items():
        for kind in ['install','nop','teacher']:
            a=old.native_config(row,kind).model_dump(mode='json');b=new.native_config(row,kind).model_dump(mode='json')
            if task==ident:
                a['environment']['extra_docker_compose'] += [x['path'] for x in runtime['extra_docker_compose']]
                a['verifier']['env']['COLUMNS']='4096'
            for cfg in [a,b]:cfg.pop('trial_name')
            if a!=b:raise ValueError('Unexpected native configuration change: '+task+'/'+kind)
    helper=(R/'scripts/campaign_image17_r12.py').read_text()
    expected=helper.replace("    if initial:\n        test = Path(initial['path'])", "    for key,value in request.get('initial_env',{}).items():\n        args += ['--env',key+'='+value]\n    if initial:\n        test = Path(initial['path'])")
    if (R/'scripts/campaign_image17_r13.py').read_text()!=expected:raise ValueError('Image helper changed outside declared trusted initial environment')
    engine=new.rpc('engine')
    proof=dict(passed=True,controller_source_sha256=new.sha(R/'scripts/run_collection_stream_r13.py'),
        deployment_config_sha256=new.CONFIG_SHA,old_deployment_config_sha256=old.CONFIG_SHA,
        helper_sha256={name:new.sha(R/'scripts'/name) for name in ['collection_readiness_r13.py','collection_readiness_r12.py','collection_readiness_r11.py','collection_readiness_r9.py','campaign_image17_r13.py','resolve_cold_image17_r3.py','collection_attempts_r8.py']},
        preserved_native_ready_tasks=len(normalized),native_config_equivalence_tasks=sorted(examples),
        native_config_kinds=['install','nop','teacher'],engine=engine,
        teacher_config_sha256=new.c.TEACHER_SHA,wheel_sha256=new.c.WHEEL_SHA,
        original_task_test_resource_deadline_changes=0,teacher_environment_or_agent_loop_changes=0,
        global_teacher_cap=8,per_task_attempt_cap=2,total_attempt_cap=2000,task_count=1000,
        source_sha256=new.sha(Path(__file__)),teacher_dispatch_authority_granted=False)
    new.freeze(R/'checks/controller-r13-offline-acceptance-r104.json',proof)
    print(json.dumps(proof))


if __name__=='__main__':main()
