"""Replay real targets through the existing native SGLang Qwen parsers, CPU only."""
from collections import OrderedDict
import gzip
import hashlib
import inspect
import json
import os
from pathlib import Path

os.environ['CUDA_VISIBLE_DEVICES']=''
from sglang.srt.entrypoints.openai.protocol import Tool
from sglang.srt.function_call.qwen3_coder_detector import Qwen3CoderDetector
from sglang.srt.parser.reasoning_parser import ReasoningParser
from sft.qwen35 import load_tokenizer,normalize_message
from sft.teacher_segments import project_decision

ROOT=Path('/home/chenkeyi/workspace/RSI/runtime-evidence/qwen35-new-cf500-tmax500-20261029')


def main():
    tokenizer=load_tokenizer();records=[]
    for path in sorted((ROOT/'sources/canary-calls').glob('*.jsonl.gz')):
        calls=[json.loads(line) for line in gzip.open(path,'rt')]
        for call in calls:
            decision=project_decision(tokenizer,call);left,right=decision.evidence['supervised_range']
            text=tokenizer.decode(decision.row['input_ids'][left:right],skip_special_tokens=False,clean_up_tokenization_spaces=False)
            if not text.endswith('<|im_end|>\n'):raise ValueError('Unexpected official target ending')
            generated=text[:-len('<|im_end|>\n')]
            expected=normalize_message(call['assistant_response'])
            tools=[Tool.model_validate(x) for x in call['provider_payload']['tools']]
            expected_calls=[dict(name=x['function']['name'],arguments=x['function']['arguments']) for x in expected.get('tool_calls',[])]
            reasoning,body=ReasoningParser(model_type='qwen3',stream_reasoning=True,force_reasoning=True).parse_non_stream(generated)
            parsed=Qwen3CoderDetector().detect_and_parse(body,tools)
            got=[dict(name=x.name,arguments=json.loads(x.parameters)) for x in parsed.calls]
            if got!=expected_calls:raise ValueError('Nonstreaming tool semantics differ: '+call['call_id'])
            if (reasoning or '').strip()!=expected.get('reasoning_content','').strip():raise ValueError('Thinking semantics differ')
            if parsed.normal_text.strip()!=expected['content'].strip():raise ValueError('Visible body semantics differ')
            rp=ReasoningParser(model_type='qwen3',stream_reasoning=True,force_reasoning=True)
            tp=Qwen3CoderDetector();thought=[];normal=[];stream_calls=OrderedDict();offset=0;iteration=0
            sizes=[1,7,31,257,4096]
            while offset<len(generated):
                size=sizes[iteration%len(sizes)];chunk=generated[offset:offset+size];offset+=size;iteration+=1
                r,b=rp.parse_stream_chunk(chunk)
                if r:thought.append(r)
                if b:
                    value=tp.parse_streaming_increment(b,tools)
                    normal.append(value.normal_text)
                    for c in value.calls:
                        part=stream_calls.setdefault(c.tool_index,dict(name='',arguments=''))
                        if c.name:part['name']+=c.name
                        if c.parameters:part['arguments']+=c.parameters
            streamed=[dict(name=c['name'],arguments=json.loads(c['arguments'])) for c in stream_calls.values()]
            if streamed!=expected_calls:
                print(json.dumps(dict(call_id=call['call_id'],expected=[dict(name=c['name'],parameters={k:dict(type=type(v).__name__,sha256=hashlib.sha256(json.dumps(v,sort_keys=True).encode()).hexdigest(),length=len(v) if isinstance(v,(str,list,dict)) else None) for k,v in c['arguments'].items()}) for c in expected_calls],streamed=[dict(name=c['name'],parameters={k:dict(type=type(v).__name__,sha256=hashlib.sha256(json.dumps(v,sort_keys=True).encode()).hexdigest(),length=len(v) if isinstance(v,(str,list,dict)) else None) for k,v in c['arguments'].items()}) for c in streamed])),flush=True)
                raise ValueError('Streaming tool semantics differ: '+call['call_id'])
            if ''.join(thought).strip()!=expected.get('reasoning_content','').strip():raise ValueError('Streaming Thinking differs')
            if ''.join(normal).strip()!=expected['content'].strip():raise ValueError('Streaming visible body differs')
            records.append(dict(task=call['task_name'],trial_id=call['trial_id'],call_id=call['call_id'],
                tool_names=[x['name'] for x in expected_calls],nonstreaming_roundtrip=True,streaming_roundtrip=True,
                target_suffix_sha256=hashlib.sha256(text.encode()).hexdigest(),chunk_sizes=sizes))
    files={}
    for cls in [Qwen3CoderDetector,ReasoningParser]:
        path=Path(inspect.getfile(cls));files[str(path)]=hashlib.sha256(path.read_bytes()).hexdigest()
    report=dict(passed=True,targets=len(records),records=records,native_parser_files=files,
        reasoning_parser='qwen3',tool_call_parser='qwen3_coder',
        request_chat_template_kwargs=dict(enable_thinking=True),separate_reasoning=True,
        force_reasoning=True,force_reasoning_basis='Native serving_chat request logic for qwen3 with enable_thinking=true',
        stop_policy='Official im_end EOS ends generation; EOS supervised, not passed as text to tool/reasoning parsers',
        scope='Offline native parser replay of all first-canary targets; new model live serving remains a later check',
        model_loaded=False,gpu_work=False)
    (ROOT/'checks/canary-native-serving-parsers.json').write_text(json.dumps(report,indent=2));print(json.dumps({k:v for k,v in report.items() if k!='records'}))


if __name__=='__main__':main()
