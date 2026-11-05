"""Prove native configs/Ready evidence unchanged by a client-only transport fix."""
import json
from pathlib import Path
import collection_readiness_r14 as old
import collection_readiness_r15 as new
from collection_attempts_r8 import attempt_counts
from collection_selection_r7 import active_rows


def main():
    R=new.R
    if new.NODE!=old.NODE or new.DEPLOYMENT['environment']!=old.DEPLOYMENT['environment']:raise ValueError('Engine, node, storage or native runtime changed')
    for key in ['task_public_dependencies','task_runtime_initialization','public_verifier_dependency_approvals149','public_image_bindings_mirror149','dependency_override','dependency_override_sha256','image_helper','image_helper_sha256']:
        if new.DEPLOYMENT[key]!=old.DEPLOYMENT[key]:raise ValueError('Accepted Task/image/bootstrap binding changed: '+key)
    if new.DEPLOYMENT['new_native_acceptance_required_task_ids']:raise ValueError('An unchanged Task unnecessarily requires replay')
    pool_file=Path(new.DEPLOYMENT['native_client_acceptance']);pool=json.loads(pool_file.read_text());client=Path(new.DEPLOYMENT['native_client_bin'])/'ssh'
    if new.sha(pool_file)!=new.DEPLOYMENT['native_client_acceptance_sha256'] or new.sha(client)!=new.DEPLOYMENT['native_client_ssh_sha256'] or not pool['passed']:
        raise ValueError('Native SSH candidate identity changed')
    if new.sha(R/'client-bin-v2/rsync')!='8f9b3942d5be0d89e5d5822d94027e5ed8273c39e96a759abfacefbe8bd38c21':raise ValueError('Existing unlimited rsync changed')
    selected=active_rows(attempt_counts());normalized={};examples={}
    for root in old.readiness_roots():
        for path in [*sorted((root/'environment-outcomes').glob('*.json')),*sorted((root/'ready-revisions').glob('*/*.json'))]:
            value=json.loads(path.read_text())
            if value['status']=='ENV_READY':normalized[value['task_id']]=new.normalize_ready(value,path)
    for pool_name in ['calibforge','tmax']:
        for row in [x for x in selected if x['pool']==pool_name and x['task_id'] in normalized][:3]:examples[row['task_id']]=normalized[row['task_id']]['admitted_task']
    for ident in set(new.DEPLOYMENT['task_public_dependencies'])|set(new.DEPLOYMENT['task_runtime_initialization']):
        if ident in normalized:examples[ident]=normalized[ident]['admitted_task']
    for ident,row in examples.items():
        for kind in ['install','nop','teacher']:
            a=old.native_config(row,kind).model_dump(mode='json');b=new.native_config(row,kind).model_dump(mode='json')
            for config in [a,b]:config.pop('trial_name')
            if a!=b:raise ValueError('Native config changed under SSH-only deployment: '+ident+'/'+kind)
    io=R/'checks/controller-r15-readiness-io-acceptance-r128.json'
    accepted_io=json.loads(io.read_text())
    if not accepted_io['passed'] or accepted_io['new_controller_sha256']!=new.sha(R/'scripts/run_collection_stream_r15.py') or accepted_io['deployment_config_sha256']!=new.CONFIG_SHA:raise ValueError('Readiness event-loop boundary not accepted')
    engine=new.rpc('engine')
    proof=dict(passed=True,controller_source_sha256=new.sha(R/'scripts/run_collection_stream_r15.py'),
        deployment_config_sha256=new.CONFIG_SHA,old_deployment_config_sha256=old.CONFIG_SHA,
        helper_sha256={name:new.sha(R/'scripts'/name) for name in ['collection_readiness_r15.py','collection_readiness_r14.py','collection_readiness_r13.py','collection_readiness_r12.py','collection_readiness_r11.py','collection_readiness_r9.py','campaign_image17_r13.py','resolve_cold_image17_r3.py','collection_attempts_r8.py']},
        preserved_native_ready_tasks=len(normalized),native_config_equivalence_tasks=sorted(examples),native_config_kinds=['install','nop','teacher'],
        native_client_sha256=new.sha(client),native_pool_acceptance_sha256=new.sha(pool_file),engine=engine,
        teacher_config_sha256=new.c.TEACHER_SHA,wheel_sha256=new.c.WHEEL_SHA,
        global_teacher_cap=8,per_task_attempt_cap=2,total_attempt_cap=2000,task_count=1000,
        original_task_test_image_resource_deadline_prompt_tools_or_model_changes=0,teacher_admission_granted=False,
        source_sha256=new.sha(Path(__file__)))
    new.freeze(R/'checks/controller-r15-offline-acceptance-r126.json',proof);print(json.dumps(proof))


if __name__=='__main__':main()
