"""Bind one completed original-process acceptance; do not grant admission."""
import json
from pathlib import Path
import collection_readiness_r12 as old
from collection_attempts_r8 import attempt_counts


def main():
    ident='task_004361_0d2c270d'
    root=old.R/'stream/original-process-format-native17-r109'
    source=root/'environment-outcomes'/(ident+'.json')
    value=json.loads(source.read_text())
    if value['status']!='CANDIDATE_ENV_READY_PENDING_RUNTIME_BINDING' or not (root/'TERMINAL.json').exists():
        raise ValueError('Exact native initial, CLI and official NOP have not completed')
    if attempt_counts().get(ident,0):raise ValueError('Preserve any started Teacher')
    for kind in ['install','nop']:
        trial=Path(value['native_'+kind+'_trial']);result=json.loads((trial/'result.json').read_text())
        if old.sha(trial/'result.json')!=value[kind+'_result_sha256'] or result.get('exception_info') or result.get('infrastructure_errors'):
            raise ValueError('Native Result changed or has infrastructure failure')
        if kind=='nop' and (not result.get('verifier',{}).get('finished_at') or result['verifier_result']['rewards']['reward']!=0):
            raise ValueError('Official NOP did not complete normally')
    ssh_proof=old.R/'checks/ssh-native-preflight-eight-r108.json'
    ssh=json.loads(ssh_proof.read_text());client=old.R/'client-bin-preflight-r108/ssh'
    if not ssh['passed'] or ssh['source_client_sha256']!=old.sha(client):raise ValueError('Exact native SSH client acceptance changed')
    config=json.loads(old.CONFIG.read_text())
    config.update(native_client_bin=str(client.parent),native_client_ssh_sha256=old.sha(client),
        native_client_acceptance=str(ssh_proof),native_client_acceptance_sha256=old.sha(ssh_proof),
        native_client_policy='New native Docker commands use independent SSH connections to the same authorized identity, endpoint and private Engine; old Trial process environments and client-bin-v2/rsync stay unchanged.')
    config.update(revision='r13',deployment_revision='r13',
        controller_root=str(old.R/'stream/collection-r4/deployment-r13'),
        readiness_root=str(old.R/'stream/collection-r4/deployment-r13-readiness'),
        previous_deployment_config=str(old.CONFIG),previous_deployment_config_sha256=old.CONFIG_SHA,
        image_helper=str(Path(config['image_helper']).with_name('campaign_image17_r13.py')),
        image_helper_sha256=old.sha(old.R/'scripts/campaign_image17_r13.py'),
        previous_public_image_bindings_mirror149=config['public_image_bindings_mirror149'],
        new_native_acceptance_required_task_ids=[ident])
    config['legacy_readiness']=dict(config=str(old.CONFIG),sha256=old.CONFIG_SHA,
        roots=[str(p) for p in old.readiness_roots()])
    recipe=value['startup_translation']
    config['task_runtime_initialization'][ident]=dict(startup=recipe['command'],startup_ready='pid1_sleep',
        initial_env={'COLUMNS':'4096'},
        extra_docker_compose=[dict(path=value['runtime_compose'],sha256=value['runtime_compose_sha256'])],
        original_container_def=recipe['original_container_def'],original_container_def_sha256=recipe['original_container_def_sha256'],
        native_acceptance=str(source),native_acceptance_sha256=old.sha(source),goal_repairs=0,
        reason='Invoke the unchanged source-declared deleted Python process after clearing its stale image-build marker. Trusted initial tests use explicit ps output width; the original process/SQL and all tests remain unchanged.')
    config['task_public_dependencies'][ident]=dict(verifier_env={'COLUMNS':'4096'},
        native_acceptance=str(source),native_acceptance_sha256=old.sha(source),
        reason='Original ps aux in pytest truncates the live process command to python3 repor. Explicit output width restores observation of the unchanged real process; no test or Goal modification.')
    config['public_dependency_policy']+=' One additional source-declared process and trusted initial/Verifier COLUMNS=4096; no Teacher environment or model transport change.'
    path=old.R/'configs/campaign-deployment17-r13.json';old.freeze(path,config)
    proof=dict(deployment_config=str(path),sha256=old.sha(path),native_acceptance=str(source),
        native_acceptance_sha256=old.sha(source),teacher_admission_granted=False,
        original_task_test_resource_deadline_changes=0,teacher_environment_changed=False)
    old.freeze(old.R/'checks/deployment-r13-candidate-input-freeze-r104.json',proof)
    print(json.dumps(proof))


if __name__=='__main__':main()
