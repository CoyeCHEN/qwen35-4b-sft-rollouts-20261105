"""Offline exact-delta and native-receipt validation before R19 admission."""
import json
from pathlib import Path
import collection_readiness_r17 as old
import collection_readiness_r19 as new

R=new.R
IDS={'data-processing_20260420_020307_002','video-processing_20260414_211532_001'}
assert old.NODE==new.NODE and old.DEPLOYMENT['environment']==new.DEPLOYMENT['environment']
for key in ['task_runtime_initialization','public_verifier_dependency_approvals149','public_image_bindings_mirror149',
            'dependency_override','dependency_override_sha256','native_client_bin','native_client_ssh_sha256','native_ssh_pool']:
    if old.DEPLOYMENT[key]!=new.DEPLOYMENT[key]:raise ValueError('Unrelated frozen binding changed: '+key)
before=old.DEPLOYMENT['task_public_dependencies'];after=new.DEPLOYMENT['task_public_dependencies']
assert set(after)-set(before)==IDS and all(after[key]==value for key,value in before.items())
assert set(new.DEPLOYMENT['new_native_acceptance_required_task_ids'])==IDS
assert new.DEPLOYMENT['hot_setup_buffer']==old.DEPLOYMENT['hot_setup_buffer']==8
assert new.DEPLOYMENT['native_lifecycle_capacity']==old.DEPLOYMENT['native_lifecycle_capacity']==24
phase=R/'checks/controller-r19-agent-phase-acceptance-r224.json'
phase_doc=json.loads(phase.read_text());assert phase_doc['passed']
assert phase_doc['controller_source_sha256']==new.sha(R/'scripts/run_collection_stream_r19.py')
accepted=[]
for ident in sorted(IDS):
    path=R/'stream/signed-debian-native-acceptance17-r223/environment-outcomes'/(ident+'.json')
    value=json.loads(path.read_text())
    assert value['status']=='ENV_READY' and value['deployment_config_sha256']==new.CONFIG_SHA
    assert value['engine_id']==new.NODE['engine_id'] and value['model_calls']==0
    for kind in ['install','nop']:
        result=Path(value['native_'+kind+'_trial'])/'result.json'
        assert new.sha(result)==value[kind+'_result_sha256']
        native=json.loads(result.read_text());assert native['finished_at'] and not native.get('exception_info') and not native['infrastructure_errors']
    row=value['admitted_task']
    task=Path(row['prepared_task_path'])
    assert new.sha(task/'task.toml')==row['prepared_task_toml_sha256']
    assert new.sha(task/'instruction.md')==row['instruction_sha256']
    for artifact in row['verifier_files']:assert new.sha(task/artifact['path'])==artifact['sha256']
    for kind in ['install','nop','teacher']:
        a=old.native_config(row,kind).model_dump(mode='json');b=new.native_config(row,kind).model_dump(mode='json')
        a.pop('trial_name');b.pop('trial_name')
        added=after[ident]['extra_docker_compose']
        expected=[item['path'] for item in added]
        actual=b['environment']['extra_docker_compose']
        if actual[-len(expected):]!=expected:raise ValueError('Declared APT Compose files not attached to the native Task')
        b['environment']['extra_docker_compose']=actual[:-len(expected)]
        if a!=b:raise ValueError('Native config changed beyond the declared public APT binding')
    for item in after[ident]['extra_docker_compose']:
        compose=Path(item['path']);assert new.sha(compose)==item['sha256']
        mount=json.loads(compose.read_text())['services']['main']['volumes'][0]
        source=Path(mount['source']);assert source.parent==compose.parent and mount['read_only']
        assert new.sha(source)==after[ident]['candidate_apt_source_sha256']
    accepted.append(dict(task_id=ident,path=str(path),sha256=new.sha(path),native_install=value['native_install_trial'],
        native_nop=value['native_nop_trial'],official_nop_reward=value['nop_reward']))
proof=dict(passed=True,controller_source_sha256=new.sha(R/'scripts/run_collection_stream_r19.py'),
    deployment_config_sha256=new.CONFIG_SHA,old_deployment_config_sha256=old.CONFIG_SHA,
    affected_task_ids=sorted(IDS),approvals=accepted,teacher_config_sha256=new.c.TEACHER_SHA,wheel_sha256=new.c.WHEEL_SHA,
    unchanged_original_images=True,unchanged_original_task_test_resource_deadline_model_and_tools=True,
    unchanged_teacher_global_cap=8,unchanged_native_cap=24,unchanged_hot_setup_buffer=8,
    source_sha256=new.sha(Path(__file__)),helper_sha256={name:new.sha(R/'scripts'/name) for name in
        ['collection_readiness_r19.py','collection_readiness_r17.py','collection_attempts_r8.py','campaign_image17_r13.py','resolve_cold_image17_r3.py']},
    teacher_admission_granted=False,model_calls=0)
new.freeze(R/'checks/controller-r19-offline-acceptance-r225.json',proof)
print(json.dumps(proof))
