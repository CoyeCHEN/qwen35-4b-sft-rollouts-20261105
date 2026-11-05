"""Freeze a deployment candidate; never grant teacher admission authority."""
import copy
import hashlib
import json
from pathlib import Path
import shlex
import subprocess

R = Path('/home/chenkeyi/.local/share/harbor-rsi/qwen35-new-cf500-tmax500-20261029')


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def freeze(p, value):
    p.parent.mkdir(parents=True, exist_ok=True)
    if p.exists():
        if json.loads(p.read_text()) != value:
            raise ValueError('Existing candidate differs: ' + str(p))
    else:
        with p.open('x') as f:
            json.dump(value, f, indent=2)


def main():
    old_path = R / 'configs/campaign-deployment17-r9.json'
    old = json.loads(old_path.read_text())
    cfg = copy.deepcopy(old)
    def remote(code):
        result = subprocess.run([*old['ssh'], old['host'], shlex.join([old['python17'], '-c', code])],
            text=True, capture_output=True, check=True, timeout=60)
        return json.loads(result.stdout)
    seed_path = old['runtime']['ssd_root'] + '/verifier-public-python-r59/PUBLIC_PYTEST_VOLUME.json'
    seed = remote('import json;from pathlib import Path;print(Path(' + repr(seed_path) + ').read_text())')
    if seed['status'] != 'PUBLIC_LIBRARY_VOLUME_SEEDED_NATIVE_ACCEPTANCE_PENDING' or seed['verified_files'] != 540 or seed['engine_id'] != old['runtime']['engine_id']:
        raise ValueError('Public package volume lacks its exact seeded identity')
    helper = R / 'scripts/campaign_image17_r10.py'
    helper17 = old['image_helper'].replace('campaign_image17_r9.py', helper.name)
    subprocess.run(['rsync', '-a', '-e', shlex.join(old['ssh']), str(helper), old['host'] + ':' + helper17], check=True, timeout=120)
    actual = remote('import hashlib,json;from pathlib import Path;print(json.dumps({"sha256":hashlib.sha256(Path(' + repr(helper17) + ').read_bytes()).hexdigest()}))')
    if actual['sha256'] != sha(helper):
        raise ValueError('Node17 helper copy differs')
    proxy_plan = R / 'manifests/VERIFIER_PUBLIC_PROXY_CANDIDATES_R55.json'
    proxy = json.loads(proxy_plan.read_text())
    cases = {x['task_id']: dict(verifier_env=proxy['verifier_public_dependency_env'],
        public_dependency_kind='VERIFIER_ONLY_PUBLIC_PACKAGE_PROXY', source_evidence=str(proxy_plan), source_evidence_sha256=sha(proxy_plan)) for x in proxy['tasks']}
    cargo_path = R / 'configs/private17-cargo-public-proxy-r62.json'
    freeze(cargo_path, {'services': {'main': {'environment': {'CARGO_HTTP_PROXY': 'http://172.17.0.1:49179'}}}})
    cases['task_009221_2c5f3e9f'] = dict(public_dependency_kind='CARGO_ONLY_PUBLIC_PACKAGE_PROXY',
        extra_docker_compose=[dict(path=str(cargo_path), sha256=sha(cargo_path))],
        model_transport_uses_cargo_http_proxy=False)
    python_path = R / 'configs/private17-public-pytest310-r62.json'
    freeze(python_path, {'services': {'main': {'volumes': ['public_verifier_python:/harbor/public-verifier-python:ro']}},
        'volumes': {'public_verifier_python': {'external': True, 'name': seed['volume']}}})
    cases['task_007141_26892089'] = dict(public_dependency_kind='PUBLIC_PYTEST_FOR_ORIGINAL_PYTHON310',
        extra_docker_compose=[dict(path=str(python_path), sha256=sha(python_path))],
        verifier_env={'PYTHONPATH': '/harbor/public-verifier-python', 'PYTHONDONTWRITEBYTECODE': '1'},
        public_python={key: seed[key] for key in ['volume', 'manifest', 'manifest_sha256']},
        seed_receipt=seed_path, original_python_unchanged=True)
    cfg.update(revision='r10', deployment_revision='r10', controller_root=str(R/'stream/collection-r4/deployment-r10'),
        readiness_root=str(R/'stream/collection-r4/deployment-r10-readiness'), image_helper=helper17,
        image_helper_sha256=sha(helper), previous_deployment_config=str(old_path), previous_deployment_config_sha256=sha(old_path),
        task_public_dependencies=cases,
        legacy_readiness=dict(config=str(old_path), sha256=sha(old_path), roots=[*old['legacy_readiness']['roots'], old['readiness_root'], old['controller_root']]),
        public_dependency_policy='Only explicitly listed public package dependencies. No global teacher HTTP proxy; original Tasks, tests, images, resources, deadlines and model transport unchanged. Candidate configuration is not dispatch authority.')
    target = R / 'configs/campaign-deployment17-r10.json'
    freeze(target, cfg)
    print(json.dumps(dict(config=str(target), config_sha256=sha(target), task_ids=sorted(cases), teacher_dispatches=0, admission_authority_granted=False)))


if __name__ == '__main__':
    main()
