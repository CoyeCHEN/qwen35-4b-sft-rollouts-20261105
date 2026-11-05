"""Refresh the already reviewed exact R86 NOP limitation after clean CLI recovery."""
import datetime
import json
from pathlib import Path
import re

import collection_readiness_r21 as n
from collection_attempts_r8 import attempt_counts
from collection_selection_r7 import active_rows
from run_collection_stream_r22 import freeze

IDENT = 'task_008794_911eb529'
R = n.R
S = R/'stream/official-nop-stall-diagnostic17-r450'
PREVIOUS = R/'checks/original-verifier-failure-cleanup-review-r86.json'
PREVIOUS_SHA = '0a5bb6d31c968e3519389fc5e704dfde0a6fc18d0de7b50828800aef1c651181'
REVIEW = R/'checks/known-verifier-cleanup-revalidation-r452.json'
read = lambda path: json.loads(path.read_text())


def main():
    counts = attempt_counts()
    assert counts[IDENT] == 1 and sum(counts.values()) == 1273
    assert not REVIEW.exists()
    assert n.sha(PREVIOUS) == PREVIOUS_SHA
    previous = read(PREVIOUS)
    assert previous['task_id'] == IDENT and previous['original_nop_reward'] is None
    assert previous['original_nop_verifier_completed'] is False
    plan, terminal = read(S/'PLAN.json'), read(S/'TERMINAL.json')
    assert plan['source_sha256'] == n.sha(R/'scripts/diagnose_official_nop_stall149_r450.py')
    assert plan['engine_id'] == n.NODE['engine_id'] and plan['deployment_config_sha256'] == n.CONFIG_SHA
    assert terminal['model_calls'] == terminal['teacher_dispatches'] == 0
    assert terminal['teacher_budget_unchanged'] and terminal['original_sources_unchanged']
    assert terminal['verifier_result'] is None and terminal['exception']['exception_type'] == 'VerifierTimeoutError'
    assert terminal['exception']['exception_message'] == 'Verifier execution timed out after 120.0 seconds'
    assert not terminal['infrastructure_errors']
    task = Path(next(iter(plan['original_sources']))).parent
    assert n.sha(task/'tests/test_final_state.py') == previous['original_verifier_sha256']
    assert n.sha(task/'instruction.md') == previous['original_public_instruction_sha256']
    assert all(n.sha(Path(path)) == digest for path,digest in plan['original_sources'].items())
    static = plan['static_thread_cleanup_evidence']
    assert static['thread_calls'] == [{'line':101,'keywords':['target']}] and static['stop_calls'] == [138]
    assert 110 in static['assert_lines'] and not static['cleanup_finally_blocks']
    live = []
    for path in sorted((S/'live-snapshots').glob('*.json')):
        value = read(path)
        stdout = value.get('official_verifier_stdout',{}).get('stdout','')
        threads = value.get('process_threads',{}).get('stdout','')
        commands = value.get('process_commands',{}).get('stdout','')
        match = re.search(r'\b5 failed in ([\d.]+)s',stdout)
        if not match:
            continue
        assert 'Failed to clone deploy.git.' in stdout
        if 'futex_wait_queue_me' in threads and 'do_poll' in threads and 'python3 -m pytest test_final_state.py -v' in commands:
            live.append(dict(path=str(path),sha256=n.sha(path),observed_at=value['checked_at'],pytest_tests_failed_in_seconds=float(match[1])))
    assert len(live) >= 3
    span=(datetime.datetime.fromisoformat(live[-1]['observed_at'])-datetime.datetime.fromisoformat(live[0]['observed_at'])).total_seconds()
    assert span > 60
    initial = read(S/'initial-outcome.json')
    assert initial['initial_state_returncode'] == 0 and initial['cleanup_confirmed']
    assert initial['actual_resources']['cpu_max'] == '100000 100000' and initial['actual_resources']['memory_max'] == '2147483648'
    assert initial['engine_id'] == n.NODE['engine_id'] and initial['status'] == 'ORIGINAL_TASK_INITIAL_RESOURCES_NETWORK_ACCEPTED'
    install = R/'stream/public-cpython-native-setup-recovery17-r394/trials/task_008794_911eb529__aYgiQwH'
    install_result = read(install/'result.json')
    assert n.sha(install/'result.json') == '8967023f3d551db10079f5a7bb9e5eb058ca384c3b97b389cf53e1f40cc2c49f'
    assert not install_result.get('exception_info') and not install_result['infrastructure_errors'] and install_result['agent_setup']['finished_at']
    assert read(install/'config.json')['install_only'] is True
    assert not (install/'agent/openharness-rollout/events.jsonl').exists()
    nop = Path(terminal['native_trial'])
    assert n.sha(nop/'result.json') == terminal['result_sha256']
    assert read(nop/'config.json')['agent']['name'] == 'nop'
    assert not (nop/'agent/openharness-rollout/events.jsonl').exists()
    failed = R/'stream/collection-r4/trials/task_008794_911eb529__ZMkRYhD/result.json'
    assert n.sha(failed) == '82a70cd3965fb36b5c861c82b0ee19b393a0bdff602759bb51498df4f5d68dad'
    assert read(failed).get('agent_execution') is None
    assert datetime.datetime.fromisoformat(install_result['finished_at'].replace('Z','+00:00')) > datetime.datetime.fromisoformat(read(failed)['finished_at'].replace('Z','+00:00'))
    source_files = {str(PREVIOUS):PREVIOUS_SHA, **plan['original_sources']}
    source_files.update({str(path):n.sha(path) for path in [S/'PLAN.json',S/'TERMINAL.json',S/'initial-outcome.json',S/'ssd-archive.json',install/'result.json',nop/'result.json',failed]})
    source_files.update({entry['path']:entry['sha256'] for entry in live})
    review = dict(task_id=IDENT,pool='tmax',status='EXISTING_R86_LIMITATION_REVALIDATED_REQUIRES_READY_PUBLICATION',
        checked_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),source_sha256=n.sha(Path(__file__)),
        previous_review=str(PREVIOUS),previous_review_sha256=PREVIOUS_SHA,source_files=source_files,
        deployment_config_sha256=n.CONFIG_SHA,engine_id=n.NODE['engine_id'],native_install_trial=str(install),native_nop_trial=str(nop),
        source_native_setup_failure=str(failed),source_native_setup_failure_sha256=n.sha(failed),
        original_nop_verifier_completed=False,original_nop_reward=None,original_verifier_timeout_sec=120,
        live_tests_finished_but_unstopped_thread_span_seconds=span,live_snapshots=live,
        teacher_actual_or_conservative_attempts_before_review=counts[IDENT],actual_or_conservative_attempts=sum(counts.values()),
        existing_research_exception_scope_unchanged=True,official_task_tests_resources_and_reward_unmodified=True,
        model_calls=0,teacher_dispatches=0,teacher_success_not_implied=True,
        reason='Reuse the exact already accepted R86 limitation for this fixed Task and unchanged official test. Fresh original initial resources and CLI installation passed. All5 tests fail on the unsolved Goal before cleanup; the unjoined non-daemon SMTP thread keeps pytest alive. Preserve the official120s timeout and absent NOP Reward. No teacher or success qualification rule is relaxed.')
    freeze(REVIEW,review)
    row = next(value for value in active_rows(counts) if value['task_id'] == IDENT)
    admitted = n.prepare_identity(row)
    ready = dict(task_id=IDENT,pool='tmax',status='ENV_READY',admitted_task=admitted,engine_id=n.NODE['engine_id'],
        deployment_config_sha256=n.CONFIG_SHA,placement=admitted['deployment_assignment'],placement_sha256=admitted['deployment_assignment_sha256'],
        raw_outcome=str(REVIEW),raw_outcome_sha256=n.sha(REVIEW),nop_reward=None,original_nop_verifier_completed=False,
        preflight_exception='ORIGINAL_VERIFIER_THREAD_CLEANUP_ON_UNSOLVED_GOAL',teacher_success_not_implied=True,
        native_install_trial=str(install),install_result_sha256=n.sha(install/'result.json'),native_nop_trial=str(nop),nop_result_sha256=n.sha(nop/'result.json'),
        reason=review['reason'],model_calls=0,teacher_dispatches=0)
    freeze(S/'READY_CANDIDATE_R452.json',ready)
    assert attempt_counts() == counts
    print(json.dumps(dict(review=str(REVIEW),review_sha256=n.sha(REVIEW),candidate=str(S/'READY_CANDIDATE_R452.json'),
        candidate_sha256=n.sha(S/'READY_CANDIDATE_R452.json'),ready_published=False,model_calls=0,live_span=span)))


if __name__=='__main__':
    main()
