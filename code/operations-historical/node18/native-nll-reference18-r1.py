"""Finite native SGLang teacher-forced NLL checks on unchanged frozen rows."""
from collections import defaultdict
import hashlib
import json
import math
from pathlib import Path
import time
import urllib.request
from datasets import load_from_disk

R=Path('/ssd/chenkeyi/qwen35-sft-772-20261101')
F=R/'frozen-data-772-r3'
URL='http://127.0.0.1:18304'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
    def request(path,payload=None,timeout=300):
        req=urllib.request.Request(URL+path,data=json.dumps(payload).encode()if payload else None,
            headers={'Content-Type':'application/json'})
        with opener.open(req,timeout=timeout)as response:return json.loads(response.read())
    started=time.monotonic()
    while True:
        try:info=request('/model_info',timeout=5);break
        except OSError:
            if time.monotonic()-started>300:raise TimeoutError('Native NLL server failed to start')
            time.sleep(2)
    assert info['model_path']==str(R/'assets/source17-r1/student-tokenizer')
    results=[]
    for pool,split,index in [('calibforge','train',899),('tmax','train',0),('calibforge','validation',94)]:
        cache=load_from_disk(str(F/pool/'cache-131072'));row=cache[split][index]
        labels=row['labels'];positions=[i for i,v in enumerate(labels)if v!=-100]
        identity=next(json.loads(line)for line in(R/'supplemental-nll-label-index-r1'/(pool+'-131072.jsonl')).open()
            if (lambda x:x['split']==split and x['row_index']==index)(json.loads(line)))
        start=time.monotonic()
        payload=dict(input_ids=row['input_ids'],return_logprob=True,return_text_in_logprobs=False,
            logprob_start_len=positions[0]-1,sampling_params=dict(temperature=0,max_new_tokens=1,top_k=-1,
                min_p=0,presence_penalty=0,frequency_penalty=0,repetition_penalty=1),stream=False)
        response=request('/generate',payload)
        values=response['meta_info']['input_token_logprobs'];offset=len(row['input_ids'])-len(values)
        assert [v[1]for v in values]==row['input_ids'][offset:]
        categories=defaultdict(lambda:[0.,0]);stages=defaultdict(lambda:[0.,0]);total=0.;seen=set()
        for span in identity['spans']:
            for position in range(span['start'],span['end']):
                assert position in positions and position not in seen;seen.add(position)
                loss=-values[position-offset][0];assert math.isfinite(loss)
                categories[span['category']][0]+=loss;categories[span['category']][1]+=1
                stages[span['decision_stage']][0]+=loss;stages[span['decision_stage']][1]+=1;total+=loss
        assert seen==set(positions)
        result=dict(pool=pool,split=split,row_index=index,task_id=identity['task_id'],trial_id=identity['trial_id'],
            sample_sha256=identity['sample_sha256'],input_tokens=len(row['input_ids']),supervised_tokens=len(positions),
            mean_nll=total/len(positions),nll_sum=total,
            category_nll={k:v[0]/v[1]for k,v in categories.items()},category_tokens={k:v[1]for k,v in categories.items()},
            stage_nll={k:v[0]/v[1]for k,v in stages.items()},
            exact_input_token_logprob_alignment=True,elapsed_seconds=time.monotonic()-start,
            meta={k:v for k,v in response['meta_info'].items()if k!='input_token_logprobs'})
        results.append(result);print(json.dumps(result),flush=True)
    proof=dict(passed=True,results=results,actual_model_info=info,
        class_index_audit_sha256=sha(R/'supplemental-nll-label-index-r1/LABEL_CLASS_INDEX_AUDIT.json'),
        new_teacher_calls=0,optimizer_updates=0,training_or_official_evaluation_protocol_modified=False,
        scope='Unpenalized native input-token logprobs, frozen Assistant labels only, single causal shift. Not autonomous task success or the formal temperature1 evaluation.')
    (R/'checks/NATIVE_SGLANG_NLL_REFERENCE_R1.json').write_text(json.dumps(proof,indent=2)+'\n')


if __name__=='__main__':main()
