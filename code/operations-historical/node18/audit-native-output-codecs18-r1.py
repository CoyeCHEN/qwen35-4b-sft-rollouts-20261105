"""All original tool actions through the installed native Qwen detector, no training data rewriting."""
import os
os.environ['CUDA_VISIBLE_DEVICES']=''
os.environ['OMP_NUM_THREADS']='1'
os.environ['TOKENIZERS_PARALLELISM']='false'
import hashlib
import json
from pathlib import Path
import sys
import time

R=Path('/ssd/chenkeyi/qwen35-sft-772-20261101')
P=Path('/data/chenkeyi/qwen35-sft-772-20261101/provenance')
sys.path.insert(0,str(R/'new-sft/source-r4/repository'))
from sft.qwen35 import normalize_message
from transformers import AutoTokenizer
from sglang.srt.entrypoints.openai.protocol import ChatCompletionRequest
from sglang.srt.function_call.qwen3_coder_detector import Qwen3CoderDetector


def semantic(value):
    if value is None:return ('null',)
    if isinstance(value,bool):return ('bool',value)
    if isinstance(value,(int,float)):return ('number',value)
    if isinstance(value,str):return ('string',value)
    if isinstance(value,list):return ('array',tuple(semantic(v)for v in value))
    return ('object',tuple((k,semantic(value[k]))for k in sorted(value)))


def combined(parts):
    groups={}
    for part in parts:
        row=groups.setdefault(part.tool_index,dict(name='',arguments=''))
        if part.name:row['name']+=part.name
        if part.parameters:row['arguments']+=part.parameters
    return [(v['name'],semantic(json.loads(v['arguments']or'{}')))for _,v in sorted(groups.items())]


def main():
    while not(P/'OUTPUT_CODEC_FIXTURE_EXTRACTION.json').exists():time.sleep(10)
    source=P/'OUTPUT_CODEC_ORIGINAL_FIXTURES.jsonl'
    manifest=json.loads((P/'OUTPUT_CODEC_FIXTURE_EXTRACTION.json').read_text())
    assert hashlib.sha256(source.read_bytes()).hexdigest()==manifest['fixtures_sha256']
    tokenizer=AutoTokenizer.from_pretrained(R/'assets/source17-r1/student-tokenizer',local_files_only=True)
    template=json.loads((P/'NEW11_PAYLOAD_TEMPLATE.json').read_text())
    tools=ChatCompletionRequest.model_validate(dict(model='codec-diagnostic',messages=[dict(role='user',content='codec')],tools=template['tools'])).tools
    results=[];mismatches=[];targets=0;tool_calls=0;start=time.time()
    for line in source.open():
        item=json.loads(line);targets+=1;calls=item['tool_calls'];tool_calls+=len(calls)
        record={k:item[k]for k in ['pool','task_id','trial_id','call_id']}
        record['tool_calls']=len(calls)
        try:
            if calls:
                assistant=normalize_message(dict(role='assistant',content='',tool_calls=calls))
                # Isolated wire-codec fixture only; this never becomes a corpus history.
                rendered=tokenizer.apply_chat_template([dict(role='user',content='Output codec diagnostic'),assistant],
                    tokenize=False,add_generation_prompt=False,enable_thinking=True)
                marker='<|im_start|>assistant\n';at=rendered.index(marker)
                body=rendered[at+len(marker):].removesuffix('<|im_end|>\n')
                expected=[(c['function']['name'],semantic(json.loads(c['function']['arguments'])if isinstance(c['function']['arguments'],str)else c['function']['arguments']))for c in calls]
                once=combined(Qwen3CoderDetector().detect_and_parse(body,tools).calls)
                detector=Qwen3CoderDetector();parts=[];offset=0
                sizes=[1,7,32,256,1024];count=0
                while offset<len(body):
                    step=sizes[count%len(sizes)];parts.extend(detector.parse_streaming_increment(body[offset:offset+step],tools).calls)
                    offset+=step;count+=1
                streamed=combined(parts)
                record.update(nonstreaming_equal=once==expected,streaming_equal=streamed==expected)
                if once!=expected or streamed!=expected:
                    record['expected_sha256']=hashlib.sha256(repr(expected).encode()).hexdigest()
                    record['nonstream_sha256']=hashlib.sha256(repr(once).encode()).hexdigest()
                    record['stream_sha256']=hashlib.sha256(repr(streamed).encode()).hexdigest()
                    record['expected_tool_names']=[x[0]for x in expected]
                    mismatches.append(record)
            else:record.update(nonstreaming_equal=True,streaming_equal=True)
        except (ValueError,TypeError,KeyError,AttributeError)as e:
            record.update(nonstreaming_equal=False,streaming_equal=False,error=type(e).__name__+': '+str(e)[:200])
            mismatches.append(record)
        results.append(record)
        if targets%512==0:
            print(json.dumps(dict(targets=targets,tool_calls=tool_calls,mismatches=len(mismatches),elapsed_seconds=time.time()-start)),flush=True)
    assert targets==30193 and tool_calls==36852
    report=dict(passed=not mismatches,completed=True,targets=targets,tool_calls=tool_calls,mismatches=mismatches,
        input_fixtures_sha256=manifest['fixtures_sha256'],source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        numeric_semantics='JSON numbers compared numerically; bool distinct; all strings exact including whitespace',
        training_data_rewritten=False,model_calls=0,elapsed_seconds=time.time()-start)
    (R/'checks/ALL_TARGET_NATIVE_OUTPUT_CODEC_AUDIT.json').write_text(json.dumps(report,indent=2)+'\n')
    with(R/'checks/ALL_TARGET_NATIVE_OUTPUT_CODEC_ROWS.jsonl').open('x')as f:
        for row in results:f.write(json.dumps(row)+'\n')
    print(json.dumps({k:v for k,v in report.items()if k!='mismatches'}),flush=True)


if __name__=='__main__':main()
