"""Owned image archive transport using native Docker save/load and existing SSH.

No task scheduling, model calls, rebuilds, force removal or global cache pruning.
"""
from pathlib import Path
import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
from uuid import uuid4

R = Path('/home/chenkeyi/.local/share/harbor-rsi/qwen35-new-cf500-tmax500-20261029')
S17 = '/ssd/chenkeyi/qwen35-new-cf500-tmax500-20261029'
E17 = '/home/chenkeyi/workspace/RSI/runtime-evidence/qwen35-new-cf500-tmax500-20261029'
PY17 = '/home/chenkeyi/workspace/RSI/runtime-evidence/qwen35-length-lf-audit-20261023/.venv/bin/python'
SSH = ['ssh', '-S', '/home/chenkeyi/.ssh/cf17-20261028.sock', '-oBatchMode=yes', '-oProxyCommand=false']
HOST = 'chenkeyi@180.163.192.17'
ENGINE = 'c6e16cdf-e878-4cc5-84c8-78a56c54b5c5'


class ImageCapacityError(RuntimeError):
    """The exact immutable image must wait for bounded storage capacity."""


def run(args, timeout=30, **kwargs):
    return subprocess.run(args, check=True, capture_output=True, text=True, timeout=timeout, **kwargs)


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def image_info(image):
    result = subprocess.run(['docker', 'image', 'inspect', image], capture_output=True, text=True, timeout=30)
    if result.returncode == 0:
        return json.loads(result.stdout)[0]
    if 'No such image' in result.stderr:
        return None
    raise RuntimeError('Native Docker image observation failed')


def validate_identity(task_id, image_id, pool):
    if not re.fullmatch(r'[a-zA-Z0-9_-]+', task_id) or not re.fullmatch(r'sha256:[0-9a-f]{64}', image_id) or pool not in ['calibforge', 'tmax']:
        raise ValueError('Invalid frozen Task/image identity')
    if run(['docker', 'info', '--format', '{{.ID}}']).stdout.strip() != ENGINE:
        raise ValueError('Native149 Docker engine differs')


def archive_image(task_id, image_id, pool, source_identity):
    """Copy the exact original image to17 and fully verify it before publication."""
    validate_identity(task_id, image_id, pool)
    target = R / 'checks/native-cold-image-archives-r1' / (task_id + '.json')
    if target.exists():
        existing = json.loads(target.read_text())
        if existing['image_id'] != image_id or existing['source_identity'] != source_identity:
            raise ValueError('Existing original archive identity differs')
        return existing
    info = image_info(image_id)
    if info is None:
        raise ValueError('Original image is absent; never rebuild it implicitly')
    if pool == 'tmax' and info['Config'].get('Labels', {}).get('rsi.campaign') != R.name:
        raise ValueError('Native TMax image is not owned by this campaign')
    if shutil.disk_usage(R).free < 32 * 1024**3 + 2 * info['Size']:
        raise ImageCapacityError('Insufficient bounded149 image-save headroom')
    transport = R / 'sources/native-cold-image-transfers-r1'; transport.mkdir(exist_ok=True)
    temporary = transport / (task_id + '-' + uuid4().hex + '.tar')
    log = temporary.with_suffix('.save.log')
    with log.open('x') as stream:
        subprocess.run(['docker', 'image', 'save', '--output', str(temporary), image_id],
            stdout=stream, stderr=subprocess.STDOUT, check=True, timeout=1800)
    archive_sha = sha(temporary)
    remote = S17 + '/cold-images-from149-r1/' + pool + '/' + task_id + '/' + image_id.split(':')[1]
    run(SSH + [HOST, 'mkdir -p ' + shlex.quote(remote)], timeout=30)
    archive = remote + '/image.tar'
    run(['rsync', '-a', '--bwlimit=8192', '-e', shlex.join(SSH), str(temporary), HOST + ':' + archive], timeout=3600)
    receipt = remote + '/image-audit.json'
    reply = run(SSH + [HOST, shlex.join([PY17, E17 + '/scripts/inspect_cold_oci_r1.py', archive,
        image_id, archive_sha, receipt])], timeout=1800)
    metadata = run(SSH + [HOST, 'cat ' + shlex.quote(receipt)], timeout=30)
    proof = json.loads(metadata.stdout)
    if proof['image_id'] != image_id or proof['archive_sha256'] != archive_sha or not proof['all_original_manifest_config_layer_and_diffid_hashes_verified']:
        raise ValueError('Original native image archive failed identity verification')
    result = dict(task_id=task_id, pool=pool, image_id=image_id, source_identity=source_identity,
        source_engine=ENGINE, archive=archive, archive_sha256=archive_sha,
        archive_bytes=proof['archive_bytes'], expanded_layer_tar_bytes=proof['expanded_layer_tar_bytes'],
        remote_audit=receipt, remote_audit_sha256=hashlib.sha256(metadata.stdout.encode()).hexdigest(),
        all_original_manifest_config_layer_and_diffid_hashes_verified=True,
        archive_transport='Native Docker save + existing authenticated rsync; no image conversion',
        model_calls=0, task_modifications=0, original_image_retained_149=True)
    target.parent.mkdir(exist_ok=True)
    with target.open('x') as stream:
        stream.write(json.dumps(result, indent=2))
    temporary.unlink()  # Verified identical original archive stays on17 SSD.
    return result


def load_verified_archive(task_id, image_id, pool, receipt, reserve_bytes=32 * 1024**3):
    """Materialize one immutable image before native Harbor environment startup."""
    validate_identity(task_id, image_id, pool)
    if receipt['image_id'] != image_id or not receipt['all_original_manifest_config_layer_and_diffid_hashes_verified']:
        raise ValueError('Cold receipt belongs to another image or is incomplete')
    current = image_info(image_id)
    if current is not None:
        return dict(status='EXACT_IMAGE_ALREADY_RESIDENT', image_id=image_id)
    remote = Path(receipt['archive'])
    if not remote.is_relative_to(Path(S17)) or '..' in remote.parts:
        raise ValueError('Cold image escaped owned remote storage')
    required = reserve_bytes + 2 * receipt['archive_bytes'] + receipt['expanded_layer_tar_bytes']
    if shutil.disk_usage(R).free < required:
        raise ImageCapacityError('Insufficient149 image-load headroom: need ' + str(required))
    directory = R / 'sources/native-cold-image-transfers-r1'; directory.mkdir(exist_ok=True)
    temporary = directory / (task_id + '-' + uuid4().hex + '.tar')
    run(['rsync', '-a', '--bwlimit=8192', '-e', shlex.join(SSH), HOST + ':' + str(remote), str(temporary)], timeout=3600)
    if sha(temporary) != receipt['archive_sha256']:
        raise ValueError('Cold image transport SHA mismatch; retain evidence, no fallback')
    with temporary.with_suffix('.load.log').open('x') as stream:
        subprocess.run(['docker', 'image', 'load', '--input', str(temporary)], stdout=stream,
            stderr=subprocess.STDOUT, check=True, timeout=1800)
    actual = image_info(image_id)
    if actual is None or actual['Id'] != image_id:
        raise ValueError('Native Docker restore changed the frozen image identity')
    temporary.unlink()
    return dict(status='EXACT_COLD_IMAGE_RESTORED', image_id=image_id, archive_sha256=receipt['archive_sha256'])
