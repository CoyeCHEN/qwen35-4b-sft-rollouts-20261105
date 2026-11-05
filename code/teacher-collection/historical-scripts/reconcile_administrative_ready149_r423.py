"""Retain billing-drain failures but restore their unchanged verified environments."""
import datetime
import json
from pathlib import Path

import collection_readiness_r21 as n
from collection_attempts_r8 import attempt_counts


def main():
 controller=Path(n.DEPLOYMENT['controller_root'])
 drain=controller/'DRAIN_REQUESTED.json'
 request=json.loads(drain.read_text())
 assert request['reason']=='AUTHORIZED_TEACHER_SERVICE_HTTP402_INSUFFICIENT_BALANCE'
 counts_before=attempt_counts()
 events=[json.loads(line) for line in (n.R/'stream/collection-r4/teacher-lifecycle.jsonl').open()]
 admitted={x['trial_name'] for x in events if x['event']=='TEACHER_ADMITTED'}
 cases={}
 unresolved={}
 positives={}
 for root in n.readiness_roots():
  for path in [*sorted((root/'environment-outcomes').glob('*.json')),*sorted((root/'ready-revisions').glob('*/*.json'))]:
   raw=json.loads(path.read_text())
   if raw['status']=='ENV_READY':positives.setdefault(raw['task_id'],[]).append((path,raw))
 for p in (controller/'setup-failures').glob('*.json'):
  failed=json.loads(p.read_text());trial=Path(failed['native_result']).parent
  result=json.loads((trial/'result.json').read_text());error=result.get('exception_info') or {}
  if error.get('exception_type')!='ValueError' or error.get('exception_message')!='Admission drained before agent run':continue
  assert result.get('finished_at') and not result.get('agent_execution') and trial.name not in admitted
  assert not (trial/'agent/openharness-rollout/events.jsonl').exists()
  ident=failed['task_id'];candidates=[]
  for path,raw in positives.get(ident,[]):
    row=n.normalize_ready(raw,path)
    if row.get('engine_id')!=n.NODE['engine_id'] or row.get('deployment_config_sha256')!=n.CONFIG_SHA:continue
    assert n.sha(Path(row['placement']))==row['placement_sha256']
    for kind in ['install','nop']:
     source=Path(row['native_'+kind+'_trial'])/'result.json'
     assert n.sha(source)==row[kind+'_result_sha256']
     native=json.loads(source.read_text());assert not native.get('exception_info') and not native.get('infrastructure_errors')
     if kind=='nop':assert native['verifier']['finished_at'] and native['verifier_result']['rewards']['reward'] in [0,1]
    candidates.append((path,row))
  if not candidates:
   unresolved[ident]='Verified source receipt not found; administrative failure retained without a Ready claim'
   continue
  path,row=candidates[-1]
  updated=dict(row,administrative_admission_reconciliation=dict(reason='Native billing drain rejected AgentStart before model execution; no environment failure',
    original_ready_receipt=str(path),original_ready_receipt_sha256=n.sha(path),original_administrative_result=str(trial/'result.json'),
    original_administrative_result_sha256=n.sha(trial/'result.json'),drain_request_sha256=n.sha(drain),new_teacher_attempts=0))
  receipt=n.D/'ready-revisions/administrative-billing-drain-r423'/(ident+'.json')
  assert not receipt.exists()
  cases[ident]=(receipt,updated)
 assert len(cases)+len(unresolved)==5 and cases
 for receipt,updated in cases.values():n.freeze(receipt,updated)
 assert attempt_counts()==counts_before and n.sha(drain)==n.sha(controller/'DRAIN_REQUESTED.json')
 out=dict(checked_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),passed=True,reconciled_verified_environments=len(cases),unresolved=unresolved,
  cases={ident:dict(receipt=str(path),sha256=n.sha(path)) for ident,(path,_) in cases.items()},
  original_failures_results_recorders_and_ready_receipts_preserved=True,model_attempt_counter_changed=False,
  provider_balance_drain_still_active=True,model_calls=0,teacher_dispatches=0,source_sha256=n.sha(Path(__file__)))
 n.freeze(n.R/'checks/ADMINISTRATIVE_READY_RECONCILIATION_R423.json',out)
 print(json.dumps(out))


if __name__=='__main__':main()
