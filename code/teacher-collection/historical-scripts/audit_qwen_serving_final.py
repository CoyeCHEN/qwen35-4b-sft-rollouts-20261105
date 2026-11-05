"""Replay real targets through the existing native SGLang Qwen parsers, CPU only."""
from collections import OrderedDict
import argparse
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

ROOT=Path(os.environ.get('CF_TMAX_AUDIT_ROOT','/home/chenkeyi/workspace/RSI/runtime-evidence/qwen35-new-cf500-tmax500-20261029'))


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--all-canaries',action='store_true')
    args=ap.parse_args()
    source_dir=ROOT/('sources/canary-calls-all' if args.all_canaries else 'sources/canary-calls')
    projection_file=ROOT/'checks'/('canary-qwen-projection-all-v4.json' if args.all_canaries else 'canary-qwen-projection-v4.json')
    projection={x['trial_id']:x for x in json.loads(projection_file.read_text())}
    tokenizer=load_tokenizer();records=[]
    for path in sorted(source_dir.glob('*.jsonl.gz')):
        calls=[json.loads(line) for line in gzip.open(path,'rt')]
        item=projection[calls[0]['trial_id']]
        if item['errors']:continue
        training={x['call_id']:x for x in json.loads(Path(item['target_mapping']).read_text())}
        for call in calls:
            decision=project_decision(tokenizer,call);left,right=decision.evidence['supervised_range']
            for key in ['generation_prefix_sha256','input_sha256','labels_sha256','provider_payload_sha256','normalized_history_sha256']:
                if decision.evidence[key]!=training[call['call_id']][key]:
                    raise ValueError('Serving and training environments project different contexts: '+key)
            text=tokenizer.decode(decision.row['input_ids'][left:],skip_special_tokens=False,clean_up_tokenization_spaces=False)
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
            generated_ids=tokenizer.encode(generated,add_special_tokens=False)
            emitted=''
            while offset<len(generated_ids):
                size=sizes[iteration%len(sizes)];offset=min(len(generated_ids),offset+size);iteration+=1
                cumulative=tokenizer.decode(generated_ids[:offset],skip_special_tokens=False,clean_up_tokenization_spaces=False)
                if cumulative.endswith('\ufffd') and offset<len(generated_ids):continue
                if not cumulative.startswith(emitted):raise ValueError('Non-monotonic token decode needs native detokenizer review')
                chunk=cumulative[len(emitted):];emitted=cumulative
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
            if streamed!=expected_calls:raise ValueError('Streaming tool semantics differ: '+call['call_id'])
            if ''.join(thought).strip()!=expected.get('reasoning_content','').strip():raise ValueError('Streaming Thinking differs')
            if ''.join(normal).strip()!=expected['content'].strip():raise ValueError('Streaming visible body differs')
            records.append(dict(task=call['task_name'],trial_id=call['trial_id'],call_id=call['call_id'],
                tool_names=[x['name'] for x in expected_calls],nonstreaming_roundtrip=True,streaming_roundtrip=True,
                training_and_serving_prefix_ids_identical=True,
                target_suffix_sha256=hashlib.sha256(text.encode()).hexdigest(),chunk_sizes_in_qwen_tokens=sizes))
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
    report['scope']='Offline native parser replay; each projected prefix compared with the separate training environment. No live model serving.'
    file='canary-native-serving-parsers-all-v4.json' if args.all_canaries else 'canary-native-serving-parsers-final.json'
    (ROOT/'checks'/file).write_text(json.dumps(report,indent=2));print(json.dumps({k:v for k,v in report.items() if k!='records'}))


if __name__=='__main__':main()
