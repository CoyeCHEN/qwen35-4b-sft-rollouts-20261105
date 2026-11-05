"""Single-worker source -> official IDs/labels -> actual LF collator audit.

All old data remain read-only. Full Qwen parameters are meta; no CUDA/model update.
"""
import collections
import argparse
import traceback
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import time

import pyarrow.parquet as pq
import torch
from accelerate import init_empty_weights
from datasets import load_from_disk
from transformers import AutoConfig, AutoModelForImageTextToText
from llamafactory.hparams import ModelArguments, DataArguments
from llamafactory.model import load_tokenizer
from llamafactory.data import get_template_and_fix_tokenizer, SFTDataCollatorWith4DAttentionMask
from adapters.openharness_v2 import _resolve
from sft import qwen35 as codec

parser=argparse.ArgumentParser();parser.add_argument('--only-m2',action='store_true');parser.add_argument('--failed-only',action='store_true');options=parser.parse_args()
OUT = Path('/home/chenkeyi/workspace/RSI/runtime-evidence/qwen35-new-cf500-tmax500-20261029')
OLD = Path('/home/chenkeyi/workspace/RSI/runtime-evidence/qwen35-sft-preflight-20261023')
M2 = Path('/ssd/chenkeyi/qwen35-sft-launch-prep-20261025/m2-teacher149-candidates-v2')
BASE = '/data/models/Qwen/Qwen3.5-4B'
torch.set_num_threads(1)
codec.MODEL = BASE
tok = codec.load_tokenizer()
module = load_tokenizer(ModelArguments(model_name_or_path=BASE))
template = get_template_and_fix_tokenizer(module['tokenizer'], DataArguments(template='qwen3_5'))
config = AutoConfig.from_pretrained(BASE, local_files_only=True)
with init_empty_weights():
    model = AutoModelForImageTextToText.from_config(config)
collate = SFTDataCollatorWith4DAttentionMask(template=template, model=model,
    tokenizer=module['tokenizer'], processor=module['processor'], pad_to_multiple_of=8,
    label_pad_token_id=-100, block_diag_attn=False, neat_packing=False,
    attn_implementation='flash_attention_2', compute_dtype=torch.bfloat16)
counts = collections.Counter()
errors = []
shell = collections.Counter()
shell_examples = []
task_splits = collections.defaultdict(set)
seen = set()
start = time.monotonic()
row_name='actual-input-collator-m2-r2.jsonl' if options.failed_only else ('actual-input-collator-m2-r1.jsonl' if options.only_m2 else 'actual-input-collator-rows.jsonl')
rows_out = (OUT/'stage1'/row_name).open('x')
reused_m1_proof=None


def file_sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def error(identity, failure):
    errors.append(identity | {'error_type': type(failure).__name__, 'reason':str(failure)[:1000], 'traceback_lines':[dict(file=t.filename,line=t.lineno,function=t.name)for t in traceback.extract_tb(failure.__traceback__)[-3:]]})


def verify(row, meta, reconstructed, family, split, identity):
    ids=row['input_ids'];labels=row['labels'];n=len(ids)
    assert len(labels)==len(row['attention_mask'])==n and all(x==1 for x in row['attention_mask'])
    assert n==meta['text_tokens'] and codec.digest(ids)==meta['input_sha256']
    assert codec.digest(labels)==meta['labels_sha256']
    assert all(isinstance(x,int) and 0<=x<config.text_config.vocab_size for x in ids)
    assert all(y==-100 or y==x for x,y in zip(ids,labels))
    assert sum(x!=-100 for x in labels)==meta['loss_tokens']>0
    assert reconstructed['input_ids']==ids and reconstructed['labels']==labels
    assert all(not row.get(kind) for kind in ('images','videos','audios'))
    target_key=(family, identity['trajectory'] if family=='m1' else identity['trial_id'],
        'all_assistant_once' if family=='m1' else identity['call_id'])
    assert target_key not in seen, 'Duplicate supervised source target identity'
    seen.add(target_key)
    task_splits[(family,split)].add(identity['task_group'])
    feature=copy.deepcopy(row);batch=collate([feature])
    assert torch.equal(batch['input_ids'][0,:n],torch.tensor(ids))
    assert torch.equal(batch['labels'][0,:n],torch.tensor(labels))
    assert bool((batch['labels'][0,n:]==-100).all())
    assert bool((batch['attention_mask'][0,n:]==0).all())
    assert batch['input_ids'].shape[-1] <= (65536 if family=='m1' else 131072)
    pids=batch.get('position_ids')
    position_result='not_present_in_collator_output'
    if pids is not None:
        actual=pids[..., :n].reshape(-1,n)
        assert bool((actual==torch.arange(n)).all()), 'Unexpected non-monotonic text-only positions'
        position_result='all_text_axes_equal_arange'
    record=identity | dict(dataset=family,split=split,text_tokens=n,supervised_tokens=meta['loss_tokens'],
        input_sha256=meta['input_sha256'],labels_sha256=meta['labels_sha256'],
        supervised_ranges=meta['supervised_ranges'],collated_positions=batch['input_ids'].shape[-1],
        added_positions_masked=True,position_ids_check=position_result,passed=True)
    rows_out.write(json.dumps(record)+'\n')
    counts[family+'_'+split+'_rows']+=1
    counts[family+'_'+split+'_supervised_tokens']+=meta['loss_tokens']
    counts[family+'_assistant_targets']+=len(meta['supervised_ranges'])
    if sum(v for k,v in counts.items() if k.endswith('_rows'))%100==0:
        print(json.dumps(dict(event='progress',counts=dict(counts),seconds=time.monotonic()-start)),flush=True)


