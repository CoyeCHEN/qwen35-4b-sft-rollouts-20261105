"""CPU diagnostic for both real canaries; failed trials are never SFT-admitted."""
import gzip
import hashlib
import json
import os
from pathlib import Path
import time

os.environ['CUDA_VISIBLE_DEVICES']=''
from sft.qwen35 import load_tokenizer
from sft.teacher_segments import project_decision,make_segments

ROOT=Path('/home/chenkeyi/workspace/RSI/runtime-evidence/qwen35-new-cf500-tmax500-20261029')


def main():
    tokenizer=load_tokenizer();report=[]
    out=ROOT/'derived/canary-qwen-v2';out.mkdir(parents=True,exist_ok=True)
    for path in sorted((ROOT/'sources/canary-calls').glob('*.jsonl.gz')):
        started=time.monotonic();calls=[json.loads(x) for x in gzip.open(path,'rt')];decisions=[];errors=[]
        for call in calls:
            try:decisions.append(project_decision(tokenizer,call))
            except (ValueError,AssertionError) as error:errors.append(dict(call_id=call['call_id'],error=str(error)))
        lengths={};identity=path.name.split('.')[0]
        for cap in [131072,262144]:
            if not decisions:continue
            encoded=make_segments(decisions,cutoff=cap)
            target=out/(identity+'-'+str(cap)+'.jsonl.gz')
            with gzip.open(target,'wt') as stream:
                for sample in encoded['samples']:stream.write(json.dumps(sample)+'\n')
            lengths[str(cap)]=dict(targets=encoded['target_count'],segments=len(encoded['samples']),
                supervised_tokens=sum(x['evidence']['supervised_tokens'] for x in encoded['samples']),
                quarantine=encoded['quarantine'],all_original_targets_once=encoded['all_targets_exactly_once'] and not errors,
                segment_lengths=[x['evidence']['input_tokens'] for x in encoded['samples']],
                cache=str(target),cache_sha256=hashlib.sha256(target.read_bytes()).hexdigest())
        evidence_path=out/(identity+'-targets.json')
        evidence_path.write_text(json.dumps([d.evidence for d in decisions],indent=2))
        record=dict(task=calls[0]['task_name'],trial_id=calls[0]['trial_id'],calls=len(calls),projected=len(decisions),
            errors=errors,lengths=lengths,seconds=time.monotonic()-started,
            raw_export_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
            target_mapping=str(evidence_path),target_mapping_sha256=hashlib.sha256(evidence_path.read_bytes()).hexdigest(),
            generation_boundary_bpe_changes=sum(d.evidence['generation_boundary_changes_bpe'] for d in decisions),
            scope='Conversion diagnostic only; source verifier/native integrity and loader gate separate',
            sft_admission='NOT_GRANTED_BY_THIS_DIAGNOSTIC')
        report.append(record);print(json.dumps(record),flush=True)
    (ROOT/'checks/canary-qwen-projection-v2.json').write_text(json.dumps(report,indent=2))


if __name__=='__main__':main()
