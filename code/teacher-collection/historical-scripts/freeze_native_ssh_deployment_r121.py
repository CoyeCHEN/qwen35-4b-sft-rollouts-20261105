"""Freeze a client-only deployment revision after its complete zero-model test."""
import json
from pathlib import Path
import collection_readiness_r13 as old


def main():
    pool_path=old.R/'checks/native-ssh-preseed-pool-r119.json';pool=json.loads(pool_path.read_text())
    source=old.R/'stream/native-ssh-pool-candidate17-r120/OUTCOME.json';case=json.loads(source.read_text())
    client=Path(pool['native_client_bin'])/'ssh'
    if not pool['passed'] or old.sha(client)!=pool['native_client_sha256'] or case['status']!='NATIVE_SSH_POOL_CANDIDATE_ACCEPTED' or case['native_client_sha256']!=pool['native_client_sha256']:
        raise ValueError('Exact native SSH client did not pass full initial/CLI/NOP acceptance')
    for item in case['native_results'].values():
        result=Path(item['trial'])/'result.json';raw=json.loads(result.read_text())
        if old.sha(result)!=item['result_sha256'] or raw.get('exception_info') or raw.get('infrastructure_errors') or not raw['finished_at']:raise ValueError('Accepted native Result changed')
    config=json.loads(old.CONFIG.read_text())
    config.update(revision='r14',deployment_revision='r14',
        controller_root=str(old.R/'stream/collection-r4/deployment-r14'),readiness_root=str(old.R/'stream/collection-r4/deployment-r14-readiness'),
        previous_deployment_config=str(old.CONFIG),previous_deployment_config_sha256=old.CONFIG_SHA,
        native_client_bin=pool['native_client_bin'],native_client_ssh_sha256=pool['native_client_sha256'],
        native_client_acceptance=str(pool_path),native_client_acceptance_sha256=old.sha(pool_path),
        native_client_policy='Use the fixed16 pre-opened native OpenSSH sockets with automatic master creation disabled. A missing socket uses the ordinary independent native SSH connection. Same authorized identity/host/private Engine; model HTTP transport unchanged.',
        native_ssh_pool=dict(path=str(pool_path),sha256=old.sha(pool_path),size=16),
        native_transport_full_acceptance=dict(path=str(source),sha256=old.sha(source)),
        previous_public_image_bindings_mirror149=config['public_image_bindings_mirror149'],
        new_native_acceptance_required_task_ids=[])
    config['legacy_readiness']=dict(config=str(old.CONFIG),sha256=old.CONFIG_SHA,roots=[str(p) for p in old.readiness_roots()])
    path=old.R/'configs/campaign-deployment17-r14.json';old.freeze(path,config)
    proof=dict(deployment_config=str(path),sha256=old.sha(path),native_pool=str(pool_path),native_pool_sha256=old.sha(pool_path),
        native_acceptance=str(source),native_acceptance_sha256=old.sha(source),teacher_admission_granted=False,
        task_test_image_resource_deadline_prompt_tool_model_or_attempt_changes=0)
    old.freeze(old.R/'checks/deployment-r14-candidate-input-freeze-r121.json',proof);print(json.dumps(proof))


if __name__=='__main__':main()
