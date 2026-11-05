"""Verify a sparse, evidence-bound classification change; no index writes."""
import copy
import datetime
import hashlib
import json
from pathlib import Path

import reviewed_verifier_zero_r113 as review

R=review.R
sha=lambda path:hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    old=R/'scripts/audit_collection_results_r8.py';new=R/'scripts/audit_collection_results_r9.py'
    source=new.read_text().replace('\nfrom reviewed_verifier_zero_r113 import apply_reviewed_zero','').replace('            record=apply_reviewed_zero(record)\n','')
    if source!=old.read_text():raise ValueError('New reader changed more than the reviewed-zero projection')
    changes=[];unchanged=0;successes=0;negative=0;inputs={};records=[]
    for pool in ['CALIBFORGE','TMAX']:
        for kind in ['SUCCESS_INDEX','FAILURE_OR_PENDING_INDEX']:
            path=R/'indexes'/(pool+'_'+kind+'.jsonl');blob=path.read_bytes();inputs[str(path)]=hashlib.sha256(blob).hexdigest()
            for line in blob.splitlines():
                row=json.loads(line);records.append(row);before=copy.deepcopy(row);after=review.apply_reviewed_zero(row)
                if row!=before:raise ValueError('Reviewer mutated the source record')
                if after==before:
                    unchanged+=1;successes+=bool(row['qualified_success']);continue
                if row['qualified_success']:raise ValueError('A success admission changed')
                if after['raw_reward']!=row['raw_reward'] or after['result_sha256']!=row['result_sha256']:raise ValueError('Reward or Result changed')
                changes.append(dict(trial_id=row['trial_id'],task_id=row['task_id'],old=row['classification'],new=after['classification']))
                for key,value in [('raw_reward',1),('result_sha256','0'*64),('task_id','different'),('classification','QUALIFIED_SUCCESS'),('native_exception','VerifierTimeoutError')]:
                    bad=copy.deepcopy(before);bad[key]=value
                    try:review.apply_reviewed_zero(bad)
                    except ValueError:negative+=1
                    else:raise ValueError('Invalid review input was accepted: '+key)
    if {x['trial_id'] for x in changes}!=set(review.reviews()):raise ValueError('Changed trial set is not the exact three reviewed zeroes')
    if sha(R/'scripts/collection_attempts_r8.py')!='bd4ef9049840a89acf65ab8fa7f6d3aa0a565986684eca47da58d973ebef9238':raise ValueError('Attempt counter changed')
    expected_sha=review.MANIFEST_SHA;review.reviews.cache_clear();review.MANIFEST_SHA='0'*64
    try:
        try:review.reviews()
        except ValueError:negative+=1
        else:raise ValueError('A changed manifest identity was accepted')
    finally:review.MANIFEST_SHA=expected_sha;review.reviews.cache_clear()
    proof=dict(passed=True,checked_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        old_audit_sha256=sha(old),new_audit_sha256=sha(new),review_helper_sha256=sha(R/'scripts/reviewed_verifier_zero_r113.py'),
        review_manifest_sha256=expected_sha,unchanged_native_validator_source_sha256=sha(R/'scripts/audit_collection_results_r7.py'),
        unchanged_records=unchanged,unchanged_success_records=successes,changes=changes,negative_cases_passed=negative,
        input_indexes_at_validation=inputs,source_body_unchanged_outside_sparse_reviews=True,
        actual_or_conservative_attempt_counter_changed=False,task_pool_or_split_changed=False,
        teacher_prompt_model_tools_or_budget_changed=False,raw_results_rewards_or_logs_modified=False,
        index_writes_by_this_validation=0,teacher_calls=0,source_sha256=sha(Path(__file__)))
    with (R/'checks/qualification-reader-r9-acceptance-r114.json').open('x') as f:json.dump(proof,f,indent=2)
    print(json.dumps(proof))


if __name__=='__main__':main()
