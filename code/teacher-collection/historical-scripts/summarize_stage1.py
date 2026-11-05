"""Summarize completed fixed-corpus and serving evidence, no new execution."""
import csv
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
read=lambda name:json.loads((ROOT/name).read_text())
fingerprint=lambda name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest()
rows=[]
m1=read('checks/m1-full-target-nll.json');m2=read('checks/m2-full-target-nll.json')
assert len(m1['samples'])==len(m2['samples'])==3
for a,b in zip(m1['samples'],m2['samples']):
    assert a['source_input_sha256']==b['source_input_sha256'] and a['category_counts']==b['category_counts']
    for category in ['TOTAL']+list(a['category_counts']):
        before=a['total_mean_nll'] if category=='TOTAL' else a['category_mean_nll'][category]
        after=b['total_mean_nll'] if category=='TOTAL' else b['category_mean_nll'][category]
        rows.append(dict(dataset=a['dataset'],split=a['split'],index=a['index'],task_id=a.get('task_id'),
            call_id=a.get('call_id'),category=category,tokens=a['supervised_positions'] if category=='TOTAL' else a['category_counts'][category],
            m1_nll=before,m2_nll=after,delta_nats=after-before,input_sha256=a['source_input_sha256']))
with (ROOT/'stage1/FIXED_CORPUS_NLL.csv').open('w') as stream:
    writer=csv.DictWriter(stream,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
(ROOT/'checks/fixed-corpus-nll-comparison.json').write_text(json.dumps(dict(
    scope='Three complete fixed inputs, every supervised position; not full corpus averages',
    m1_source_sha256=fingerprint('checks/m1-full-target-nll.json'),
    m2_source_sha256=fingerprint('checks/m2-full-target-nll.json'),rows=rows),indent=2))

comparisons=[]
for condition,hot,cold in [
    ('HISTORICAL_SERVING_FLAGS',read('checks/serving-cold-hot-r1.json')['phases'][1],read('checks/serving-cold-hot-r2.json')['phases'][0]),
    ('INDEPENDENT_DETERMINISTIC_PAIRED_SEEDS',read('checks/serving-cold-hot-r3.json')['phases'][1],read('checks/serving-cold-hot-r3.json')['phases'][2]),
]:
    for a,b in zip(hot['cases'],cold['cases']):
        assert a['input_sha256']==b['input_sha256'] and a['fixed_continuation']['tokens']==b['fixed_continuation']['tokens']
        runs=[]
        for x,y in zip(a['runs'],b['runs']):
            pa=x['response']['meta_info']['output_token_logprobs'];pb=y['response']['meta_info']['output_token_logprobs']
            same_tokens=[v[1] for v in pa]==[v[1] for v in pb]
            delta=max(abs(u[0]-v[0]) for u,v in zip(pa,pb)) if same_tokens else None
            runs.append(dict(seed=x['seed'],same_generated_tokens=same_tokens,
                same_decoded_text=x['response']['text']==y['response']['text'],max_logprob_absolute_difference=delta))
        comparisons.append(dict(condition=condition,task=a['task'],input_sha256=a['input_sha256'],input_tokens=a['input_tokens'],
            historical_input_tokens=a['historical_input_tokens'],fixed_continuation_tokens=64,
            hot_nll=a['fixed_continuation']['mean_nll'],cold_nll=b['fixed_continuation']['mean_nll'],
            nll_absolute_difference=abs(a['fixed_continuation']['mean_nll']-b['fixed_continuation']['mean_nll']),runs=runs))
proof=dict(complete=True,comparisons=comparisons,
    historical_seed_semantics='sampling_seed ignored unless enable_deterministic_inference; historical draws are unpaired',
    paired_seed_condition='Independent native deterministic mode + pytorch sampler + server seed42; historical scores unchanged',
    historical_token_exact_reproduction=False,historical_24_token_difference='UNRESOLVED; not padded',
    full_raw_logits='NOT_EXPOSED; top5 normalized logprobs and fixed continuation NLL retained',
    inference='Three-prefix checks do not support pervasive hot-update corruption; long/high-concurrency/multimodal behavior remains unexcluded',
    source_sha256={name:fingerprint('checks/'+name+'.json') for name in ['serving-cold-hot-r1','serving-cold-hot-r2','serving-cold-hot-r3']})
(ROOT/'checks/serving-cold-hot-comparison.json').write_text(json.dumps(proof,indent=2))
print(json.dumps(dict(nll_rows=len(rows),serving_cases=len(comparisons),
    paired_generated_matches=sum(all(r['same_generated_tokens'] for r in c['runs']) for c in comparisons if c['condition'].startswith('INDEPENDENT')))))
