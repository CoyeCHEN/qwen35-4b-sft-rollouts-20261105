"""Bounded complete old validation-matrix NLL, cold M1 then cold M2.

Reuse the checked SGLang process lifecycle, fixed IDs/labels and official label
categories. No task execution, model update, paid API or benchmark dispatch.
"""
from collections import defaultdict
import fcntl
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import sys
import time

ROOT=Path('/home/chenkeyi/workspace/RSI/runtime-evidence/qwen35-new-cf500-tmax500-20261029')
OLD=Path('/home/chenkeyi/workspace/RSI/runtime-evidence/qwen35-m2-regression-diagnosis-20261029')
spec=importlib.util.spec_from_file_location('existing_serving_lifecycle',ROOT/'scripts/serving_cold_hot.py')
api=importlib.util.module_from_spec(spec);spec.loader.exec_module(api)
api.SUFFIX='-full-validation-r1';api.PROOF=ROOT/'checks/full-validation-serving-nll-r1.json'
assert not api.PROOF.exists(),'Preserve an existing matrix and inspect before any continuation'
api.REPORT=dict(scope='Full 191-row M1 and 125-row M2 validation sets, all supervised positions, cold native SGLang BF16 TP4',
    planned_models=['m1','m2'],expected_rows_per_model=316,complete=False,events=[],models={},
    historical_token_exact_benchmark_replay=False,new_model_updates=0,new_benchmark_trials=0,new_paid_requests=0,
    limitation='Serving backend BF16 NLL; compare models within this method, not unrelated online training means')


def digest(value):
    return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def main():
    from datasets import load_from_disk
    from transformers import AutoTokenizer
    spec=importlib.util.spec_from_file_location('original_label_categories',OLD/'scripts/audit_supervision.py')
    helpers=importlib.util.module_from_spec(spec);spec.loader.exec_module(helpers)
    tokenizer=AutoTokenizer.from_pretrained('/data/models/Qwen/Qwen3.5-4B',local_files_only=True)
    definitions=[('m1',
        '/home/chenkeyi/workspace/RSI/runtime-evidence/qwen35-sft-preflight-20261023/data/m1-64k',
        '/home/chenkeyi/workspace/RSI/runtime-evidence/qwen35-sft-preflight-20261023/manifests/m1-holdout-rows.jsonl'),
        ('m2','/ssd/chenkeyi/qwen35-sft-launch-prep-20261025/m2-teacher149-candidates-v2/tokenized',
         '/ssd/chenkeyi/qwen35-sft-launch-prep-20261025/m2-teacher149-candidates-v2/validation-rows.jsonl')]
    datasets={name:load_from_disk(path)['validation'] for name,path,_ in definitions}
    indexes={name:list(map(json.loads,Path(path).open())) for name,_,path in definitions}
    assert len(datasets['m1'])==len(indexes['m1'])==191 and len(datasets['m2'])==len(indexes['m2'])==125
    api.REPORT['validation_index_sha256']={name:hashlib.sha256(Path(path).read_bytes()).hexdigest()for name,_,path in definitions}
    api.REPORT['script_sha256']=hashlib.sha256(Path(__file__).read_bytes()).hexdigest();api.save()
    with open('/home/chenkeyi/workspace/RSI/runtime-evidence/qwen35-sft-preflight-20261023/runs/training.lock','a')as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        api.check_free()
        for model in ('m1','m2'):
            state=dict(rows_completed=0,started_at=time.time(),datasets={})
            api.REPORT['models'][model]=state;api.save()
            with api.server(model):
                state['actual_server_identity']=api.query('/get_model_info');api.save()
                with (ROOT/f'stage1/full-validation-nll-r1-{model}.jsonl').open('x')as output:
                    for family in ('m1','m2'):
                        aggregates=defaultdict(lambda:[0.0,0]);tasks=defaultdict(lambda:[0.0,0,0.0,0]);sample_sum=0.0
                        for index in range(len(datasets[family])):
                            started=time.monotonic();row=datasets[family][index];meta=indexes[family][index]
                            ids=row['input_ids'];labels=row['labels']
                            assert digest(ids)==meta['input_sha256'] and digest(labels)==meta['labels_sha256']
                            positions=[i for i,v in enumerate(labels)if v!=-100];assert positions and positions[0]>0
                            categories={};left=0
                            while left<len(labels):
                                if labels[left]==-100:left+=1;continue
                                right=left+1
                                while right<len(labels)and labels[right]!=-100:right+=1
                                groups,_=helpers.classes(tokenizer,ids[left:right]);categories.update(zip(range(left,right),groups));left=right
                            result=api.query('/generate',dict(input_ids=ids,return_logprob=True,return_text_in_logprobs=False,
                                logprob_start_len=positions[0]-1,sampling_params=dict(temperature=0,max_new_tokens=1),stream=False),timeout=240)
                            probabilities=result['meta_info']['input_token_logprobs'];offset=len(ids)-len(probabilities)
                            assert [p[1]for p in probabilities]==ids[offset:],'Returned logprob tokens do not align with the frozen input'
                            groups=defaultdict(lambda:[0.0,0]);total=0.0
                            for position in positions:
                                value=probabilities[position-offset][0]
                                assert value is not None and math.isfinite(value)
                                value=-value;total+=value;groups[categories[position]][0]+=value;groups[categories[position]][1]+=1
                            assert len(positions)==meta['loss_tokens']
                            for key,(summed,count)in groups.items():aggregates[key][0]+=summed;aggregates[key][1]+=count
                            mean=total/len(positions);sample_sum+=mean;task=meta.get('task_group',meta.get('task_id','UNKNOWN'))
                            tasks[task][0]+=total;tasks[task][1]+=len(positions);tasks[task][2]+=mean;tasks[task][3]+=1
                            record=dict(model=model,dataset=family,index=index,task=task,source_call_id=meta.get('call_id'),
                                input_sha256=meta['input_sha256'],labels_sha256=meta['labels_sha256'],
                                input_tokens=len(ids),supervised_tokens=len(positions),sample_mean_nll=mean,
                                category_counts={k:v[1]for k,v in groups.items()},category_mean_nll={k:v[0]/v[1]for k,v in groups.items()},
                                native_prompt_tokens=result['meta_info'].get('prompt_tokens'),seconds=time.monotonic()-started)
                            output.write(json.dumps(record)+'\n');output.flush()
                            state['rows_completed']+=1
                            state['datasets'][family]=dict(rows=index+1,sample_mean_nll=sample_sum/(index+1),
                                token_mean_nll=sum(x[0]for x in aggregates.values())/sum(x[1]for x in aggregates.values()),
                                supervised_tokens=sum(x[1]for x in aggregates.values()),
                                category_counts={k:v[1]for k,v in aggregates.items()},category_mean_nll={k:v[0]/v[1]for k,v in aggregates.items()},
                                tasks={k:dict(supervised_tokens=v[1],token_mean_nll=v[0]/v[1],rows=v[3],sample_mean_nll=v[2]/v[3])for k,v in tasks.items()})
                            state['last_row']=dict(dataset=family,index=index,seconds=record['seconds']);api.save()
                            if (index+1)%10==0:print(json.dumps(dict(model=model,dataset=family,rows=index+1,last_seconds=record['seconds'])),flush=True)
            state['complete']=state['rows_completed']==316;state['finished_at']=time.time();api.save()
        api.REPORT['complete']=all(m['complete']for m in api.REPORT['models'].values());api.save()


if __name__=='__main__':
    try:main()
    except BaseException as error:
        api.REPORT.update(error_type=type(error).__name__,error=str(error),complete=False);api.save();raise
