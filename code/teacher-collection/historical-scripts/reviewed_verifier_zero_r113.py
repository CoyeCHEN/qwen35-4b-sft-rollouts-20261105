"""Apply only three hash-bound reviews of existing official zeroes."""
import functools
import hashlib
import json
from pathlib import Path

R=Path('/home/chenkeyi/.local/share/harbor-rsi/qwen35-new-cf500-tmax500-20261029')
MANIFEST=R/'checks/COMPLETED_VERIFIER_ZERO_REVIEWS_R113.json'
MANIFEST_SHA='f635364bbbf38162df78435f55c4ba2a7eff95f41bbed731afc1d73112954619'


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


@functools.cache
def reviews():
    if sha(MANIFEST)!=MANIFEST_SHA:raise ValueError('Completed-zero review manifest changed')
    value=json.loads(MANIFEST.read_text());result={}
    for item in value['reviews']:
        path=Path(item['path'])
        if not path.is_relative_to(R/'checks/completed-verifier-zero-reviews-r113') or sha(path)!=item['sha256']:
            raise ValueError('Completed-zero review identity changed')
        row=json.loads(path.read_text())
        if row['trial_id']!=item['trial_id'] or row['trial_id'] in result:raise ValueError('Review Trial identity repeats or differs')
        result[row['trial_id']]=(row,path,item['sha256'])
    if len(result)!=3:raise ValueError('The exact reviewed trial set changed')
    return result


def apply_reviewed_zero(record):
    item=reviews().get(record['trial_id'])
    if item is None:return record
    review,path,digest=item
    if any(record[key]!=review[key] for key in ['trial_id','pool','task_id','result_path','result_sha256']):
        raise ValueError('Review belongs to another original Result')
    if record['classification']!=review['previous_classification'] or record['raw_reward']!=0 or not record['verifier_actually_completed']:
        raise ValueError('Review would replace a different qualification or reward')
    if record['qualified_success'] or record['is_primary_trajectory'] or record['native_exception'] or record['infrastructure_errors']:
        raise ValueError('Review is not an unqualified completed official zero')
    for file,key in [(Path(review['result_path']),'result_sha256'),(Path(review['verifier_stdout']),'verifier_stdout_sha256'),(Path(review['reward_path']),'reward_sha256')]:
        if sha(file)!=review[key]:raise ValueError('Reviewed raw native evidence changed')
    return dict(record,classification=review['classification'],
        completed_verifier_zero_review=str(path),completed_verifier_zero_review_sha256=digest,
        verifier_failure_scope=review['failure_scope'],scoring_interpretation=review['scoring_interpretation'],
        observed_missing_task_dependency=review['module'],official_reward_unmodified=True)
