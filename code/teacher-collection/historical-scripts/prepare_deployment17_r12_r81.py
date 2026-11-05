"""Freeze approved image/runtime deployment inputs; grant no dispatch authority."""
import copy
import json
from pathlib import Path
import shlex
import subprocess

import collection_readiness_r11 as n


def main():
    target=n.R/'configs/campaign-deployment17-r12.json'
    if target.exists():raise FileExistsError('Inspect existing frozen deployment candidate')
    cfg=copy.deepcopy(n.DEPLOYMENT);scripts=Path(n.DEPLOYMENT['image_helper']).parent
    for name in ['resolve_cold_image17_r3.py','campaign_image17_r12.py']:
        source=n.R/'scripts'/name
        subprocess.run(['rsync','-a','-e',shlex.join(n.DEPLOYMENT['ssh']),str(source),n.DEPLOYMENT['host']+':'+str(scripts/name)],check=True,timeout=120)
    mapping=n.R/'manifests/PRIVATE17_PUBLIC_IMAGE_BINDINGS_R76.json'
    remote=n.NODE['ssd_root']+'/deployment-r12/public-image-bindings-r76.json'
    subprocess.run([*n.DEPLOYMENT['ssh'],n.DEPLOYMENT['host'],'mkdir -p '+shlex.quote(str(Path(remote).parent))],check=True,timeout=30)
    subprocess.run(['rsync','-a','-e',shlex.join(n.DEPLOYMENT['ssh']),str(mapping),n.DEPLOYMENT['host']+':'+remote],check=True,timeout=120)
    cfg['runtime']['cold_resolver_sha256']=n.sha(n.R/'scripts/resolve_cold_image17_r3.py')
    cfg['runtime']['approved_public_verifier_dependency_bindings']=dict(path=remote,sha256=n.sha(mapping))
    cfg['image_helper']=str(scripts/'campaign_image17_r12.py');cfg['image_helper_sha256']=n.sha(n.R/'scripts/campaign_image17_r12.py')
    approval=n.R/'manifests/PUBLIC_DEPENDENCY_IMAGE_APPROVALS_R76.json'
    cfg['public_verifier_dependency_approvals149']=dict(path=str(approval),sha256=n.sha(approval))
    old_mapping=n.R/'checks/public-image-bindings-r39-mirror-r76.json'
    cfg['previous_public_image_bindings_mirror149']=dict(path=str(old_mapping),sha256=n.sha(old_mapping))
    cfg['public_image_bindings_mirror149']=dict(path=str(mapping),sha256=n.sha(mapping))
    cases={}
    for ident in ['task_002533_e325196c','task_009717_6fd14b5e']:
        path=n.R/'stream/original-runtime-process-native17-r71/environment-outcomes'/(ident+'.json')
        value=json.loads(path.read_text())
        if value['status']!='CANDIDATE_ENV_READY_PENDING_RUNTIME_BINDING' or value['nop_reward']!=0:
            raise ValueError('Original runtime initializer has no completed native zero')
        recipe=value['startup_translation'];source=Path(recipe['original_container_def'])
        if n.sha(source)!=recipe['original_container_def_sha256']:raise ValueError('Original process declaration changed')
        override=Path(value['runtime_compose'])
        if n.sha(override)!=value['runtime_compose_sha256']:raise ValueError('Accepted native runtime override changed')
        cases[ident]=dict(startup=recipe['command'],startup_ready='pid1_sleep',
            extra_docker_compose=[dict(path=str(override),sha256=n.sha(override))],
            original_container_def=str(source),original_container_def_sha256=n.sha(source),
            native_acceptance=str(path),native_acceptance_sha256=n.sha(path),
            reason=recipe['reason'],goal_repairs=0)
    cfg.update(revision='r12',deployment_revision='r12',controller_root=str(n.R/'stream/collection-r4/deployment-r12'),
        readiness_root=str(n.R/'stream/collection-r4/deployment-r12-readiness'),
        previous_deployment_config=str(n.CONFIG),previous_deployment_config_sha256=n.CONFIG_SHA,
        task_runtime_initialization=cases,
        new_native_acceptance_required_task_ids=['task_007141_26892089','task_001742_6788502c',*cases],
        legacy_readiness=dict(config=str(n.CONFIG),sha256=n.CONFIG_SHA,roots=[*n.DEPLOYMENT['legacy_readiness']['roots'],n.DEPLOYMENT['readiness_root'],n.DEPLOYMENT['controller_root']]),
        public_dependency_policy='Four image-specific native approvals, four unchanged Verifier/Cargo-only proxy bindings, and two exact original background-process initializers. No global teacher proxy, Goal repair, official test or resource/deadline modification. Rejected/pending candidates are excluded.')
    n.freeze(target,cfg)
    proof=dict(config=str(target),config_sha256=n.sha(target),image_approvals_sha256=n.sha(approval),
        native_runtime_initializers=sorted(cases),source_sha256=n.sha(Path(__file__)),teacher_dispatch_authority_granted=False)
    n.freeze(n.R/'checks/deployment-r12-candidate-input-freeze-r81.json',proof)
    print(json.dumps(proof))


if __name__=='__main__':main()
