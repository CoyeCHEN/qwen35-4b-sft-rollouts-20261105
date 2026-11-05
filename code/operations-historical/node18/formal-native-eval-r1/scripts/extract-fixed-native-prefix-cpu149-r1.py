"""Copy three actual completed calls for a CPU-only alias/prefix regression."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import urllib.request

R = Path('/home/chenkeyi/.local/share/harbor-rsi/qwen35-new772-tb21-20261101')
CODE = r'''
from pathlib import Path
import json,sys
from foundation.rollouts.export import loadValue
root=Path(sys.argv[1]);starts={};payloads={};rows=[]
with(root/'events.jsonl').open('rb')as stream:
 for line in stream:
  if line[-1:]!=bytes([10]):break
  event=json.loads(line);data=event['data'];kind=event['type']
  if kind=='call_start':starts[data['call_id']]=data['source']
  elif kind=='call_payload'and starts.get(data['call_id'])=='agent':payloads[data['call_id']]=loadValue(data['payload'],root/'artifacts')
  elif kind=='call_end'and starts.get(data['call_id'])=='agent':
   response=loadValue(data.get('response'),root/'artifacts')or{}
   if response.get('stopReason')not in('toolUse','stop'):continue
   payload=payloads[data['call_id']];assert 'model'in payload
   thinking=''.join(x['thinking']for x in response['content']if x['type']=='thinking')
   text=''.join(x['text']for x in response['content']if x['type']=='text');calls=[]
   for part in response['content']:
    if part['type']=='toolCall':calls.append(dict(id=part['id'],type='function',function=dict(name=part['name'],arguments=json.dumps(part['arguments'],ensure_ascii=False))))
   assistant=dict(role='assistant',content=text,reasoning_content=thinking)
   if calls:assistant['tool_calls']=calls
   rows.append(dict(call_id=data['call_id'],context_fidelity='provider_payload',provider_payload=payload,assistant_response=assistant,actual_prompt_tokens=response['usage']['input']+response['usage'].get('cacheRead',0)))
   if len(rows)==3:break
assert len(rows)==3
print(json.dumps(rows,ensure_ascii=False))
'''


def main():
    output = R / 'checks/formal-alias-prefix-cpu-r1'
    assert not output.exists()
    trial = R / 'jobs/qwen35-new772-new-m1-epoch3-fixed-diagnostic/llm-inference-batching-scheduler__new-m1-e3-fixed-r1'
    assert (trial / 'result.json').exists(), 'Use the completed native Recorder on149'
    assert json.loads((trial / 'agent/artifact.json').read_text())['wheel_sha256'] == '1d27eef1ca6696275f306d8c653f7a266a4c7aea7321f0d47fd01b739c27fa18'
    command = [str(R.parent / 'qwen35-m1-m2-tb21-20261026/venv/bin/python'), '-c', CODE,
               str(trial / 'agent/openharness-rollout')]
    result = subprocess.run(command, capture_output=True, text=True, timeout=40)
    if result.returncode:
        raise RuntimeError(result.stderr[-2000:])
    rows = json.loads(result.stdout)
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open('http://172.17.0.1:18303/model_info', timeout=10) as response:
        info = json.loads(response.read())
    assert info['weight_version'] == '2e02fec581cbb3c802cd1e0e80ac2c9568bead3a9002338f4d661ea6ac94053d'
    binding = dict(model_id=rows[0]['provider_payload']['model'], tokenizer_model_path=info['model_path'],
                   actual_model_info=info, weight_version=info['weight_version'],
                   model_manifest=info['model_path'] + '/EPOCH_MODEL_EXPORT_COMPLETE.json')
    output.mkdir()
    values = {'RESOLVED_NATIVE_CALLS.json': rows, 'SERVING_MODEL_BINDING.json': binding,
              'config.json': dict(model=dict(id=binding['model_id']))}
    for name, value in values.items():
        path = output / name
        path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
        path.chmod(0o600)
    (output / 'EXTRACTOR_SOURCE.py').write_bytes(Path(__file__).read_bytes())
    print(json.dumps(dict(path=str(output),actual_model_alias=binding['model_id'],calls=len(rows),
          source_trial='llm-inference-batching-scheduler__new-m1-e3-fixed-r1',new_model_calls=0,
          source_recorder_unmodified=True,source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())))


if __name__ == '__main__':
    main()