def inspect_shell(messages, identity):
    system='\n'.join(str(m.get('content',''))for m in messages if m['role']=='system')
    persistent=bool(re.search(r'(?i)(working directory|environment variables).{0,100}preserv',system))
    if persistent:shell['trajectories_declaring_persistent_shell']+=1
    commands=[]
    for ordinal,m in enumerate(messages):
        if m['role']!='assistant':continue
        for block in re.findall(r'<tool_call>(.*?)</tool_call>',str(m.get('content','')),re.S):
            value=None
            try:
                call=json.loads(block);args=call.get('arguments',{});value=args.get('command',args.get('cmd',args.get('commands')))
            except (ValueError,AttributeError):
                match=re.search(r'<parameter=(?:command|cmd|commands)>(.*?)</parameter>',block,re.S)
                if match:value=match.group(1)
            if isinstance(value,list):value='\n'.join(map(str,value))
            if isinstance(value,str):commands.append((ordinal,value))
    shell['commands_examined']+=len(commands)
    flagged=set()
    for index, (ordinal,command) in enumerate(commands[:-1]):
        following=commands[index+1][1]
        kind=None
        if re.fullmatch(r'\s*cd\s+[^;&|\n]+\s*;?\s*',command) and not re.match(r'\s*cd\s',following):
            kind='isolated_cd_followed_by_command'
        match=re.search(r'(?:^|[;\n])\s*export\s+([A-Za-z_]\w*)=',command)
        if match and re.search(r'\$(?:'+re.escape(match.group(1))+r'\b|\{'+re.escape(match.group(1))+r'\})',following):
            kind='export_variable_referenced_in_next_call'
        fn=re.search(r'(?:^|[;\n])\s*(?:function\s+)?([A-Za-z_]\w*)\s*\(\s*\)\s*\{',command)
        if fn and re.search(r'(?m)^\s*'+re.escape(fn.group(1))+r'\b',following):kind='shell_function_called_in_next_call'
        if re.search(r'(?:^|[;\n])\s*(?:source|\.)\s+\S+',command):shell['source_command_occurrences']+=1
        if kind:
            shell[kind]+=1;flagged.add(kind)
            if sum(x['kind']==kind for x in shell_examples)<5:
                shell_examples.append(identity|dict(kind=kind,assistant_ordinal=ordinal,
                    command_sha256=codec.digest(command),next_command_sha256=codec.digest(following),
                    original_commands_location='Source Parquet messages; hashes only in this report',
                    declared_persistent=persistent,classification='STATIC_SEMANTIC_RISK_NOT_REPLAY_PROOF'))
    for kind in flagged:shell['trajectories_with_'+kind]+=1


m1_manifest=json.loads((OLD/'manifests/m1-64k.json').read_text())
if not options.only_m2:
    m1=load_from_disk(str(OLD/'data/m1-64k'))
    source_hashes=[]
    for source_split,split in [('train','train'),('holdout','validation')]:
        source=m1_manifest['source_files'][source_split]
        assert file_sha(source['path'])==source['sha256']
        source_hashes.append(source)
        index_file=OLD/'manifests'/('m1-train-rows.jsonl'if split=='train'else'm1-holdout-rows.jsonl')
        index={}
        for i,line in enumerate(index_file.open()):
            meta=json.loads(line);index[meta['trajectory']]=(i,meta)
        selected=set()
        for batch in pq.ParquetFile(source['path']).iter_batches(batch_size=1):
            for raw in batch.to_pylist():
                trajectory=raw['trajectory_id']
                if trajectory not in index:continue
                i,meta=index[trajectory];identity=dict(trajectory=trajectory,task_group=raw['task_group_id'],index=i)
                try:
                    messages=raw['messages'];last=max(i for i,m in enumerate(messages) if m['role']=='assistant')
                    assert codec.digest(messages)==meta['original_messages_sha256']
                    trimmed=messages[:last+1]
                    rebuilt,evidence=codec.encode(tok,trimmed,scope='all_assistant',cutoff=65536)
                    assert evidence['source_messages_sha256']==meta['source_messages_sha256']
                    verify(m1[split][i],meta,rebuilt,'m1',split,identity)
                    inspect_shell(trimmed,identity)
                except Exception as failure:error(identity|{'dataset':'m1','split':split},failure)
                selected.add(trajectory)
        assert selected==set(index)

