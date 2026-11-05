"""Read-only OCI identity and expanded-layer size audit; never extracts files.

Content-addressed layer receipts avoid re-expanding shared public dependencies.
Archive, manifest, config, compressed layer and DiffID hashes are all checked.
"""
from pathlib import Path
import argparse
import gzip
import hashlib
import json
import os
import tarfile
from uuid import uuid4

S = Path('/ssd/chenkeyi/qwen35-new-cf500-tmax500-20261029')


def sha_file(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def publish(path, value):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(value, sort_keys=True, indent=2) + '\n'
    temporary = path.with_name(path.name + '.' + uuid4().hex + '.partial')
    temporary.write_text(data)
    try:
        try:
            os.link(temporary, path)
        except FileExistsError:
            if json.loads(path.read_text()) != value:
                raise ValueError('Immutable cold-image audit identity changed: ' + str(path))
    finally:
        temporary.unlink()


def inspect_archive(archive, expected_image_id, expected_archive_sha256, layer_cache=None):
    archive = Path(archive).resolve()
    if not archive.is_relative_to(S):
        raise ValueError('Cold archive is outside the owned SSD root')
    digest = sha_file(archive)
    if expected_archive_sha256 and digest != expected_archive_sha256:
        raise ValueError('Frozen archive SHA mismatch')
    layer_cache = Path(layer_cache or S / 'cold-image-layer-audits-r1')
    with tarfile.open(archive, 'r') as tar:
        def blob(descriptor):
            algorithm, value = descriptor['digest'].split(':')
            if algorithm != 'sha256' or len(value) != 64:
                raise ValueError('Unsupported OCI digest')
            try:
                member = tar.getmember('blobs/sha256/' + value)
            except KeyError as error:
                raise ValueError('Frozen OCI blob is missing') from error
            if not member.isfile() or ('size' in descriptor and member.size != descriptor['size']):
                raise ValueError('OCI descriptor size/type mismatch')
            return member

        def json_blob(descriptor):
            member = blob(descriptor)
            raw = tar.extractfile(member).read()
            if 'sha256:' + hashlib.sha256(raw).hexdigest() != descriptor['digest']:
                raise ValueError('OCI manifest/config SHA mismatch')
            return json.loads(raw)

        top = json_blob(dict(digest=expected_image_id))
        manifest = top
        manifest_id = expected_image_id
        for _ in range(4):
            if 'layers' in manifest:
                break
            choices = [x for x in manifest.get('manifests', []) if x.get('platform', {}).get('os') == 'linux' and x.get('platform', {}).get('architecture') == 'amd64']
            if len(choices) != 1:
                raise ValueError('Need one exact linux/amd64 native manifest')
            manifest_id = choices[0]['digest']; manifest = json_blob(choices[0])
        else:
            raise ValueError('OCI index nesting exceeded supported image layout')
        config = json_blob(manifest['config'])
        if config.get('os') != 'linux' or config.get('architecture') != 'amd64':
            raise ValueError('Original image platform differs from accepted native runtime')
        differences = config['rootfs']['diff_ids']
        if len(differences) != len(manifest['layers']):
            raise ValueError('Original layer and DiffID lists differ')
        layers = []
        for descriptor, expected_diff_id in zip(manifest['layers'], differences):
            member = blob(descriptor)
            with tar.extractfile(member) as stream:
                compressed_sha = 'sha256:' + hashlib.file_digest(stream, 'sha256').hexdigest()
            if compressed_sha != descriptor['digest']:
                raise ValueError('Original compressed layer SHA mismatch')
            cache = layer_cache / (descriptor['digest'].split(':')[1] + '.json')
            if cache.exists():
                layer = json.loads(cache.read_text())
                if layer['digest'] != descriptor['digest'] or layer['diff_id'] != expected_diff_id or layer['compressed_bytes'] != member.size or layer['media_type'] != descriptor['mediaType']:
                    raise ValueError('Content-addressed layer proof differs')
            else:
                media = descriptor['mediaType']
                with tar.extractfile(member) as raw:
                    if media.endswith('+gzip') or media.endswith('.gzip'):
                        stream = gzip.GzipFile(fileobj=raw)
                    elif media.endswith('.tar'):
                        stream = raw
                    else:
                        raise ValueError('Unsupported original layer compression: ' + media)
                    expanded = hashlib.sha256(); count = 0
                    for block in iter(lambda: stream.read(1024**2), b''):
                        expanded.update(block); count += len(block)
                    if 'sha256:' + expanded.hexdigest() != expected_diff_id:
                        raise ValueError('Original expanded layer DiffID mismatch')
                layer = dict(digest=descriptor['digest'], diff_id=expected_diff_id, media_type=media,
                    compressed_bytes=member.size, expanded_tar_bytes=count)
                publish(cache, layer)
            layers.append(layer)
    return dict(status='ORIGINAL_COLD_IMAGE_FULLY_HASHED', image_id=expected_image_id,
        native_manifest_digest=manifest_id, config_digest=manifest['config']['digest'],
        archive=str(archive), archive_sha256=digest, archive_bytes=archive.stat().st_size,
        expanded_layer_tar_bytes=sum(x['expanded_tar_bytes'] for x in layers), layers=layers,
        all_original_manifest_config_layer_and_diffid_hashes_verified=True,
        filesystem_extractions=0, model_calls=0, task_modifications=0,
        inspector_sha256=sha_file(Path(__file__)))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive'); parser.add_argument('image_id'); parser.add_argument('archive_sha256')
    parser.add_argument('output')
    args = parser.parse_args()
    result = inspect_archive(args.archive, args.image_id, args.archive_sha256)
    publish(Path(args.output), result)
    print(json.dumps({k: result[k] for k in ['status', 'image_id', 'archive_sha256', 'expanded_layer_tar_bytes']}))
