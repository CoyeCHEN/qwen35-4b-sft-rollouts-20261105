"""Readonly parser-boundary investigation; synthetic wrappers are not model output."""
import os
os.environ['CUDA_VISIBLE_DEVICES'] = ''
os.environ['OMP_NUM_THREADS'] = '1'
os.environ['TOKENIZERS_PARALLELISM'] = 'false'

from collections import Counter
import hashlib
import inspect
import json
from pathlib import Path
import sys
import time

# Append only after the Serving environment's own dependencies. The frozen
# Harness supplies the unchanged, read-only artifact decoder; no venv is copied.
sys.path.append('/ssd/chenkeyi/qwen35-sft-772-20261101/env/harness-new11-r2/lib/python3.11/site-packages')
import torch
from foundation.rollouts.export import loadValue
from sglang.srt.entrypoints.openai.protocol import ChatCompletionRequest
from sglang.srt.function_call.qwen3_coder_detector import Qwen3CoderDetector

R = Path('/ssd/chenkeyi/qwen35-sft-772-20261101')
E = R / 'formal-native-eval-r1'
CASES = [
    ('llm-inference-batching-scheduler', '82fac629-25e3-4d18-a467-d4f5c7ddfbbd',
     '31585c2e5835705bcf0b0192e7cbb82199b726b17b6f73b222828108bdfb58d6'),
    ('extract-moves-from-video', '0cbd4ebd-dc8a-4621-b1de-526e973c0a89',
     '90191594f78db3c9ffa95c7afe8b6921a60f13ab782b51d1c1cefbad65565011'),
]


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def parse(text, tools, sizes):
    detector = Qwen3CoderDetector()
    pieces = []
    pos = 0
    count = 0
    while pos < len(text):
        length = sizes[count % len(sizes)]
        pieces.extend(detector.parse_streaming_increment(text[pos:pos+length], tools).calls)
        pos += length
        count += 1
    names = [piece.name for piece in pieces if piece.name]
    arguments = ''.join(piece.parameters or '' for piece in pieces)
    return dict(indices=sorted({piece.tool_index for piece in pieces}), names=names,
                arguments=json.loads(arguments), final_function_name=detector.current_func_name)


