"""Add two verified public APT mirror bindings to a new, inactive deployment."""
import copy
import json
from pathlib import Path
import collection_readiness_r20 as old

R=old.R
scope=R/'stream/signed-debian-mirror-diagnostic17-r315'
document=json.loads((scope/'TERMINAL.json').read_text())
assert len(document['outcomes'])==1 and document['model_calls']==0
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
    public_file=R/'configs'/('private17-signed-debian-mirror-r316-'+ident+'.sources')
    if public_file.exists():
        assert old.sha(public_file)==old.sha(after)
    else:
        public_file.write_bytes(after.read_bytes())
    assert old.sha(public_file)==source['candidate_sha256']
    compose=R/'configs'/('private17-signed-debian-mirror-r316-'+ident+'.json')
    old.freeze(compose,dict(services=dict(main=dict(volumes=[dict(type='bind',source=str(public_file),target=source['container_path'],
        read_only=True,bind=dict(create_host_path=False))]))))
    proof=scope/ident/'TERMINAL.json'
    cases[ident]=dict(public_dependency_kind='SIGNED_DEBIAN_TUNA_HTTPS_MIRROR',
        extra_docker_compose=[dict(path=str(compose),sha256=old.sha(compose))],
        original_apt_source_sha256=source['original_sha256'],candidate_apt_source_sha256=source['candidate_sha256'],
        diagnostic_proof=str(proof),diagnostic_proof_sha256=old.sha(proof),
        original_trusted_keyring_and_signatures_unchanged=True,model_transport_or_proxy_changed=False)
    approved.append(ident)
cfg.update(revision='r21',deployment_revision='r21',controller_root=str(R/'stream/collection-r4/deployment-r21'),
    readiness_root=str(R/'stream/collection-r4/deployment-r21-readiness'),previous_deployment_config=str(old.CONFIG),
    previous_deployment_config_sha256=old.CONFIG_SHA,previous_public_image_bindings_mirror149=cfg['public_image_bindings_mirror149'],
    new_native_acceptance_required_task_ids=sorted(approved),
    legacy_readiness=dict(config=str(old.CONFIG),sha256=old.CONFIG_SHA,roots=[str(p) for p in old.readiness_roots()]),
    public_dependency_policy='Preserve all R20 runtime, public CPython cache and Task bindings. Add only one explicit read-only signed Debian HTTPS source for the remaining attempt of machine-learning_20260419_065313_002 after its original verifier bootstrap network failure. Original Task/image/tests/resources/deadlines/model/attempt budget unchanged; new native install/NOP required before admission.')
target=R/'configs/campaign-deployment17-r21.json';old.freeze(target,cfg)
old.freeze(R/'checks/signed-debian-deployment-r316.json',dict(config=str(target),sha256=old.sha(target),
    source_sha256=old.sha(Path(__file__)),task_ids=sorted(approved),teacher_admission_granted=False,model_calls=0))
print(json.dumps(dict(config=str(target),sha256=old.sha(target),tasks=sorted(approved),teacher_admission_granted=False)))
