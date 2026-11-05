"""Read-only acceptance of exact service-error labels and an unchanged success path."""
import copy
import datetime
import hashlib
import json
from pathlib import Path

import reviewed_teacher_service_failure_r408 as review

R=review.R
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()


def main():
 old=(R/'scripts/audit_collection_results_r11.py').read_text()
 new=(R/'scripts/audit_collection_results_r13.py').read_text()
 assert new.replace('\nfrom reviewed_teacher_service_failure_r408 import apply_service_failure','').replace('            record=apply_service_failure(record)\n','')==old
 worker=(R/'scripts/audit_stream_data_worker149_r13.py').read_text()
 assert worker.replace("source_revision='r13'","source_revision='r12'").replace('logs/stream-r13-data-audit.log','logs/stream-r12-data-audit.log').replace("script('audit_collection_results_r13.py')","script('audit_collection_results_r11.py')").replace("'stream-r13-'+ident","'stream-r12-'+ident")== (R/'scripts/audit_stream_data_worker149_r12.py').read_text()
 entries=[];indexes={}
 for pool in ['CALIBFORGE','TMAX']:
  for kind in ['SUCCESS_INDEX','FAILURE_OR_PENDING_INDEX']:
   p=R/'indexes'/(pool+'_'+kind+'.jsonl');indexes[str(p)]=sha(p)
   entries.extend(json.loads(line) for line in p.open())
 positives=[x for x in entries if x['qualified_success']]
 for row in positives:assert review.apply_service_failure(row) is row
 cases={x['trial_id']:x for x in entries if x['trial_id'] in review.CASES}
 assert len(cases)==8
 rejected=0
 for ident,row in cases.items():
  result=review.apply_service_failure(row)
  assert result['classification']=='TEACHER_SERVICE_HTTP402_INSUFFICIENT_BALANCE' and not result['qualified_success'] and not result['is_primary_trajectory']
  assert {k:v for k,v in result.items() if k in row and k!='classification'}=={k:v for k,v in row.items() if k!='classification'}
  for key,value in [('qualified_success',True),('is_primary_trajectory',True),('result_sha256','incorrect'),('task_id','another-task'),('raw_reward','incorrect'),('native_exception','another-exception')]:
   bad=copy.deepcopy(row);bad[key]=value
   try:review.apply_service_failure(bad)
   except ValueError:rejected+=1
   else:raise AssertionError('Unsafe service label accepted: '+key)
 unknown=dict(next(iter(cases.values())),trial_id='not-in-reviewed-scope')
 assert review.apply_service_failure(unknown) is unknown
 assert all(sha(Path(p))==digest for p,digest in indexes.items())
 sources={name:sha(R/'scripts'/name) for name in ['reviewed_teacher_service_failure_r408.py','audit_collection_results_r13.py','audit_stream_data_worker149_r13.py','audit_stream_data_worker149_r12.py','audit_collection_results_r11.py']}
 value=dict(passed=True,checked_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),sources=sources,
  cases=[dict(proof=str(review.REGISTRY),sha256=sha(review.REGISTRY))],exact_negative_trials=8,
  unchanged_qualified_trajectories=len(positives),unsafe_mutations_rejected=rejected,unknown_trials_unchanged=True,
  full_prior_qualification_source_unchanged_except_exact_negative_review=True,
  raw_results_rewards_recorders_or_model_attempt_counts_modified=False,teacher_calls=0,
  source_sha256=sha(Path(__file__)))
 p=R/'checks/SERVICE_FAILURE_DATA_WRITER_ACCEPTANCE_R409.json'
 with p.open('x') as f:json.dump(value,f,indent=2)
 print(json.dumps(value))


if __name__=='__main__':main()
