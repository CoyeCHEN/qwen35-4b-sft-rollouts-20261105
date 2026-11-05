"""Version only native Agent permit lifetime and bounded native lifecycle capacity."""
import json
from pathlib import Path
import collection_readiness_r15 as old

R=old.R
evidence=sorted((R/'checks').glob('actual-active-agent-eight-and-backfill-r143-*.json'))[-1]
observed=json.loads(evidence.read_text())
closed=[x['trial_name'] for x in observed['rows'] if x.get('agent_phase_metadata',{}).get('completion_marker_present')]
if not closed:raise ValueError('No completed CLI was shown occupying the old lifecycle permit')
config=json.loads(old.CONFIG.read_text())
config.update(revision='r16',deployment_revision='r16',controller_root=str(R/'stream/collection-r4/deployment-r16'),
    readiness_root=str(R/'stream/collection-r4/deployment-r16-readiness'),previous_deployment_config=str(old.CONFIG),
    previous_deployment_config_sha256=old.CONFIG_SHA,previous_public_image_bindings_mirror149=config['public_image_bindings_mirror149'],
    new_native_acceptance_required_task_ids=[],teacher_permit_boundary='Native AGENT_START through AGENT_END',
    native_lifecycle_capacity=24,hot_setup_buffer=4,
    phase_boundary_evidence=dict(path=str(evidence),sha256=old.sha(evidence)),
    research_task_or_model_changes=0)
config['legacy_readiness']=dict(config=str(old.CONFIG),sha256=old.CONFIG_SHA,roots=[str(p) for p in old.readiness_roots()])
target=R/'configs/campaign-deployment17-r16.json';old.freeze(target,config)
proof=dict(deployment_config=str(target),sha256=old.sha(target),phase_evidence=str(evidence),
    phase_evidence_sha256=old.sha(evidence),old_completed_cli_trials_still_holding_permits=closed,
    global_teacher_cap=8,native_total_lifecycle_capacity=24,teacher_admission_granted=False,
    source_sha256=old.sha(Path(__file__)))
old.freeze(R/'checks/deployment-r16-candidate-input-freeze-r144.json',proof);print(json.dumps(proof))
