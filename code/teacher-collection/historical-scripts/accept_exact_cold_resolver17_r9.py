"""Exercise exact original/candidate identities and reject corrupt evidence."""
import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import time

import resolve_cold_image17_r2 as resolver


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def main():
    declaration = json.loads(sys.argv[1])
    source = Path(resolver.__file__)
    old = resolver.R / 'checks/cold-image-sizes-r1/task_003872_36777bc0.json'
    original_old_sha = sha(old)
    cases = [
        ('optimization_20260604_194036_001', 'calibforge', 'sha256:2a305e2c2317f4affee0b64a862269bc2ae9f8e2fb94a57450f27128b85677c0'),
        ('optimization_20260604_194036_001', 'calibforge', 'sha256:9363a56e38051c358de68a8c894ffd8b72e40d7a82c53b7be06c1dc76165c921'),
        ('system-administration_20260510_062946_002', 'calibforge', 'sha256:4a6ccad17d9b897028f5bd4103d43d09aaa379cf10eba548cad08b6a213bf865'),
        ('system-administration_20260510_062946_002', 'calibforge', 'sha256:2566f33d4300bed3ef9d79a674b2e3f570b94c81145c7554382637fa66f678d9'),
        ('task_003872_36777bc0', 'tmax', 'sha256:e1da46ad0d427877052cde54b4fceccc3fabd14b6bb8849bd69d88be5f41f594'),
        ('task_003872_36777bc0', 'tmax', 'sha256:d3800c600be9ebd9f8a866258f0156ddae47ab7df328031ae2c29e047c2b43ab'),
    ]
    passed = []
    started = time.monotonic()
    for task, pool, image in cases:
        proof = resolver.resolve(task, image, pool, declaration)
        assert proof['image_id'] == image and proof['all_original_manifest_config_layer_and_diffid_hashes_verified']
        passed.append(dict(task_id=task, image_id=image, archive_sha256=proof['archive_sha256']))
    assert sha(old) == original_old_sha
    manifest = json.loads(Path(declaration['path']).read_text())
    task = cases[1][0]
    image = cases[1][2]
    rejected = []
    with tempfile.TemporaryDirectory(prefix='exact-image-acceptance-r9-', dir=resolver.S) as temporary:
        directory = Path(temporary)

        def rejects(label, document):
            path = directory / (label + '.json')
            path.write_text(json.dumps(document))
            record = dict(path=str(path), sha256=sha(path))
            try:
                resolver.resolve(task, image, 'calibforge', record)
            except ValueError:
                rejected.append(label)
            else:
                raise AssertionError('Invalid native approval accepted: ' + label)

        bad = copy.deepcopy(manifest)
        bad['bindings'][task]['official_task_or_test_changes'] = 1
        rejects('changed-official-task', bad)
        bad = copy.deepcopy(manifest)
        bad['bindings'][task]['native_results'].pop('nop')
        rejects('missing-official-verifier', bad)
        bad = copy.deepcopy(manifest)
        bad['bindings'][task]['native_results']['nop']['result_sha256'] = '0' * 64
        rejects('corrupt-native-result-sha', bad)
        bad = copy.deepcopy(manifest)
        result = json.loads(Path(bad['bindings'][task]['native_results']['nop']['node17_result']).read_text())
        result['verifier_result']['rewards']['reward'] = 1
        path = directory / 'changed-nop-reward-result.json'
        path.write_text(json.dumps(result))
        bad['bindings'][task]['native_results']['nop'].update(node17_result=str(path), result_sha256=sha(path))
        rejects('unsolved-nop-not-zero', bad)
        bad = copy.deepcopy(manifest)
        bad['bindings'][task]['native_results']['nop']['node17_result'] = '/outside-owned-ssd/result.json'
        rejects('native-result-outside-ssd', bad)
        bad = copy.deepcopy(manifest)
        bad['bindings'][task]['image_audit_sha256'] = '0' * 64
        rejects('corrupt-image-integrity-proof', bad)
    try:
        resolver.resolve(task, 'sha256:' + '0' * 64, 'calibforge', declaration)
    except ValueError:
        rejected.append('unapproved-image-identity')
    else:
        raise AssertionError('Unapproved image accepted')
    proof = dict(passed=True, checked_source_sha256=sha(source), positive_exact_identities=passed,
        rejected_corrupt_or_unapproved_evidence=rejected, old_single_task_receipt_sha256=original_old_sha,
        old_receipt_unchanged=sha(old) == original_old_sha, proof_cache_root=str(resolver.S / 'cold-image-sizes-r2'),
        total_seconds=time.monotonic() - started, model_calls=0, image_builds=0, image_loads=0)
    path = resolver.S / 'deployment-r9/exact-cold-resolver-acceptance-r9.json'
    with path.open('x') as stream:
        json.dump(proof, stream, indent=2)
    print(json.dumps(proof))


if __name__ == '__main__':
    main()
