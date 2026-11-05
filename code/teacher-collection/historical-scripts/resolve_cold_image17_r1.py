"""Resolve one exact native image archive, with full hash/expanded-size evidence."""
from pathlib import Path
import json
import re
import sys
from inspect_cold_oci_r1 import S, inspect_archive, publish, sha_file

R = Path('/home/chenkeyi/workspace/RSI/runtime-evidence/qwen35-new-cf500-tmax500-20261029')


def resolve(task_id, image_id, pool):
    if not re.fullmatch(r'[a-zA-Z0-9_-]+', task_id) or not re.fullmatch(r'sha256:[0-9a-f]{64}', image_id):
        raise ValueError('Invalid frozen image identity')
    choices = []
    if pool == 'calibforge':
        for name in ['tasks-local-skopeo-r1', 'tasks']:
            path = S / 'registry' / name / task_id / 'cache.json'
            if path.exists():
                value = json.loads(path.read_text())
                if value.get('status') != 'PINNED_PUBLIC_IMAGE_ARCHIVE_READY' or value['image_id'] != image_id:
                    raise ValueError('Frozen public image receipt differs; no fallback')
                choices.append((value['archive'], value['archive_sha256']))
                break
    elif pool == 'tmax':
        path = S / 'buildkit-rootless-r2/archives' / task_id / 'client-proxy-r3/build.json'
        if path.exists():
            value = json.loads(path.read_text())
            registered = R / 'checks/tmax-original-build-network-recovery-r5' / (task_id + '.json')
            if registered.exists():
                recovery = json.loads(registered.read_text())
                replacement = Path(recovery['recovery_build_receipt'])
                if (recovery['kind'] != 'EXPLICIT_ORIGINAL_CONTEXT_NETWORK_RECOVERY'
                        or recovery['task_id'] != task_id
                        or value['status'] != 'NATIVE_SSD_BUILD_FAILED'
                        or sha_file(path) != recovery['original_failed_build_sha256']
                        or replacement != path.parent.parent / 'network-recovery-r5/build.json'
                        or sha_file(replacement) != recovery['recovery_build_receipt_sha256']):
                    raise ValueError('Registered original network-recovery identity differs')
                recovered = json.loads(replacement.read_text())
                if recovered['source_context'] != value['source_context']:
                    raise ValueError('Network recovery changed original native source context')
                value = recovered
            if value['status'] != 'ORIGINAL_NATIVE_OCI_ARCHIVE_BUILT_INITIAL_AND_VERIFIER_TESTS_PENDING' or value['source_context']['task_id'] != task_id:
                raise ValueError('Original native Task image build is not verified')
            if value['native_manifest_digest'] == image_id:
                choices.append((value['archive'], value['archive_sha256']))
    else:
        raise ValueError('Unknown frozen source pool')
    backup = S / 'cold-images-from149-r1' / pool / task_id / image_id.split(':')[1] / 'image-audit.json'
    if not choices and backup.exists():
        value = json.loads(backup.read_text())
        if value['image_id'] != image_id or not value['all_original_manifest_config_layer_and_diffid_hashes_verified']:
            raise ValueError('Exact native backup receipt is invalid')
        choices.append((value['archive'], value['archive_sha256']))
    if len(choices) != 1:
        raise FileNotFoundError('No exact verified cold image; never rebuild implicitly')
    receipt = R / 'checks/cold-image-sizes-r1' / (task_id + '.json')
    archive, archive_sha = choices[0]
    if receipt.exists():
        proof = json.loads(receipt.read_text())
        if proof['image_id'] != image_id or proof['archive_sha256'] != archive_sha:
            raise ValueError('Immutable image-size proof differs')
    else:
        proof = inspect_archive(archive, image_id, archive_sha)
        publish(receipt, proof)
    if not Path(archive).is_file():
        raise FileNotFoundError('Verified cold archive is missing')
    return proof


if __name__ == '__main__':
    request = json.load(sys.stdin)
    print(json.dumps(resolve(request['task_id'], request['image_id'], request['pool'])))
