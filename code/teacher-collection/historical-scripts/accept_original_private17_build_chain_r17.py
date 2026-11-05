"""Read-only acceptance of an actual original Task through the private build chain."""
import datetime
import json
from pathlib import Path

import collection_readiness_r7 as n


def main():
    ident='task_002846_5f6e2d5a';scope=n.R/'stream/direct17-native-source-r17'
    raw=scope/'environment-outcomes'/(ident+'.json');value=json.loads(raw.read_text())
    if value['status']!='ENV_READY' or value['engine_id']!=n.NODE['engine_id'] or value['deployment_config_sha256']!=n.CONFIG_SHA:raise ValueError('Original private build chain is not accepted')
    build=Path(value['original_context_build']);receipt=json.loads(build.read_text())
    if n.sha(build)!=value['original_context_build_sha256'] or receipt['builder_engine_id']!=n.NODE['engine_id'] or not receipt['all_manifest_config_layer_hashes_verified']:
        raise ValueError('Original context/private Engine/archive integrity differs')
    task=value['admitted_task'];prepared=Path(task['prepared_task_path'])
    if n.sha(prepared/'task.toml')!=task['prepared_task_toml_sha256'] or n.sha(prepared/'instruction.md')!=task['instruction_sha256']:raise ValueError('Prepared Task/instruction changed')
    for artifact in task['verifier_files']:
        if n.sha(prepared/artifact['path'])!=artifact['sha256']:raise ValueError('Official verifier changed')
    native={}
    for kind in ['install','nop']:
        file=Path(value['native_'+kind+'_trial'])/'result.json';result=json.loads(file.read_text())
        if n.sha(file)!=value[kind+'_result_sha256'] or result['exception_info'] or result['infrastructure_errors']:raise ValueError('Native private Engine lifecycle failed')
        config=result['config'];env=config['environment']['kwargs']
        if env!=n.DEPLOYMENT['environment']['kwargs']:raise ValueError('Native install/Verifier used another backend')
        if kind=='install' and not config['install_only']:raise ValueError('Installation check unexpectedly ran a teacher')
        if kind=='nop' and (config['agent']['name']!='nop' or not result['verifier']['finished_at']):raise ValueError('Official zero-model verifier did not complete')
        native[kind]=dict(result=str(file),result_sha256=n.sha(file),started_at=result['started_at'],finished_at=result['finished_at'],
            endpoint=env['endpoint'],socket=env['remote_socket_path'],reward=(result.get('verifier_result') or {}).get('rewards'),
            official_verifier_completed=bool((result.get('verifier') or {}).get('finished_at')),exception=None,infrastructure_errors=[])
    canary=n.R/'checks/private17-terminal-joint-acceptance-r3.json';joint=json.loads(canary.read_text())
    # The original full teacher/Recorder/Qwen canary remains the model-service
    # acceptance. This original Task adds the moved native build-chain check.
    initial=scope/'initial-outcomes'/(ident+'.json');materialized=scope/'image-materializations'/(ident+'.json')
    proof=dict(status='ORIGINAL_TASK_PRIVATE_ENGINE17_BUILD_LOAD_INITIAL_INSTALL_OFFICIAL_NOP_ACCEPTED',checked_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        task_id=ident,node='17',engine_id=n.NODE['engine_id'],deployment_config=str(n.CONFIG),deployment_config_sha256=n.CONFIG_SHA,
        build_deployment=str(n.R/'configs/campaign-build17-r17.json'),build_deployment_sha256=n.sha(n.R/'configs/campaign-build17-r17.json'),
        raw_ready=str(raw),raw_ready_sha256=n.sha(raw),original_context_build=str(build),original_context_build_sha256=n.sha(build),
        original_context_sha256=receipt['source_context']['build_context_sha256'],source_revision=receipt['source_context']['source_revision'],
        native_image_manifest=receipt['native_manifest_digest'],archive_sha256=receipt['archive_sha256'],build_seconds=receipt['seconds'],
        builder_source_sha256=receipt['builder_source_sha256'],builder_engine_id=receipt['builder_engine_id'],all_manifest_config_layer_hashes_verified=True,
        initial_state_proof=str(initial),initial_state_proof_sha256=n.sha(initial),image_materialization_proof=str(materialized),image_materialization_sha256=n.sha(materialized),
        native=native,prior_full_model_recorder_qwen_acceptance=str(canary),prior_full_model_recorder_qwen_acceptance_sha256=n.sha(canary),
        prior_full_acceptance_status=joint.get('status'),teacher_config_sha256=n.c.TEACHER_SHA,wheel_sha256=n.c.WHEEL_SHA,
        model_calls_by_this_acceptance=0,canary_replays=0,teacher_successes_claimed_from_nop=0,original_task_or_tests_modified=False,
        authoritative_task_workspaces_and_logs=n.NODE['ssd_root'],image_bytes_via149_by_new_preparation=0)
    destination=n.R/'checks/original-private17-build-chain-acceptance-r17.json'
    n.freeze(destination,proof);print(json.dumps(proof),flush=True)


if __name__=='__main__':main()
