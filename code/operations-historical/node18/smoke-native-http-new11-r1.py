"""Three explicit native GPU HTTP protocol probes, with real scratch observations."""
import hashlib
import json
from pathlib import Path
import subprocess
import time
import urllib.request

R=Path('/ssd/chenkeyi/qwen35-sft-772-20261101')
P=Path('/data/chenkeyi/qwen35-sft-772-20261101/provenance')
O=R/'smoke/new11-m0-r1'


def digest(value):
    return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True).encode()).hexdigest()


def call(messages,tools,name,index):
    model=str(R/'assets/source17-r1/student-tokenizer')
    payload=dict(model=model,messages=messages,tools=tools,
        tool_choice=dict(type='function',function=dict(name=name)),
        chat_template_kwargs=dict(enable_thinking=True),max_tokens=81920,
        temperature=1.,top_p=.95,top_k=20,min_p=0.,presence_penalty=1.5,
        repetition_penalty=1.,stream=True,stream_options=dict(include_usage=True))
    # Exercise the installed native conversion, including the real sampler's validation.
    from sglang.srt.entrypoints.openai.protocol import ChatCompletionRequest
    from sglang.srt.sampling.sampling_params import SamplingParams
    request=ChatCompletionRequest.model_validate(payload)
    native=request.to_sampling_params(stop=[],model_generation_config={})
    sampler=SamplingParams(**native)
    assert sampler.max_new_tokens==81920 and sampler.top_k==20 and sampler.min_p==0
    assert sampler.presence_penalty==1.5 and sampler.repetition_penalty==1.
    (O/f'call-{index}-request.json').write_text(json.dumps(payload,ensure_ascii=False,indent=2)+'\n')
    req=urllib.request.Request('http://127.0.0.1:18211/v1/chat/completions',
        data=json.dumps(payload,ensure_ascii=False).encode(),headers={'Content-Type':'application/json'})
    thinking='';text='';tools_by_index={};finish=None;usage=None;started=time.time()
    with urllib.request.urlopen(req,timeout=120)as response,(O/f'call-{index}-response.sse').open('wb')as raw:
        for line in response:
            raw.write(line)
            if not line.startswith(b'data:'):continue
            body=line[5:].strip()
            if body==b'[DONE]':break
            item=json.loads(body)
            if item.get('usage'):usage=item['usage']
            for choice in item.get('choices',[]):
                delta=choice.get('delta',{})
                thinking+=delta.get('reasoning_content')or''
                text+=delta.get('content')or''
                for fragment in delta.get('tool_calls')or[]:
                    part=tools_by_index.setdefault(fragment['index'],dict(id='',type='function',function=dict(name='',arguments='')))
                    if fragment.get('id'):part['id']=fragment['id']
                    f=fragment.get('function')or{}
                    part['function']['name']+=f.get('name')or''
                    part['function']['arguments']+=f.get('arguments')or''
                finish=choice.get('finish_reason')or finish
    calls=[tools_by_index[k]for k in sorted(tools_by_index)]
    assert finish=='tool_calls'and len(calls)==1,(finish,calls,text[-300:])
    assert calls[0]['function']['name']==name,calls
    args=json.loads(calls[0]['function']['arguments'])
    from jsonschema import validate
    schema=next(t['function']['parameters']for t in tools if t['function']['name']==name)
    validate(args,schema)
    message=dict(role='assistant',content=text or None,reasoning_content=thinking,tool_calls=calls)
    evidence=dict(tool=name,arguments=args,finish_reason=finish,usage=usage,
        thinking_characters=len(thinking),elapsed_seconds=time.time()-started,
        effective_native_sampling={k:native[k]for k in ['temperature','top_p','top_k','min_p','max_new_tokens','presence_penalty','repetition_penalty']},
        request_sha256=digest(payload),sse_sha256=hashlib.sha256((O/f'call-{index}-response.sse').read_bytes()).hexdigest())
    (O/f'call-{index}-parsed.json').write_text(json.dumps(evidence,ensure_ascii=False,indent=2)+'\n')
    return message,args,evidence


def main():
    O.mkdir(parents=True,exist_ok=False)
    template=json.loads((P/'NEW11_PAYLOAD_TEMPLATE.json').read_text())
    tools=template['tools'];messages=template['system_messages'][:]
    fixture=O/'fixture.txt'
    command="printf 'native-qwen35-protocol-ok\\n' > fixture.txt"
    messages.append(dict(role='user',content='Protocol smoke in '+str(O)+'. Call bash with exactly this command: '+command))
    reply,args,a=call(messages,tools,'bash',1)
    assert args['command']==command,args
    result=subprocess.run(command,shell=True,cwd=O,capture_output=True,text=True,timeout=30)
    assert result.returncode==0
    messages+=[reply,dict(role='tool',tool_call_id=reply['tool_calls'][0]['id'],
        content=json.dumps(dict(exit_code=result.returncode,stdout=result.stdout,stderr=result.stderr)))]
    messages.append(dict(role='user',content='Now call read on the exact absolute path '+str(fixture)+'.'))
    reply,args,b=call(messages,tools,'read',2)
    assert Path(args['path']).resolve()==fixture.resolve(),args
    observation=fixture.read_text();assert observation=='native-qwen35-protocol-ok\n'
    messages+=[reply,dict(role='tool',tool_call_id=reply['tool_calls'][0]['id'],content=observation)]
    messages.append(dict(role='user',content='The actual file check passed. Call finish with a short summary of this protocol smoke.'))
    reply,args,c=call(messages,tools,'finish',3)
    assert args['summary'].strip()
    proof=dict(passed=True,kind='DIRECT_NATIVE_GPU_HTTP_TOOL_PROTOCOL_SMOKE',
        model_path=str(R/'assets/source17-r1/student-tokenizer'),gpu_uuid='GPU-9d89f519-51e1-68e2-b522-6e8c1bdc1130',
        calls=[a,b,c],real_tool_observations=True,tools_exposed=len(tools),
        new_user_and_tool_rounds=True,all_responses_streamed=True,
        scope='Cold-loaded M0 native SGLang parsing and three explicit HTTP probes; not a Harbor Trial, Verifier result, or full Harness agent closure proof',
        official_task_or_verifier_used=False)
    (O/'DIRECT_NATIVE_TOOL_PROTOCOL_SMOKE.json').write_text(json.dumps(proof,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(proof,ensure_ascii=False),flush=True)


if __name__=='__main__':main()
