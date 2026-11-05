"""Freeze a capacity-only deployment revision from measured setup shortages."""
import json
from pathlib import Path
import collection_readiness_r16 as old

R=old.R
evidence=sorted((R/'checks').glob('native-setup-capacity-r196-*.json'))[-1]
measured=json.loads(evidence.read_text())
if measured['last30_long_gap_without_installed_ready']<1:raise ValueError('No measured setup shortage')
config=json.loads(old.CONFIG.read_text())
config.update(revision='r17',deployment_revision='r17',controller_root=str(R/'stream/collection-r4/deployment-r17'),
    readiness_root=str(R/'stream/collection-r4/deployment-r17-readiness'),previous_deployment_config=str(old.CONFIG),
    previous_deployment_config_sha256=old.CONFIG_SHA,previous_public_image_bindings_mirror149=config['public_image_bindings_mirror149'],
    new_native_acceptance_required_task_ids=[],native_lifecycle_capacity=24,hot_setup_buffer=8,
    setup_capacity_evidence=dict(path=str(evidence),sha256=old.sha(evidence)),research_task_or_model_changes=0)
config['legacy_readiness']=dict(config=str(old.CONFIG),sha256=old.CONFIG_SHA,roots=[str(p) for p in old.readiness_roots()])
target=R/'configs/campaign-deployment17-r17.json'
old.freeze(target,config)
print(json.dumps(dict(config=str(target),sha256=old.sha(target),teacher_cap=8,native_cap=24,hot_setup_buffer=8,model_calls=0)))
