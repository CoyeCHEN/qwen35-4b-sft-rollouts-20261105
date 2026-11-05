"""Version only controller-side metadata scheduling; native Task configs stay exact."""
import json
from pathlib import Path
import collection_readiness_r14 as old


def main():
    path=old.R/'checks/native-readiness-scan-profile-r125.json';measured=json.loads(path.read_text())
    if measured['frozen_controller_sha256']!=old.sha(old.R/'scripts/run_collection_stream_r14.py'):raise ValueError('Measured frozen controller changed')
    config=json.loads(old.CONFIG.read_text())
    config.update(revision='r15',deployment_revision='r15',controller_root=str(old.R/'stream/collection-r4/deployment-r15'),
        readiness_root=str(old.R/'stream/collection-r4/deployment-r15-readiness'),previous_deployment_config=str(old.CONFIG),
        previous_deployment_config_sha256=old.CONFIG_SHA,previous_public_image_bindings_mirror149=config['public_image_bindings_mirror149'],
        readiness_metadata_io='Run the exact complete Ready validation in asyncio.to_thread; apply on the native event loop and recheck any setup-failure block registered during scanning.',
        readiness_profile=dict(path=str(path),sha256=old.sha(path)),new_native_acceptance_required_task_ids=[])
    config['legacy_readiness']=dict(config=str(old.CONFIG),sha256=old.CONFIG_SHA,roots=[str(p) for p in old.readiness_roots()])
    target=old.R/'configs/campaign-deployment17-r15.json';old.freeze(target,config)
    proof=dict(deployment_config=str(target),sha256=old.sha(target),profile=str(path),profile_sha256=old.sha(path),
        model_task_resource_deadline_tool_prompt_or_budget_changes=0,teacher_admission_granted=False)
    old.freeze(old.R/'checks/deployment-r15-candidate-input-freeze-r126.json',proof);print(json.dumps(proof))


if __name__=='__main__':main()
