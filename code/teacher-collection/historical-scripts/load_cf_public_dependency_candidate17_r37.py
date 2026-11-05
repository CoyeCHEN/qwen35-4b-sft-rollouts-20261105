"""Validate exact public dependency lineage before loading one candidate on17."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tarfile


R = Path('/home/chenkeyi/workspace/RSI/runtime-evidence/qwen35-new-cf500-tmax500-20261029')
S = Path('/ssd/chenkeyi/qwen35-new-cf500-tmax500-20261029')


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def config(archive):
    with tarfile.open(archive, 'r') as tar:
        index = json.loads(tar.extractfile('index.json').read())
        descriptor, = index['manifests']
        raw = tar.extractfile('blobs/sha256/' + descriptor['digest'].split(':')[1]).read()
        if hashlib.sha256(raw).hexdigest() != descriptor['digest'].split(':')[1]:
            raise ValueError('Manifest changed')
        manifest = json.loads(raw)
        raw = tar.extractfile('blobs/sha256/' + manifest['config']['digest'].split(':')[1]).read()
        if hashlib.sha256(raw).hexdigest() != manifest['config']['digest'].split(':')[1]:
            raise ValueError('Image config changed')
        return descriptor['digest'], manifest, json.loads(raw)


def main():
    request = json.load(sys.stdin)
    if sha(Path(__file__)) != request['helper_sha256']:
        raise ValueError('Candidate loader source changed')
    deployment = request['deployment']
    if deployment['engine_id'] != '59c8ba22-0aa4-4aed-bc43-4e1b5989fa22' or deployment['socket'] != str(S / 'engine17-r1/socket/docker.sock'):
        raise ValueError('Candidate belongs to another Engine or storage')
    docker = ['docker', '--host', 'unix://' + deployment['socket']]
    engine = subprocess.run(docker + ['info', '--format', '{{.ID}}'], check=True, capture_output=True, text=True).stdout.strip()
    if engine != deployment['engine_id']:
        raise ValueError('Actual private Engine differs')
    parent = json.loads(subprocess.run(['docker', 'inspect', deployment['parent_container']],
        check=True, capture_output=True, text=True).stdout)[0]
    mounts = {item['Destination']:item['Source'] for item in parent['Mounts']}
    if mounts.get('/var/lib/docker') != deployment['docker_root'] or mounts.get('/var/lib/containerd') != deployment['containerd_root']:
        raise ValueError('Private Engine layers escaped the accepted SSD mounts')
    receipt = Path(request['build_receipt'])
    if not receipt.is_relative_to(S / 'cf-verifier-public-dependency-r36') or sha(receipt) != request['build_receipt_sha256']:
        raise ValueError('Frozen candidate receipt changed')
    candidate = json.loads(receipt.read_text())
    if candidate['status'] != 'CANDIDATE_PUBLIC_VERIFIER_DEPENDENCIES_BUILT_NATIVE_ACCEPTANCE_PENDING' or candidate['accepted_by_current_controller']:
        raise ValueError('Unexpected candidate status')
    if sha(R / 'scripts/build_cf_public_verifier_dependencies17_r36.py') != candidate['builder_source_sha256']:
        raise ValueError('Frozen candidate builder changed')
    original_receipt = Path(candidate['source']['original_cache_receipt'])
    if sha(original_receipt) != candidate['source']['original_cache_receipt_sha256']:
        raise ValueError('Published source image receipt changed')
    original = json.loads(original_receipt.read_text())
    old_archive = Path(original['archive'])
    archive = Path(candidate['archive'])
    if not archive.is_relative_to(S) or not old_archive.is_relative_to(S):
        raise ValueError('Candidate/source archive escaped SSD')
    if sha(archive) != candidate['archive_sha256'] or sha(old_archive) != original['archive_sha256']:
        raise ValueError('Candidate/source archive bytes changed')
    old_id, old_manifest, old_cfg = config(old_archive)
    new_id, new_manifest, new_cfg = config(archive)
    if old_id != original['image_id'] or new_id != candidate['image_id']:
        raise ValueError('Declared exact image identity changed')
    before = old_cfg['config']
    after = new_cfg['config']
    keys = ['Env', 'Cmd', 'Entrypoint', 'WorkingDir', 'User', 'ExposedPorts', 'Volumes', 'StopSignal', 'Healthcheck']
    if any(before.get(key) != after.get(key) for key in keys):
        raise ValueError('Public dependency layer changed runtime/agent environment config')
    old_labels = before.get('Labels') or {}
    new_labels = after.get('Labels') or {}
    if any(new_labels.get(key) != value for key, value in old_labels.items()):
        raise ValueError('Original image labels changed')
    if set(new_labels) - set(old_labels) - {'rsi.campaign', 'rsi.public-verifier-dependency-setup'}:
        raise ValueError('Unexpected added image label')
    original_layers = old_cfg['rootfs']['diff_ids']
    if new_cfg['rootfs']['diff_ids'][:len(original_layers)] != original_layers:
        raise ValueError('The original root filesystem is not an exact prefix')
    image_audit = receipt.parent / 'image-audit.json'
    audit = json.loads(image_audit.read_text())
    if sha(image_audit) != candidate['image_audit_sha256'] or not audit['all_original_manifest_config_layer_and_diffid_hashes_verified']:
        raise ValueError('Candidate full layer/diffID proof changed')
    subprocess.run(docker + ['image', 'load', '--input', str(archive)],
        check=True, capture_output=True, text=True, timeout=1200)
    actual = json.loads(subprocess.run(docker + ['image', 'inspect', new_id],
        check=True, capture_output=True, text=True).stdout)[0]
    if actual['Id'] != new_id:
        raise ValueError('Load did not preserve candidate identity')
    print(json.dumps(dict(status='EXACT_PUBLIC_DEPENDENCY_CANDIDATE_LOADED_NOT_ADMITTED',
        task_id=candidate['task_id'], image_id=new_id, original_image_id=old_id,
        original_rootfs_diffid_prefix_preserved=True, runtime_environment_config_unchanged=True,
        original_compressed_layer_digest_prefix_preserved=[x['digest'] for x in new_manifest['layers'][:len(old_manifest['layers'])]] == [x['digest'] for x in old_manifest['layers']],
        archive_sha256=candidate['archive_sha256'], build_receipt_sha256=request['build_receipt_sha256'],
        engine_id=engine, model_calls=0, original_task_or_test_changes=0,
        current_controller_ready_publications=0, helper_sha256=sha(Path(__file__)))))


if __name__ == '__main__':
    main()