else:
    prior_path=OUT/'checks'/('frozen-input-collator-audit-r1.json'if options.failed_only else'frozen-input-collator-audit.json')
    prior=json.loads(prior_path.read_text())
    assert prior['counts']['m1_train_rows']==5320 and prior['counts']['m1_validation_rows']==191
    assert all(e['dataset']=='m2'for e in prior['errors'])
    counts.update({k:v for k,v in prior['counts'].items()if k.startswith('m1_')or options.failed_only})
    shell.update(prior['shell_semantics']);shell_examples=prior['shell_examples'];source_hashes=prior['source_files']
    reused_m1_proof=dict(path=str(prior_path),sha256=file_sha(prior_path),scope='All successful previously audited rows; failed rows alone are rechecked with the exact raw training reader path')
    for source_split,split in [('train','train'),('holdout','validation')]:task_splits[('m1',split)].update(m1_manifest['task_groups'][source_split])

m2=load_from_disk(str(M2/'tokenized'));by_export=collections.defaultdict(dict)
for split in ('train','validation'):
    for i,line in enumerate((M2/(split+'-rows.jsonl')).open()):
        meta=json.loads(line);task_splits[('m2',split)].add(meta['task_group'])
        if options.failed_only and meta['call_id']not in {e['call_id']for e in prior['errors']}:continue
        by_export[meta['source_export']][meta['call_id']]=(split,i,meta)
for export,needed in by_export.items():
    path=Path(export);meta=next(iter(needed.values()))[2]
    assert file_sha(path/'manifest.json')==meta['export_manifest_sha256']
    assert file_sha(path/'calls.jsonl')==meta['export_calls_sha256']
    observed=set()
    for line in (path/'calls.jsonl').open():
        raw=json.loads(line);call_id=raw['call_id']
        if call_id not in needed:continue
        split,i,meta=needed[call_id]
        identity=dict(task_id=meta['task_id'],task_group=meta['task_group'],trial_id=meta['trial_id'],
            call_id=call_id,index=i,source_export=export,session_id=meta['session_id'])
        try:
            native=_resolve(raw,path);payload=native['payload']
            call=dict(call_id=call_id,context_fidelity=native['fidelity'],provider_payload=payload,
                request_messages=payload['messages'],assistant_response=native['response'])
            assert native.get('source')=='agent','Compaction/helper call incorrectly selected'
            rebuilt,evidence=codec.encode_call(tok,call,cutoff=131072)
            assert evidence['source_messages_sha256']==meta['source_messages_sha256']
            verify(m2[split][i],meta,rebuilt,'m2',split,identity)
        except Exception as failure:error(identity|{'dataset':'m2','split':split},failure)
        observed.add(call_id)
    assert observed==set(needed)
for family in ('m1','m2'):
    assert not task_splits[(family,'train')] & task_splits[(family,'validation')]
rows_out.close()
result=dict(passed=not errors,counts=dict(counts),errors=errors,source_files=source_hashes,
    m2_exports_checked_this_invocation=len(by_export),m2_exports_checked=(prior['m2_exports_checked']if options.failed_only else len(by_export)),seconds=time.monotonic()-start,
    full_source_to_ids_labels_to_native_collator=True,model_parameters_meta=all(p.is_meta for p in model.parameters()),
    cuda_initialized=torch.cuda.is_initialized(),shell_semantics=dict(shell),shell_examples=shell_examples,
    m1_provider_payload_availability='Not released upstream; original flattened messages are the traceable source, not fabricated HTTP payloads',
    m2_provider_payload_availability='Every retained call rebuilt from actual source export payload, file SHA checked',
    original_tokenizer_eos_id=tok.eos_token_id,native_collator_tokenizer_eos_id=module['tokenizer'].eos_token_id,
    source_modified=False,formal_new_data_created=False,reused_m1_proof=reused_m1_proof,
    native_response_policy='Exact original payload plus native assistant blocks; no generic adapter scrubbing or derived finish_reason. The real sft.sources reader preserves raw values and quarantines credentials rather than rewriting.',
    script_sha256=file_sha(__file__))
(OUT/'checks'/('frozen-input-collator-audit-r2.json'if options.failed_only else ('frozen-input-collator-audit-r1.json'if options.only_m2 else'frozen-input-collator-audit.json'))).write_text(json.dumps(result,indent=2))
print(json.dumps({k:v for k,v in result.items() if k not in ('errors','shell_examples','source_files')}),flush=True)
assert result['passed'] and not result['cuda_initialized']
