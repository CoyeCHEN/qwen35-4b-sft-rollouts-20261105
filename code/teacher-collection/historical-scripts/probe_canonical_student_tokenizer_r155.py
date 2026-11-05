"""Compare a real mismatched prefix in isolated canonical tokenizer resources."""
import gzip,hashlib,importlib.metadata,json,os,sys
from pathlib import Path
from sft.qwen35 import load_tokenizer,digest
from sft.teacher_segments import project_decision
label=sys.argv[1]
root=Path('/home/chenkeyi/workspace/RSI/runtime-evidence/qwen35-new-cf500-tmax500-20261029/validation/stream-r3/ddc3d97b-cd36-44c5-b911-28451892baeb')
path,=list((root/'sources/canary-calls-all').glob('*.jsonl.gz'))
call=next(json.loads(line) for line in gzip.open(path,'rt') if json.loads(line)['call_id']=='8da8700a-5b42-4b6b-8c29-b0a1e4aacf7c')
tokenizer=load_tokenizer();decision=project_decision(tokenizer,call)
backend=json.loads(tokenizer.backend_tokenizer.to_str())
backend.pop('padding',None);backend.pop('truncation',None)
report=dict(label=label,passed_fixture=decision.evidence['generation_prefix_sha256']=='7e37f3d66c1b7656110136a9f21c0011207700bed0513800d1a58a0c2a21bde3',
 model_resource=os.environ['QWEN35_MODEL_PATH'],tokenizer_class=type(tokenizer).__module__+'.'+type(tokenizer).__name__,
 versions={n:importlib.metadata.version(n) for n in ['transformers','tokenizers','jinja2']},backend_semantics_sha256=digest(backend),
 evidence={k:decision.evidence[k] for k in ['generation_prefix_sha256','input_sha256','labels_sha256','provider_payload_sha256','normalized_history_sha256']},
 trial_id=call['trial_id'],call_id=call['call_id'],raw_export_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
 all_targets_revalidated=False,formal_admission=False,model_calls=0,original_model_directory_modified=False)
target=Path(os.environ['QWEN35_MODEL_PATH'])/('PROBE_'+label.upper()+'_R155.json')
with target.open('x') as stream:json.dump(report,stream,indent=2)
print(json.dumps(report))
