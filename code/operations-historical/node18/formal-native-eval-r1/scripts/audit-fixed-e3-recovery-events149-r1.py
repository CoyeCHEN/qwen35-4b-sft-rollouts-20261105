"""Readonly real-model evidence of separated context-overflow recoveries."""
import hashlib,json,time
from collections import Counter
from pathlib import Path
from foundation.ai.utils.errors import isContextOverflow
from foundation.rollouts.export import loadValue
R=Path('/home/chenkeyi/.local/share/harbor-rsi/qwen35-new772-tb21-20261101')
def sha(path):
 h=hashlib.sha256()
 with path.open('rb')as f:
  for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
 return h.hexdigest()
def main():
 rows=[]
 for task in ['llm-inference-batching-scheduler','extract-moves-from-video']:
  trial=R/'jobs/qwen35-new772-new-m1-epoch3-fixed-diagnostic'/(task+'__new-m1-e3-fixed-r1')
  result=trial/'result.json';before=sha(result);root=trial/'agent/openharness-rollout'
  starts={};calls=[];counts=Counter();compactions=[];digest=hashlib.sha256()
  for line in(root/'events.jsonl').open('rb'):
   digest.update(line);e=json.loads(line);d=e['data'];kind=e['type'];counts[kind]+=1
   if kind=='call_start':starts[d['call_id']]=d['source']
   elif kind=='call_end'and starts[d['call_id']]=='agent':
    response=loadValue(d.get('response'),root/'artifacts')or{}
    calls.append(dict(call_id=d['call_id'],time=e['timestamp'],stop=response.get('stopReason'),
     is_context_overflow=isContextOverflow(response,262144)))
   elif 'compact'in kind or kind=='context_event':
    compactions.append(dict(type=kind,time=e['timestamp'],data={k:v for k,v in d.items()if k in ['reason','willRetry','status','summary_call_id','type','action']}))
  overflow=[i for i,v in enumerate(calls)if v['is_context_overflow']]
  episodes=[]
  for a,b in zip(overflow,overflow[1:]):
   normal=[x for x in calls[a+1:b]if x['stop']in ['stop','toolUse']]
   after=[x for x in calls[b+1:]if x['stop']in ['stop','toolUse']]
   if normal:episodes.append(dict(first_overflow_call=calls[a]['call_id'],later_independent_overflow_call=calls[b]['call_id'],
    normal_tool_use_between=sum(x['stop']=='toolUse'for x in normal),normal_stop_between=sum(x['stop']=='stop'for x in normal),
    complete_assistant_after_later_overflow=bool(after),first_complete_after_later_overflow=after[0]if after else None))
  assert before==sha(result)
  original=json.loads(result.read_text());artifact=json.loads((trial/'agent/artifact.json').read_text())
  assert artifact['wheel_sha256']=='1d27eef1ca6696275f306d8c653f7a266a4c7aea7321f0d47fd01b739c27fa18'
  rows.append(dict(task_id=task,trial_name=trial.name,result_sha256=before,events_sha256=digest.hexdigest(),
   wheel_sha256=artifact['wheel_sha256'],agent_calls_completed=len(calls),context_overflow_calls=len(overflow),
   independent_recovery_episodes=episodes,compaction_events=compactions,event_counts=dict(counts),
   raw_reward=(original.get('verifier_result')or{}).get('rewards'),
   raw_exception=(original.get('exception_info')or{}).get('exception_type'),
   qualified_task_success_not_claimed=True))
 value=dict(at=time.time(),kind='ACTUAL_REPAIRED_WHEEL_NATIVE_MODEL_CONTEXT_RECOVERY',trials=rows,
  independent_later_overflow_recovered_count=sum(e['complete_assistant_after_later_overflow']for r in rows for e in r['independent_recovery_episodes']),
  readonly=True,new_model_or_tool_calls=0,original_result_reward_recorder_or_exit_modified=False,
  source_sha256=sha(Path(__file__)))
 p=R/'checks/ACTUAL_FIXED_E3_CONTEXT_RECOVERY_R1.json';assert not p.exists();p.write_text(json.dumps(value,indent=2)+'\n');print(json.dumps(value))
if __name__=='__main__':main()
