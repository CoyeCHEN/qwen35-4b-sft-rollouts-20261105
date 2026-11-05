"""Promote the validated derived reader without stopping any native lifecycle."""
import datetime
import hashlib
import json
import os
from pathlib import Path

R = Path('/home/chenkeyi/.local/share/harbor-rsi/qwen35-new-cf500-tmax500-20261029')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    acceptance_path = R / 'checks/protocol-cache-r23-full-scope-acceptance.json'
    acceptance = json.loads(acceptance_path.read_text())
    assert acceptance['passed'] and acceptance['all_seeded_rows_equal_original_full_scan']
    assert acceptance['all_warm_rows_equal_original_full_scan']
    canonical = R / 'scripts/audit_native_canary_protocol.py'
    backup = canonical.with_name('audit_native_canary_protocol_before_r23.py')
    candidate = canonical.with_name('audit_native_canary_protocol_r23.py')
    assert sha(canonical) == sha(backup) == acceptance['baseline_source_sha256']
    assert sha(candidate) == acceptance['producer_source_sha256']
    assert sha(R / 'scripts/protocol_trial_cache_r23.py') == acceptance['cache_source_sha256']
    # A currently loaded old scanner never consults its own source file again.
    assert '__file__' not in backup.read_text()
    for revision in ['deployment-r7b', 'deployment-r8']:
        manifest = json.loads((R / 'stream/collection-r4' / revision / 'CAMPAIGN.json').read_text())
        sources = manifest['helper_sha256']
        assert canonical.name not in sources
        assert all(sha(R / 'scripts' / name) == value for name,value in sources.items())
    worker = Path('/proc/502085')
    assert str(R / 'scripts/audit_stream_data_worker149_r5.py').encode() in (worker / 'cmdline').read_bytes().split(b'\0')
    children = (worker / 'task/502085/children').read_text().split()
    proof_path = R / 'checks/protocol-cache-r23-activation.json'
    if proof_path.exists():
        raise FileExistsError('Existing derived reader promotion preserved')
    temporary = canonical.with_name('.audit_native_canary_protocol_r23.pending')
    temporary.symlink_to(candidate.name)
    os.replace(temporary, canonical)
    assert sha(canonical) == acceptance['producer_source_sha256']
    proof = dict(passed=True, checked_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        activation_source_sha256=sha(Path(__file__)), acceptance=str(acceptance_path),
        acceptance_sha256=sha(acceptance_path), canonical_source_sha256=sha(canonical),
        previous_source_preserved=str(backup), previous_source_sha256=sha(backup),
        cache_source_sha256=acceptance['cache_source_sha256'], existing_data_index_writer_pid=502085,
        data_index_writer_start_ticks=(worker / 'stat').read_text().rsplit(')', 1)[1].split()[19],
        existing_native_reader_children_preserved=list(map(int, children)),
        teacher_controller_or_configuration_changes=0, native_trial_cancellations=0,
        model_calls=0, original_recorders_or_results_changed=0,
        production_cached_report='PENDING_NEXT_EXISTING_WRITER_INVOCATION')
    with proof_path.open('x') as stream:
        json.dump(proof, stream, indent=2)
    print(json.dumps(proof))


if __name__ == '__main__':
    main()
