"""Eight identity-bound service failures; never rewrite original scores or usage."""
import hashlib
import json
from pathlib import Path

R=Path('/home/chenkeyi/.local/share/harbor-rsi/qwen35-new-cf500-tmax500-20261029')
REGISTRY=R/'checks/TEACHER_SERVICE_HTTP402_TRIALS_R400.json'
EXPECTED='0db83f189950f0837734c14310d7d220fe5383e1ccdb69659561ff421586f8fe'
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
if sha(REGISTRY)!=EXPECTED:raise ValueError('Exact reviewed service failure scope changed')
DOC=json.loads(REGISTRY.read_text())
CASES={x['trial_id']:x for x in DOC['trials']}
if len(CASES)!=8:raise ValueError('Unexpected reviewed service failure scope')


def apply_service_failure(record):
 case=CASES.get(record['trial_id'])
 if case is None:return record
 if record['qualified_success'] or record['is_primary_trajectory']:raise ValueError('Never replace a qualified success with a service classification')
 if record['task_id']!=case['task_id'] or record['pool']!='tmax' or record['result_path']!=case['result_path'] or record['result_sha256']!=case['result_sha256']:
  raise ValueError('Reviewed service failure refers to another Task or Result')
 if sha(case['result_path'])!=case['result_sha256'] or sha(case['recorder_path'])!=case['recorder_sha256']:
  raise ValueError('Original service failure Result or Recorder changed')
 if record['raw_reward']!=(case['native_raw_reward'] or {}).get('reward') or record['native_exception']!=case['native_exception_type']:
  raise ValueError('Original service failure score or exception identity differs')
 for error in case['provider_errors']:
  if error['provider']!='deepseek' or error['model']!='deepseek-flash' or error['status']!='error' or error['stopReason']!='error' or 'HTTP 402' not in error['errorMessage'] or 'Insufficient Balance' not in error['errorMessage']:
   raise ValueError('Evidence does not prove the reviewed existing service failure')
 return dict(record,classification='TEACHER_SERVICE_HTTP402_INSUFFICIENT_BALANCE',
  failure_origin='AUTHORIZED_MODEL_SERVICE',provider_failure_evidence=dict(registry=str(REGISTRY),registry_sha256=EXPECTED,
   recorder=str(case['recorder_path']),recorder_sha256=case['recorder_sha256'],call_ids=[x['call_id'] for x in case['provider_errors']]),
  actual_model_request_attempt_retained=True,original_native_infrastructure_errors_unchanged=True)
