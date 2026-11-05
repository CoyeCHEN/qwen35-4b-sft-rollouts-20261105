"""Resolve an explicitly requested image identity using verified SSD archives.

Size proofs are keyed by Task, exact image and archive SHA. Historical r1
proofs stay immutable. Only two separately approved public-dependency image
derivations are accepted; this module never builds or substitutes an image.
"""
import json
from pathlib import Path
import re
import sys

from inspect_cold_oci_r1 import S, inspect_archive, publish, sha_file


R = Path('/home/chenkeyi/workspace/RSI/runtime-evidence/qwen35-new-cf500-tmax500-20261029')


def approved_candidate(task_id, image_id, declaration):
    path = Path(declaration['path'])
    if not path.is_relative_to(S) or sha_file(path) != declaration['sha256']:
        raise ValueError('Campaign public dependency bindings changed')
    manifest = json.loads(path.read_text())
    if manifest['engine_id'] != '59c8ba22-0aa4-4aed-bc43-4e1b5989fa22' or manifest['model_calls'] != 0:
        raise ValueError('Public dependency bindings belong to another Engine or scope')
    if not 1 <= len(manifest['bindings']) <= 2:
        raise ValueError('Unexpected public dependency correction scope')
    value = manifest['bindings'].get(task_id)
    if value is None or value['image_id'] != image_id:
        return None
    if value['official_task_or_test_changes'] or not value['original_base_layers_and_runtime_config_preserved']:
        raise ValueError('Candidate changed the official Task or runtime contract')
    source_receipt = Path(value['original_cache_receipt'])
    if sha_file(source_receipt) != value['original_cache_receipt_sha256']:
        raise ValueError('Original public image identity receipt changed')
    original = json.loads(source_receipt.read_text())
    if original['image_id'] != value['original_published_image_id']:
        raise ValueError('Candidate published-image lineage differs')
    if set(value['native_results']) != {'install', 'nop'}:
        raise ValueError('Both original native install and official verifier evidence are required')
    for kind, record in value['native_results'].items():
        path = Path(record['node17_result'])
        if not path.is_relative_to(S) or sha_file(path) != record['result_sha256']:
            raise ValueError('Approved native acceptance Result changed')
        result = json.loads(path.read_text())
        if result.get('exception_info') or result.get('infrastructure_errors') or not result.get('finished_at'):
            raise ValueError('Candidate native lifecycle was not accepted')
        if kind == 'nop' and (not (result.get('verifier') or {}).get('finished_at')
                or (result.get('verifier_result') or {}).get('rewards', {}).get('reward') != 0):
            raise ValueError('Candidate original official NOP verifier did not finish')
    proof_path = Path(value['image_audit'])
    if not proof_path.is_relative_to(S) or sha_file(proof_path) != value['image_audit_sha256']:
        raise ValueError('Candidate full image-integrity proof changed')
    proof = json.loads(proof_path.read_text())
    if proof['image_id'] != image_id or proof['archive_sha256'] != value['archive_sha256']:
        raise ValueError('Approved exact candidate archive identity differs')
    if not proof['all_original_manifest_config_layer_and_diffid_hashes_verified']:
        raise ValueError('Candidate archive layers were not fully verified')
    return proof['archive'], proof['archive_sha256']


def resolve(task_id, image_id, pool, approved_bindings):
    if not re.fullmatch(r'[a-zA-Z0-9_-]+', task_id) or not re.fullmatch(r'sha256:[0-9a-f]{64}', image_id):
        raise ValueError('Invalid frozen Task/image identity')
    choices = []
    if pool == 'calibforge':
        candidate = approved_candidate(task_id, image_id, approved_bindings)
        if candidate is not None:
            choices.append(candidate)
        else:
            for name in ['tasks-local-skopeo-r1', 'tasks']:
                path = S / 'registry' / name / task_id / 'cache.json'
                if path.exists():
                    value = json.loads(path.read_text())
                    if value.get('status') != 'PINNED_PUBLIC_IMAGE_ARCHIVE_READY' or value['image_id'] != image_id:
                        raise ValueError('Requested image is neither the frozen published image nor its approved exact candidate')
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
                    raise ValueError('Registered original-context recovery changed its source')
                value = recovered
            if (value.get('status') == 'ORIGINAL_NATIVE_OCI_ARCHIVE_BUILT_INITIAL_AND_VERIFIER_TESTS_PENDING'
                    and value['source_context']['task_id'] == task_id
                    and value['native_manifest_digest'] == image_id):
                choices.append((value['archive'], value['archive_sha256']))
            # A failed/different build is not evidence about another exact
            # historical image. Only its independently verified archive can
            # satisfy that original identity; no rebuild or alias is inferred.
    else:
        raise ValueError('Unknown frozen source pool')
    backup = S / 'cold-images-from149-r1' / pool / task_id / image_id.split(':')[1] / 'image-audit.json'
    if not choices and backup.exists():
        value = json.loads(backup.read_text())
        if value['image_id'] != image_id or not value['all_original_manifest_config_layer_and_diffid_hashes_verified']:
            raise ValueError('Exact historical image archive is invalid')
        choices.append((value['archive'], value['archive_sha256']))
    if len(choices) != 1:
        raise FileNotFoundError('No archive for the explicitly requested exact image; never rebuild implicitly')
    archive, archive_sha = choices[0]
    if not re.fullmatch(r'[0-9a-f]{64}', archive_sha) or not Path(archive).is_relative_to(S):
        raise ValueError('Invalid archive identity or storage boundary')
    receipt = S / 'cold-image-sizes-r2' / task_id / image_id.split(':')[1] / (archive_sha + '.json')
    if receipt.exists():
        proof = json.loads(receipt.read_text())
        if proof['image_id'] != image_id or proof['archive_sha256'] != archive_sha or proof['archive'] != archive:
            raise ValueError('Immutable exact image/archive size proof differs')
    else:
        proof = inspect_archive(archive, image_id, archive_sha)
        publish(receipt, proof)
    if not Path(archive).is_file():
        raise FileNotFoundError('Verified exact cold archive is missing')
    return proof


if __name__ == '__main__':
    request = json.load(sys.stdin)
    print(json.dumps(resolve(request['task_id'], request['image_id'], request['pool'], request['approved_bindings'])))