def main():
    out = R / 'checks/fixed-e3-parser-boundary-r1'
    assert not out.exists()
    out.mkdir()
    parser_source = Path(inspect.getfile(Qwen3CoderDetector))
    assert sha(parser_source) == 'e5a6112dd41df1580ede5f52e928e58cb74985dfa5628fd94073fd6a0f20fb8d'
    log_path = R / 'logs/cold-new-m1-epoch3-fixed.log'
    size = log_path.stat().st_size
    with log_path.open('rb') as source:
        log = source.read(size)
    (out / 'SERVING_LOG_PREFIX.txt').write_bytes(log)
    warnings = [line for line in log.decode().splitlines() if "Tool 'None' is not defined" in line]
    rows = []
    for task, call_id, result_sha in CASES:
        trial = E / 'jobs/qwen35-new772-new-m1-epoch3-fixed-diagnostic' / (task+'__new-m1-e3-fixed-r1')
        root = trial / 'agent/openharness-rollout'
        assert sha(trial/'result.json') == result_sha
        schema = None
        response = None
        wire = []
        created = []
        for line in (root/'events.jsonl').open('rb'):
            event = json.loads(line)
            data = event['data']
            if event['type'] == 'call_payload' and data['call_id'] == call_id:
                payload = loadValue(data['payload'], root/'artifacts')
                schema = payload['tools']
            elif event['type'] == 'call_end' and data['call_id'] == call_id:
                response = loadValue(data['response'], root/'artifacts')
            elif event['type'] == 'call_chunk' and data['call_id'] == call_id:
                chunk = loadValue(data['chunk'], root/'artifacts')
                if chunk == '[DONE]':
                    continue
                native = json.loads(chunk)
                for choice in native.get('choices', []):
                    if choice.get('index', 0) == 0:
                        for delta in (choice.get('delta') or {}).get('tool_calls') or []:
                            wire.append(delta)
                            created.append(native.get('created'))
        assert response['errorMessage'] == 'Incomplete tool call identity'
        assert wire and all(delta['index'] == -1 and not delta.get('id') and
                            not delta.get('function', {}).get('name') for delta in wire)
        actual_arguments = json.loads(''.join(delta['function'].get('arguments','') for delta in wire))
        assert set(actual_arguments) == {'path','content'} and all(isinstance(v,str) for v in actual_arguments.values())
        tools = ChatCompletionRequest.model_validate(dict(model='readonly-parser-fixture',
                    messages=[dict(role='user',content='synthetic parser input')],tools=schema)).tools
        parameters = ''.join('<parameter='+key+'>\n'+value+'\n</parameter>\n' for key,value in actual_arguments.items())
        valid = '<tool_call>\n<function=write>\n'+parameters+'</function>\n</tool_call>'
        missing = '<tool_call>\n'+parameters+'</function>\n</tool_call>'
        fixtures = []
        for sizes in ([1000000],[1],[1,7,32,256,1024]):
            parsed = parse(valid,tools,sizes)
            assert parsed['indices'] == [0] and parsed['names'] == ['write'] and parsed['arguments'] == actual_arguments
            broken = parse(missing,tools,sizes)
            assert broken['indices'] == [-1] and broken['names'] == [] and broken['arguments'] == actual_arguments
            fixtures.append(dict(chunk_sizes=sizes,valid_wrapper_recovers_exact_arguments=True,
                                 missing_function_wrapper_reproduces_negative_index=True))
        assert sha(trial/'result.json') == result_sha
        parts = response['content']
        thinking = ''.join(p.get('thinking','') for p in parts if p['type']=='thinking')
        body = ''.join(p.get('text','') for p in parts if p['type']=='text')
        rows.append(dict(task=task,call_id=call_id,result_sha256=result_sha,
                         wire_tool_indices=sorted({delta['index'] for delta in wire}),
                         wire_argument_sha256=hashlib.sha256(''.join(delta['function'].get('arguments','') for delta in wire).encode()).hexdigest(),
                         native_tool_chunk_timestamps=created,
                         thinking_function_markers=thinking.count('<function='),body_function_markers=body.count('<function='),
                         counterfactual_tests=fixtures,
                         synthetic_name_write_is_not_an_inferred_actual_model_tool_name=True))
    assert not torch.cuda.is_initialized()
    proof = dict(passed=True,at=time.time(),scope='OFFLINE_PARSER_BOUNDARY_AND_ACTUAL_NATIVE_SSE',
                 parser_source_sha256=sha(parser_source),serving_log_snapshot_bytes=len(log),
                 artifact_decoder_source_sha256=sha(Path(inspect.getfile(loadValue))),
                 torch_import_path=inspect.getfile(torch),
                 serving_log_snapshot_sha256=sha(out/'SERVING_LOG_PREFIX.txt'),actual_none_function_warnings=warnings,
                 rows=rows,raw_pre_detector_model_text_not_recorded=True,
                 root_cause_remains_unresolved_model_or_pre_detector_processing=True,
                 no_evidence_for_guessing_a_tool_name_or_rewriting_a_grade=True,
                 synthetic_xml_is_never_substituted_for_the_actual_completion=True,
                 new_model_or_tool_or_verifier_calls=0,cuda_context_created=False,
                 deployed_serving_harness_or_training_modified=False,source_sha256=sha(Path(__file__)))
    target=R/'checks/FIXED_E3_PARSER_BOUNDARY_INVESTIGATION_R1.json'
    with target.open('x') as stream:
        stream.write(json.dumps(proof,indent=2)+'\n')
    print(json.dumps(dict(passed=True,actual_trials=len(rows),synthetic_cases=12,new_model_calls=0,
                          root_cause_resolved=False,proof=str(target))))


if __name__ == '__main__':
    main()
