"""CPU-only native SGLang rendering of four actual failed requests; no runtime fix."""
import os
os.environ['CUDA_VISIBLE_DEVICES']=''
os.environ['OMP_NUM_THREADS']='1'
os.environ['TOKENIZERS_PARALLELISM']='false'
import copy
import hashlib
import inspect
import json
from pathlib import Path
import tarfile
from types import SimpleNamespace

R=Path('/ssd/chenkeyi/qwen35-sft-772-20261101')
P=R/'harness-context-recovery-r1'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def main():
    bundle=P/'context-recovery-history-r2.tar.gz'
    assert sha(bundle)=='d8054bcc67870373999937c0f855ae9494c21db6f570ba8d6b919fcb1a19d628'
    folder=P/'token-investigation-r2';folder.mkdir(mode=0o700,exist_ok=True)
    with tarfile.open(bundle,'r:gz')as archive:
        for member in archive.getmembers():
            assert member.isfile() and Path(member.name).name==member.name and member.name.endswith('.json')
            data=archive.extractfile(member).read();out=folder/member.name
            if out.exists():assert out.read_bytes()==data
            else:out.write_bytes(data);out.chmod(0o600)
    audit=json.loads((folder/'HISTORICAL_CONTEXT_RECOVERY_AUDIT_R2.json').read_text())
    from transformers import AutoTokenizer
    from sglang.srt.entrypoints.openai.serving_chat import OpenAIServingChat
    from sglang.srt.entrypoints.openai.protocol import ChatCompletionRequest
    from sglang.srt.parser.jinja_template_utils import detect_jinja_template_content_format
    import torch
    module=Path(inspect.getfile(OpenAIServingChat))
    assert sha(module)=='b521132c6332a5a5796f2aad27e0837ebb376afcfddd1940415328f788821dfd'
    tokenizer=AutoTokenizer.from_pretrained(R/'assets/source17-r1/student-tokenizer',local_files_only=True)
    obj=OpenAIServingChat.__new__(OpenAIServingChat)
    obj.tokenizer_manager=SimpleNamespace(tokenizer=tokenizer)
    obj.template_manager=SimpleNamespace(chat_template_name=None,
        jinja_template_content_format=detect_jinja_template_content_format(tokenizer.chat_template))
    obj.tool_call_parser='qwen3_coder';obj.reasoning_parser='qwen3'
    obj.is_gpt_oss=False;obj.use_dpsk_v32_encoding=False
    def count(payload):
        req=ChatCompletionRequest.model_validate(payload)
        return len(obj._process_messages(req,is_multimodal=False).prompt_ids)
    rows=[]
    for record in audit['token_investigation_inputs']:
        path=folder/Path(record['path']).name
        assert sha(path)==record['sha256']
        data=json.loads(path.read_text());payload=data['provider_payload'];native=data['native_input']
        assert record['harness_replay']['native_image_blocks']==0
        measured=count(payload)
        replay_difference=measured-data['provider_actual_input_tokens']
        no_tools=copy.deepcopy(payload);no_tools.pop('tools',None);no_tools.pop('tool_choice',None)
        no_thinking=copy.deepcopy(payload)
        for m in no_thinking['messages']:
            if m['role']=='assistant':m.pop('reasoning_content',None)
        no_observation=copy.deepcopy(payload)
        for m in no_observation['messages']:
            if m['role']=='tool':m['content']=''
        estimated=record['harness_replay']['actual_trigger_estimate']['tokens']
        row=dict(trial_name=data['trial_name'],call_id=data['call_id'],input_snapshot_sha256=sha(path),
            serving_actual_input_tokens=data['provider_actual_input_tokens'],
            exact_native_sglang_replay_tokens=measured,harness_trigger_estimate=estimated,
            undercount=data['provider_actual_input_tokens']-estimated,
            exact_replay_difference=replay_difference,exact_replay_equal=replay_difference==0,threshold=262144-81920,
            requested_context=262144,requested_output=payload['max_tokens'],
            serving_budget_overflow=data['provider_actual_input_tokens']+payload['max_tokens']-262144,
            harness_replay=record['harness_replay'],
            individual_system_text_tokens=len(tokenizer.encode(native['systemPrompt'],add_special_tokens=False)),
            schema_and_tool_template_delta=measured-count(no_tools),
            rendered_thinking_delta=measured-count(no_thinking),
            rendered_visible_tool_observation_delta=measured-count(no_observation),
            ablations_are_counting_only_not_actual_or_training_contexts=True,
            component_deltas_not_claimed_additive=True,
            actual_error_requests_contain_no_images=True)
        assert payload['max_tokens']==81920
        rows.append(row)
    # Verify the complete CLI fixture advertised the exact real production schemas.
    fixture=P/'e2e/run-20261101T161651Z-718a8c/two_independent_with_11_tools/request-001.json'
    tools=json.loads(fixture.read_text())['tools']
    reference=json.loads((folder/Path(audit['token_investigation_inputs'][0]['path']).name).read_text())['provider_payload']['tools']
    assert tools==reference,'The actual fixture and production schemas must agree'
    assert not torch.cuda.is_initialized()
    result=dict(completed=True,source_sha256=sha(__file__),actual_requests=len(rows),rows=rows,
        exact_replay_matches=sum(r['exact_replay_equal']for r in rows),
        unresolved_exact_replay_mismatches=[dict(call_id=r['call_id'],difference=r['exact_replay_difference'])for r in rows if not r['exact_replay_equal']],
        no_tokens_or_padding_added_to_force_alignment=True,
        tokenizer_json_sha256=sha(R/'assets/source17-r1/student-tokenizer/tokenizer.json'),
        chat_template_sha256=sha(R/'assets/source17-r1/student-tokenizer/chat_template.jinja'),
        native_serving_source_sha256=sha(module),history_audit_sha256=sha(folder/'HISTORICAL_CONTEXT_RECOVERY_AUDIT_R2.json'),
        real_fixture_tools_equal_production_tools=True,cuda_context_created=False,
        no_new_model_or_teacher_requests=True,runtime_estimation_code_or_budgets_changed=False,
        multimodal_scope='All4 actual overflow inputs have0 image blocks. Source estimateTokens assigns1200/image; no image count is claimed exact and images cannot explain these4 failures.',
        findings=['Anchored mode uses true previous input+output usage, then chars/4 for the trailing history; template and assistant rerendering may also change that prefix.',
                  'Whenever any historical tool result is projected, the current policy clears all assistant usage anchors and uses chars/4 for all visible messages.',
                  'Fallback mode does not explicitly include System, tool schema or chat-template framing. Anchored mode already includes the previous System/schema implicitly; do not add them twice.',
                  'These are estimator findings only; the minimal Controller repair is independently validated.'])
    p=R/'checks/TOKEN_ESTIMATION_INVESTIGATION_R2.json';assert not p.exists()
    p.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(dict(completed=True,rows=[{k:r[k]for k in ['trial_name','call_id','serving_actual_input_tokens','harness_trigger_estimate','undercount','serving_budget_overflow']}for r in rows],sha256=sha(p))),flush=True)


if __name__=='__main__':main()
