"""Compare full CLI payloads to both frozen Qwen encoding and installed SGLang processing."""
import os
os.environ['CUDA_VISIBLE_DEVICES']=''
os.environ['OMP_NUM_THREADS']='1'
import hashlib
import inspect
import json
from pathlib import Path
import sys
from types import SimpleNamespace

R=Path('/ssd/chenkeyi/qwen35-sft-772-20261101')
sys.path.insert(0,str(R/'new-sft/source-r4/repository'))
from sft.teacher_segments import project_decision
from sft.qwen35 import digest
from transformers import AutoTokenizer
from sglang.srt.entrypoints.openai.serving_chat import OpenAIServingChat
from sglang.srt.entrypoints.openai.protocol import ChatCompletionRequest
from sglang.srt.parser.jinja_template_utils import detect_jinja_template_content_format


def main():
    output=Path(sys.argv[1]);config=json.loads((output/'config.json').read_text())
    binding_path=output/'SERVING_MODEL_BINDING.json'
    binding=json.loads(binding_path.read_text())
    assert binding['model_id']==config['model']['id']
    declared=Path(binding['tokenizer_model_path'])
    assert declared.is_relative_to(R)
    model=declared.resolve()
    assert Path(binding['actual_model_info']['model_path']).resolve()==model
    marker=Path(binding['model_manifest'])
    assert hashlib.sha256(marker.read_bytes()).hexdigest()==binding['weight_version']==binding['actual_model_info']['weight_version']
    assert hashlib.sha256((model/'tokenizer.json').read_bytes()).hexdigest()=='5f9e4d4901a92b997e463c1f46055088b6cca5ca61a6522d1b9f64c4bb81cb42'
    assert hashlib.sha256((model/'chat_template.jinja').read_bytes()).hexdigest()=='a4aee8afcf2e0711942cf848899be66016f8d14a889ff9ede07bca099c28f715'
    tokenizer=AutoTokenizer.from_pretrained(model,local_files_only=True)
    module=Path(inspect.getfile(OpenAIServingChat))
    assert hashlib.sha256(module.read_bytes()).hexdigest()=='b521132c6332a5a5796f2aad27e0837ebb376afcfddd1940415328f788821dfd'
    obj=OpenAIServingChat.__new__(OpenAIServingChat)
    obj.tokenizer_manager=SimpleNamespace(tokenizer=tokenizer)
    obj.template_manager=SimpleNamespace(chat_template_name=None,jinja_template_content_format=detect_jinja_template_content_format(tokenizer.chat_template))
    obj.tool_call_parser='qwen3_coder';obj.reasoning_parser='qwen3';obj.is_gpt_oss=False;obj.use_dpsk_v32_encoding=False
    rows=[]
    for call in json.loads((output/'RESOLVED_NATIVE_CALLS.json').read_text()):
        decision=project_decision(tokenizer,call)
        assert call['provider_payload']['model']==binding['model_id']
        request=ChatCompletionRequest.model_validate(call['provider_payload'])
        native=obj._process_messages(request,is_multimodal=False).prompt_ids
        want=decision.row['input_ids'][:decision.evidence['prefix_tokens']]
        assert native==want,call['call_id']
        assert len(native)==call['actual_prompt_tokens'],(call['call_id'],len(native),call['actual_prompt_tokens'])
        rows.append(dict(call_id=call['call_id'],native_prefix_tokens=len(native),prefix_sha256=digest(native),actual_gpu_usage_prompt_tokens=call['actual_prompt_tokens'],equal=True))
    result=dict(passed=True,targets=len(rows),rows=rows,serving_model_binding_sha256=hashlib.sha256(binding_path.read_bytes()).hexdigest(),scope='Actual full CLI provider payload; exact Qwen training prefix, installed native SGLang IDs and real GPU response usage')
    (output/'NATIVE_PREFIX_AUDIT.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(dict(passed=True,targets=len(rows))),flush=True)


if __name__=='__main__':main()
