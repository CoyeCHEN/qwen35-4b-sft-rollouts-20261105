"""Bind first real-canary conversion/loader/parser evidence to exact trial/call IDs."""
import gzip
import argparse
import hashlib
import json
import os
from pathlib import Path

ROOT=Path(os.environ.get('CF_TMAX_AUDIT_ROOT','/home/chenkeyi/workspace/RSI/runtime-evidence/qwen35-new-cf500-tmax500-20261029'))


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--all-canaries',action='store_true')
    args=ap.parse_args()
    names=(['canary-qwen-projection-all-v4.json','canary-native-loader-all-v4.json','canary-native-serving-parsers-all-v4.json']
        if args.all_canaries else ['canary-qwen-projection-v4.json','canary-native-loader-v4.json','canary-native-serving-parsers-final.json'])
    projection=json.loads((ROOT/'checks'/names[0]).read_text())
    loader=json.loads((ROOT/'checks'/names[1]).read_text())
    parser=json.loads((ROOT/'checks'/names[2]).read_text())
    tokenizer=json.loads((ROOT/'checks/qwen-tokenizer-processor-identity.json').read_text())
    assert loader['passed'] and parser['passed'] and tokenizer['passed']
    sources=ROOT/('sources/canary-calls-all' if args.all_canaries else 'sources/canary-calls')
    source_index={}
    for path in sources.glob('*.jsonl.gz'):
        with gzip.open(path,'rt') as stream:first=json.loads(next(stream))
        source_index.setdefault(first['trial_id'],[]).append(path)
    entries=[]
    for item in projection:
        matches=source_index.get(item['trial_id'],[])
        assert len(matches)==1
        source=matches[0];calls=[json.loads(line) for line in gzip.open(source,'rt')]
        assert hashlib.sha256(source.read_bytes()).hexdigest()==item['raw_export_sha256']
        ids=[c['call_id'] for c in calls]
        journals={c['source_journal_sha256'] for c in calls};assert len(journals)==1
        if item['errors']:
            reasons=sorted({e['error'] for e in item['errors']})
            entries.append(dict(trial_id=item['trial_id'],task_name=item['task'],
                semantic_projection_passed=False,all_original_targets_once=False,original_call_ids=ids,
                source_journal_sha256=next(iter(journals)),raw_export_sha256=item['raw_export_sha256'],
                native_loader_and_collator_passed=False,native_streaming_and_nonstreaming_parsers_passed=False,
                quarantine_class='UNSUPPORTED_MULTIMODAL' if all('Non-text content' in s for s in reasons) else 'STRUCTURAL_OR_SEMANTIC_ERROR',
                quarantine_reasons=reasons,affected_targets=len(item['errors']),
                partial_text_prefixes_not_admitted=True,source_reward_checked_separately=True))
            continue
        observed=[x['call_id'] for x in parser['records'] if x['trial_id']==item['trial_id']]
        assert ids==observed and len(ids)==item['projected']==item['calls'] and not item['errors']
        assert any(x['source_trial']==item['trial_id'] and x['all_rows_loaded_through_formal_loader'] for x in loader['records'])
        entries.append(dict(trial_id=item['trial_id'],task_name=item['task'],semantic_projection_passed=True,
            exact_deployment_prefixes=True,all_original_targets_once=True,original_call_ids=ids,
            source_journal_sha256=next(iter(journals)),raw_export_sha256=item['raw_export_sha256'],
            native_loader_and_collator_passed=True,native_streaming_and_nonstreaming_parsers_passed=True,
            qwen_revision=tokenizer['revision'],encoder_commit='f974a81241baf0740f3d7602181f386313a5c90e',
            encoder_sha256=hashlib.sha256((ROOT/'sft-code/sft/teacher_segments.py').read_bytes()).hexdigest(),
            native_loss_gradient_reference_passed=loader['numerical_reference']['passed'],
            length_views=item['lengths'],supervision_token_classes=item['supervision_token_classes'],
            source_reward_checked_separately=True))
    proofs={}
    for name in [*names,'qwen-tokenizer-processor-identity.json']:
        p=ROOT/'checks'/name;sha=hashlib.sha256(p.read_bytes()).hexdigest()
        if args.all_canaries:
            frozen=ROOT/'checks/student-proof-artifacts'/(sha+'.json');frozen.parent.mkdir(exist_ok=True)
            if frozen.exists():assert frozen.read_bytes()==p.read_bytes()
            else:
                with frozen.open('xb') as stream:stream.write(p.read_bytes())
            p=frozen
        proofs[name]=dict(path=str(p),sha256=sha,relative_path=str(p.relative_to(ROOT)))
    report=dict(scope='Real teacher canary conversion only; reward, protocol and task admission remain separate',
        entries=entries,proofs=proofs,does_not_approve_reward_or_task_provenance=True)
    file='STUDENT_AUDIT_TRIALS_ALL.json' if args.all_canaries else 'STUDENT_AUDIT_TRIALS.json'
    (ROOT/'checks'/file).write_text(json.dumps(report,indent=2));print(json.dumps(dict(trials=len(entries),targets=sum(len(x['original_call_ids']) for x in entries))))


if __name__=='__main__':main()
