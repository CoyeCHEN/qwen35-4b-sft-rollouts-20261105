"""Test precise reuse of R86, including unknown failures and changed proof rejection."""
import copy
import datetime
import json
from pathlib import Path

import collection_readiness_r21 as n
import collection_current_setup_blocks_r453 as known
from collection_administrative_ready_r427 import reconcile
from collection_attempts_r8 import attempt_counts
from run_collection_stream_r22 import freeze


def main():
    counts = attempt_counts()
    ready = {}
    for root in n.readiness_roots():
        for path in [*sorted((root/'environment-outcomes').glob('*.json')),*sorted((root/'ready-revisions').glob('*/*.json'))]:
            value = json.loads(path.read_text())
            if value['status'] == 'ENV_READY':
                ready[value['task_id']] = n.normalize_ready(value,path)
    before, _ = reconcile(n.R,ready,known.current_setup_blocks(n.R,ready))
    assert set(before) == {known.IDENT}
    candidate_path = n.R/'stream/official-nop-stall-diagnostic17-r450/READY_CANDIDATE_R452.json'
    assert n.sha(candidate_path) == 'e266ed58a1fa4a6f977d6393b98b5464444c68dd4885cb26d78d3b3d4cad4ce9'
    candidate = json.loads(candidate_path.read_text())
    proposed = dict(ready, **{known.IDENT:candidate})
    after, administrative = reconcile(n.R,proposed,known.current_setup_blocks(n.R,proposed))
    assert not after and len(administrative) == 5
    rejected = []
    variants = [('invented-nop-reward',{'nop_reward':1}),('fabricated-nop-completion',{'original_nop_verifier_completed':True}),
        ('other-engine',{'engine_id':'unknown'}),('other-config',{'deployment_config_sha256':'0'*64}),
        ('different-nop-trial',{'native_nop_trial':'/invalid/no-native-trial'})]
    other_task = copy.deepcopy(candidate)
    other_task['admitted_task']['image_id'] = 'sha256:'+'0'*64
    for label,update in variants:
        value = dict(candidate,**update)
        try:
            known.current_setup_blocks(n.R,dict(ready,**{known.IDENT:value}))
        except (ValueError,KeyError,FileNotFoundError):
            rejected.append(label)
        else:
            raise AssertionError('Unsafe known-verifier receipt accepted: '+label)
    try:
        known.current_setup_blocks(n.R,dict(ready,**{known.IDENT:other_task}))
    except ValueError:
        rejected.append('other-task-image')
    else:
        raise AssertionError('Changed image accepted')
    original_hash = known.sha
    review = json.loads((n.R/'checks/known-verifier-cleanup-revalidation-r452.json').read_text())
    for path in review['source_files']:
        try:
            known.sha = lambda source, target=path: '0'*64 if str(source)==target else original_hash(source)
            try:
                known.current_setup_blocks(n.R,proposed)
            except ValueError:
                rejected.append('source-identity:'+path)
            else:
                raise AssertionError('Changed native evidence accepted')
        finally:
            known.sha = original_hash
    original = known.original_blocks
    base = original(n.R,{key:value for key,value in proposed.items() if key != known.IDENT})
    later = copy.deepcopy(base)
    later[known.IDENT]['native_result_sha256'] = 'f'*64
    try:
        known.original_blocks = lambda root, rows: copy.deepcopy(later)
        actual = known.current_setup_blocks(n.R,proposed)
        assert known.IDENT in actual, 'A new actual setup failure must stay blocked'
    finally:
        known.original_blocks = original
    assert attempt_counts() == counts
    report = dict(passed=True,checked_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        previous_review_sha256=known.PREVIOUS_SHA,renewed_review_sha256=known.REVIEW_SHA,
        helper_source_sha256=n.sha(n.R/'scripts/collection_current_setup_blocks_r453.py'),
        candidate_sha256=n.sha(candidate_path),known_exact_task_accepted=True,new_real_setup_failure_still_blocked=True,
        negative_cases_rejected=rejected,original_timeout_and_absent_reward_preserved=True,
        original_task_tests_and_teacher_success_conditions_unchanged=True,actual_or_conservative_attempts=sum(counts.values()),
        model_calls=0,teacher_dispatches=0,ready_published=False)
    freeze(n.R/'checks/KNOWN_VERIFIER_READY_ACCEPTANCE_R456.json',report)
    print(json.dumps(dict(passed=True,negative_cases=len(rejected),current_blocks_before=len(before),
        current_blocks_with_validated_candidate=len(after),ready_published=False,model_calls=0)))


if __name__=='__main__':
    main()
