"""Apply five additional hash-bound log reviews; original official zeroes stay zero."""
import functools
import hashlib
import json
from pathlib import Path
from reviewed_verifier_zero_r113 import apply_reviewed_zero as previous_reviews

R=Path('/home/chenkeyi/.local/share/harbor-rsi/qwen35-new-cf500-tmax500-20261029')
MANIFEST=R/'checks/COMPLETED_VERIFIER_ZERO_REVIEWS_R235.json'
EXPECTED='6cf56735320957a75ccd06db6599f3ce61f080cab968b3a64fd1bff151bb12e8'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()


@functools.cache
def reviews():
    if sha(MANIFEST)!=EXPECTED:raise ValueError('Reviewed original-zero manifest changed')
    output={}
    for entry in json.loads(MANIFEST.read_text())['reviews']:
        path=Path(entry['path'])
        if path.parent!=R/'checks/completed-verifier-zero-reviews-r235' or sha(path)!=entry['sha256']:
            raise ValueError('Reviewed original-zero evidence changed')
        row=json.loads(path.read_text())
        if row['trial_id']!=entry['trial_id'] or row['trial_id'] in output:
            raise ValueError('Duplicate or different reviewed Trial identity')
        output[row['trial_id']]=(row,path,entry['sha256'])
    if len(output)!=5:raise ValueError('The exact five reviewed zeroes changed')
    return output


def apply_reviewed_zero(record):
    record=previous_reviews(record)
    item=reviews().get(record['trial_id'])
    if item is None:return record
    review,path,digest=item
    if any(record[k]!=review[k] for k in ['trial_id','task_id','pool','result_path','result_sha256']):
        raise ValueError('Zero review refers to another original Result')
    if record['classification']!=review['previous_classification'] or record['raw_reward']!=0 or not record['verifier_actually_completed']:
        raise ValueError('Zero review cannot override another outcome')
    if record['qualified_success'] or record['is_primary_trajectory'] or record['native_exception'] or record['infrastructure_errors']:
        raise ValueError('Zero review is not the reviewed completed official zero')
    for key,identity in [('result_path','result_sha256'),('verifier_stdout','verifier_stdout_sha256'),('reward_path','reward_sha256')]:
        if sha(Path(review[key]))!=review[identity]:raise ValueError('Reviewed original verifier evidence changed')
    return dict(record,classification=review['reviewed_classification'],
        completed_verifier_zero_review=str(path),completed_verifier_zero_review_sha256=digest,
        verifier_failure_reason=review['reason'],scoring_infrastructure_failure_detected=review['scoring_infrastructure_failure_detected'],
        official_reward_unmodified=True)
