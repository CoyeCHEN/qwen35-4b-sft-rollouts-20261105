"""Add two verified public APT mirror bindings to a new, inactive deployment."""
import copy
import json
from pathlib import Path
import collection_readiness_r17 as old

R=old.R
scope=R/'stream/signed-debian-mirror-diagnostic17-r214'
document=json.loads((scope/'TERMINAL.json').read_text())
assert len(document['outcomes'])==2 and document['model_calls']==0
cfg=copy.deepcopy(old.DEPLOYMENT)
cases=cfg['task_public_dependencies']
approved=[]
for item in document['outcomes']:
    ident=item['task_id']
    if item['status']!='SIGNED_DEBIAN_MIRROR_DIAGNOSTIC_PASSED_NATIVE_INSTALL_NOP_STILL_REQUIRED' or not item['native_cleanup_complete']:
        raise ValueError('Public package diagnosis did not pass')
    if ident in cases:raise ValueError('Do not replace an existing Task public dependency binding')
    source,=item['sources'];before=Path(source['original']);after=Path(source['candidate'])
    assert old.sha(before)==source['original_sha256'] and old.sha(after)==source['candidate_sha256']
    expected=before.read_text()
    for origin in ['http://deb.debian.org/','https://deb.debian.org/','http://security.debian.org/','https://security.debian.org/']:
        expected=expected.replace(origin,'https://mirrors.tuna.tsinghua.edu.cn/')
    if after.read_text()!=expected or 'Signed-By:' not in expected:raise ValueError('APT signature policy or additional configuration changed')
    for step in item['steps']:
        if step['return_code'] or old.sha(Path(step['log']))!=step['sha256']:raise ValueError('Public bootstrap evidence changed')
    compose=R/'configs'/('private17-signed-debian-mirror-r219-'+ident+'.json')
    old.freeze(compose,dict(services=dict(main=dict(volumes=[dict(type='bind',source=str(after),target=source['container_path'],
        read_only=True,bind=dict(create_host_path=False))]))))
    proof=scope/ident/'TERMINAL.json'
    cases[ident]=dict(public_dependency_kind='SIGNED_DEBIAN_TUNA_HTTPS_MIRROR',
        extra_docker_compose=[dict(path=str(compose),sha256=old.sha(compose))],
        original_apt_source_sha256=source['original_sha256'],candidate_apt_source_sha256=source['candidate_sha256'],
        diagnostic_proof=str(proof),diagnostic_proof_sha256=old.sha(proof),
        original_trusted_keyring_and_signatures_unchanged=True,model_transport_or_proxy_changed=False)
    approved.append(ident)
cfg.update(revision='r18',deployment_revision='r18',controller_root=str(R/'stream/collection-r4/deployment-r18'),
    readiness_root=str(R/'stream/collection-r4/deployment-r18-readiness'),previous_deployment_config=str(old.CONFIG),
    previous_deployment_config_sha256=old.CONFIG_SHA,previous_public_image_bindings_mirror149=cfg['public_image_bindings_mirror149'],
    new_native_acceptance_required_task_ids=sorted(approved),
    legacy_readiness=dict(config=str(old.CONFIG),sha256=old.CONFIG_SHA,roots=[str(p) for p in old.readiness_roots()]),
    public_dependency_policy='Only two explicit read-only APT source bindings. Same signed Debian suites/components/keyring; official image, Task, tests, resources, deadlines, model transport and existing bindings unchanged. New native install/NOP required before admission.')
target=R/'configs/campaign-deployment17-r18.json';old.freeze(target,cfg)
old.freeze(R/'checks/signed-debian-deployment-r219.json',dict(config=str(target),sha256=old.sha(target),
    source_sha256=old.sha(Path(__file__)),task_ids=sorted(approved),teacher_admission_granted=False,model_calls=0))
print(json.dumps(dict(config=str(target),sha256=old.sha(target),tasks=sorted(approved),teacher_admission_granted=False)))
