"""Activate measured read-only reconciliation before publishing the exact Ready."""
import datetime
import json
from pathlib import Path
import subprocess

import collection_readiness_r21 as n
import collection_current_setup_blocks_r453 as known
from collection_attempts_r8 import attempt_counts
from run_collection_stream_r22 import freeze


def main():
    R = n.R
    counts = attempt_counts()
    review = json.loads((R/'checks/monitor-known-verifier-r454-source-equivalence.json').read_text())
    source = R/'scripts/observe_collection_known_verifier_r454.py'
    canonical = R/'scripts/observe_collection.py'
    resource_path = R/'checks/monitor-known-verifier-r455-resource/result.json'
    resource = json.loads(resource_path.read_text())
    contract_path = R/'checks/KNOWN_VERIFIER_READY_ACCEPTANCE_R456.json'
    contract = json.loads(contract_path.read_text())
    assert review['passed'] and resource['passed'] and resource['wall_seconds'] < 75
    assert n.sha(source) == review['candidate_source_sha256'] == resource['source_sha256']
    assert n.sha(canonical) == review['base_source_sha256'] == '3702c4bcdf58b2bd741bbde943578db195727b4c22b6e4485024e6b06f0d5c82'
    assert contract['passed'] and contract['helper_source_sha256'] == n.sha(R/'scripts/collection_current_setup_blocks_r453.py') == review['helper_source_sha256']
    reconstructed = source.read_text().replace("['R22','R21','R20'","['R21','R20'").replace('from collection_current_setup_blocks_r453 import current_setup_blocks','from collection_current_setup_blocks_r293 import current_setup_blocks')
    assert reconstructed == (R/'scripts/observe_collection_drained_r428.py').read_text()
    candidate_path = R/'stream/official-nop-stall-diagnostic17-r450/READY_CANDIDATE_R452.json'
    assert n.sha(candidate_path) == contract['candidate_sha256']
    candidate = json.loads(candidate_path.read_text())
    assert known.IDENT not in known.current_setup_blocks(R,{known.IDENT:candidate})
    state = subprocess.run(['systemctl','--user','is-active','qwen35-tb21-monitor.service'],capture_output=True,text=True).stdout.strip()
    assert state == 'inactive', 'Let the existing shared observation finish first'
    for process in Path('/proc').iterdir():
        if not process.name.isdigit():
            continue
        try:
            argv = (process/'cmdline').read_bytes().split(b'\0')
        except OSError:
            continue
        assert str(canonical).encode() not in argv, 'Do not publish while an old observer is still reading'
    temporary = canonical.with_suffix('.r457.pending')
    temporary.write_bytes(source.read_bytes())
    temporary.replace(canonical)
    published = n.D/'ready-revisions/known-verifier-revalidation-r452'/(known.IDENT+'.json')
    freeze(published,candidate)
    assert n.sha(published) == n.sha(candidate_path) and attempt_counts() == counts
    out = dict(passed=True,checked_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        source_sha256=n.sha(source),helper_source_sha256=n.sha(R/'scripts/collection_current_setup_blocks_r453.py'),
        resource_proof_sha256=n.sha(resource_path),known_verifier_acceptance_sha256=n.sha(contract_path),
        ready_published=str(published),ready_sha256=n.sha(published),
        original_nop_verifier_completed=False,original_nop_reward=None,teacher_success_not_implied=True,
        existing20minute_timer_shared_service_and_limits_unchanged=True,
        actual_or_conservative_attempts=sum(counts.values()),model_calls=0,teacher_dispatches=0,
        source_sha256_publisher=n.sha(Path(__file__)))
    freeze(R/'checks/KNOWN_VERIFIER_READY_AND_MONITOR_R457_ACTIVE.json',out)
    print(json.dumps(out))


if __name__=='__main__':
    main()
