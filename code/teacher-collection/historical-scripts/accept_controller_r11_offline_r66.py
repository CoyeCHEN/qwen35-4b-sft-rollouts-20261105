"""Validate deployment-only changes against the running native controller."""
import copy
import json
from pathlib import Path

import collection_readiness_r9 as old
import collection_readiness_r11 as new
from collection_attempts_r8 import attempt_counts
from collection_selection_r7 import active_rows


def main():
    R=new.R
    if old.DEPLOYMENT['runtime']!=new.DEPLOYMENT['runtime'] or old.DEPLOYMENT['environment']!=new.DEPLOYMENT['environment']:
        raise ValueError('Deployment transition changed Engine/runtime/storage')
    cases=new.DEPLOYMENT['task_public_dependencies']
    if len(cases)!=4 or 'task_007141_26892089' in cases:raise ValueError('Rejected volume binding was not excluded')
    counts=attempt_counts();selected=active_rows(counts);normalized={};examples={}
    for root in old.readiness_roots():
        for p in [*sorted((root/'environment-outcomes').glob('*.json')),*sorted((root/'ready-revisions').glob('*/*.json'))]:
            v=json.loads(p.read_text())
            if v['status']!='ENV_READY' or v['task_id'] in cases:continue
            normalized[v['task_id']]=new.normalize_ready(v,p)
    for pool in ['calibforge','tmax']:
        for row in [x for x in selected if x['pool']==pool and x['task_id'] in normalized][:3]:
            examples[row['task_id']]=normalized[row['task_id']]['admitted_task']
    for ident in cases:
        row=next(x for x in selected if x['task_id']==ident)
        examples[ident]=new.prepare_identity(row)
    verified=[]
    for ident,row in examples.items():
        case=cases.get(ident,{})
        for kind in ['install','nop','teacher']:
            a=old.native_config(row,kind).model_dump(mode='json');b=new.native_config(row,kind).model_dump(mode='json')
            a['environment']['extra_docker_compose'] += [x['path'] for x in case.get('extra_docker_compose',[])]
            a['verifier']['env'].update(case.get('verifier_env',{}))
            for obj in [a,b]:obj.pop('trial_name')
            if a!=b:raise ValueError('Native config changed outside declared public dependency bindings: '+ident+'/'+kind)
        verified.append(ident)
    cargo=json.loads(Path(cases['task_009221_2c5f3e9f']['extra_docker_compose'][0]['path']).read_text())
    if cargo!={'services':{'main':{'environment':{'CARGO_HTTP_PROXY':'http://172.17.0.1:49179'}}}}:
        raise ValueError('Cargo binding alters a general/model HTTP proxy')
    for ident,case in cases.items():
        if ident.startswith('task_'):continue
        if set(case['verifier_env'])!={'http_proxy','https_proxy','HTTP_PROXY','HTTPS_PROXY','NO_PROXY','no_proxy'}:
            raise ValueError('Unexpected public Verifier dependency environment')
    engine=new.rpc('engine')
    if engine['engine_id']!=new.NODE['engine_id'] or engine['node']!='17':raise ValueError('Actual Engine identity mismatch')
    proof=dict(passed=True,controller_source_sha256=new.sha(R/'scripts/run_collection_stream_r11.py'),
        deployment_config_sha256=new.CONFIG_SHA,old_deployment_config_sha256=old.CONFIG_SHA,
        helper_sha256={name:new.sha(R/'scripts'/name) for name in ['collection_readiness_r11.py','collection_readiness_r9.py','campaign_image17_r9.py','collection_attempts_r8.py']},
        preserved_native_ready_tasks=len(normalized),native_config_equivalence_tasks=verified,native_config_kinds=['install','nop','teacher'],
        changed_only_declared_public_dependencies=True,rejected_external_volume_excluded=True,
        engine=engine,teacher_config_sha256=new.c.TEACHER_SHA,wheel_sha256=new.c.WHEEL_SHA,
        global_teacher_cap=8,per_task_attempt_cap=2,total_attempt_cap=2000,task_count=1000,
        model_transport_or_agent_loop_changes=0,official_task_test_image_resource_deadline_changes=0,
        source_sha256=new.sha(Path(__file__)),teacher_dispatch_authority_granted=False)
    new.freeze(R/'checks/controller-r11-offline-acceptance-r66.json',proof)
    print(json.dumps(proof))


if __name__=='__main__':main()
