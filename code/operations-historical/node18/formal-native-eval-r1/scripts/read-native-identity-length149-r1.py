from pathlib import Path
from collections import Counter
import json,hashlib,time
from foundation.rollouts.export import loadValue
r=Path('/home/chenkeyi/.local/share/harbor-rsi/qwen35-new772-tb21-20261101');job=r/'jobs/qwen35-new772-new-m1-epoch3-fixed-diagnostic';rows=[]
for name in ['llm-inference-batching-scheduler','extract-moves-from-video']:
 root=job/(name+'__new-m1-e3-fixed-r1')/'agent/openharness-rollout';starts={};counts=Counter();maximums={};examples=[]
 for line in(root/'events.jsonl').open('rb'):
  e=json.loads(line);d=e['data']
  if e['type']=='call_start':starts[d['call_id']]=d['source']
  elif e['type']=='call_end'and starts[d['call_id']]=='agent':
   response=loadValue(d.get('response'),root/'artifacts')or{};u=response.get('usage')or{};n=u.get('input',0)+u.get('cacheRead',0);stop=response.get('stopReason');bucket='le131072'if n<=131072 else('131073to180224'if n<=180224 else'gt180224');counts[(bucket,stop)]+=1;maximums[stop]=max(n,maximums.get(stop,0))
   if stop=='toolUse'and n>131440 and len(examples)<3:examples.append(dict(call_id=d['call_id'],actual_input_tokens=n))
 rows.append(dict(task=name,counts={k+'|'+str(s):v for(k,s),v in counts.items()},maximum_actual_input_by_stop_reason=maximums,completed_toolUse_above_both_error_input_lengths=examples))
proof=dict(kind='READ_ONLY_NATIVE_INPUT_LENGTH_VS_TOOL_IDENTITY_ERRORS',at=time.time(),trials=rows,new_model_calls=0,model_or_serving_causation_claimed=False,raw_evidence_modified=False)
p=r/'checks/NATIVE_TOOL_IDENTITY_LENGTH_READOUT_R1.json';assert not p.exists();p.write_text(json.dumps(proof,indent=2)+'\n');print(json.dumps(proof))
