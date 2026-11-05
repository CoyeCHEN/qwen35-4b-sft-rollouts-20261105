"""Finite single-GPU native NLL audit; immutable model/cache, unique validation rows."""
import argparse
from collections import defaultdict
import gzip
import importlib
import hashlib
import json
import math
from pathlib import Path
import subprocess
import time
import urllib.request
from datasets import load_from_disk

R=Path('/ssd/chenkeyi/qwen35-sft-772-20261101')
F=R/'frozen-data-772-r3'
gpu5=importlib.import_module('gpu5_readiness18_r1')
def sha(p):
    h=hashlib.sha256()
    with p.open('rb')as f:
        for block in iter(lambda:f.read(8*1024*1024),b''):h.update(block)
    return h.hexdigest()
def digest(v):return hashlib.sha256(json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def score(model,tag,pools):
    model=model.resolve();marker=model/'EPOCH_MODEL_EXPORT_COMPLETE.json'
    if not marker.exists():marker=model/'HF_EXPORT_COMPLETE.json'
    assert marker.exists()and model.is_relative_to(R)
    manifest=json.loads(marker.read_text())
    assert all(sha(model/x.get('name',x.get('path')))==x['sha256']for x in manifest['files'])
    output=R/'nll-audits'/tag;assert not output.exists(),'A prior audit is preserved; do not silently rescore'
    (output/'raw').mkdir(parents=True)
    request_options=dict(temperature=0,max_new_tokens=1,top_k=-1,min_p=0,presence_penalty=0,frequency_penalty=0,repetition_penalty=1)
    deployment=dict(model=str(model),model_manifest_sha256=sha(marker),source_sha256=sha(Path(__file__)),
        pools=pools,split='validation',prefix_and_labels='Frozen128K cache, original unique rows',
        prefill_chunk_size=2048,concurrent_requests=1,sampling_params=request_options)
    (output/'AUDIT_DEPLOYMENT.json').write_text(json.dumps(deployment,indent=2)+'\n')
    readiness=gpu5.inspect()
    assert readiness['ready'],'Preserve any existing GPU5 task'
    (output/'GPU_READINESS.json').write_text(json.dumps(readiness,indent=2)+'\n')
    seed=json.loads((R/'checks/M0_NEW11_NATIVE_SERVING_COMMAND_R2.json').read_text())['command']
    exe=str(R/'env/serve-new11-r1/bin/python');idx=seed.index(exe);server=seed[idx:]
    server[server.index('--model-path')+1]=str(model);server[server.index('--port')+1]='18305'
    server[server.index('--max-running-requests')+1]='1'
    server+=['--chunked-prefill-size','2048','--weight-version',sha(marker)]
    flags=[x for x in seed[:idx]if not x.startswith(('--unit=','--property=StandardOutput=','--property=StandardError=','--property=Environment=CUDA_VISIBLE_DEVICES='))]
    unit='qwen35-new772-nll-'+tag+'-20261101.service'
    command=flags+['--unit='+unit,'--property=RuntimeMaxSec=10800',
        '--property=Environment=CUDA_VISIBLE_DEVICES='+readiness['gpu_uuid'],
        '--property=StandardOutput=append:'+str(output/'server.log'),'--property=StandardError=append:'+str(output/'server.log')]+server
    (output/'SERVER_COMMAND.json').write_text(json.dumps(command,indent=2)+'\n')
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
    def query(path,payload=None,timeout=300):
        req=urllib.request.Request('http://127.0.0.1:18305'+path,
            data=json.dumps(payload).encode()if payload is not None else None,headers={'Content-Type':'application/json'})
        with opener.open(req,timeout=timeout)as response:return json.loads(response.read())
    summaries={}
    try:
        subprocess.run(command,check=True,capture_output=True,text=True)
        start=time.monotonic()
        while True:
            try:info=query('/model_info',timeout=5);break
            except OSError:
                if time.monotonic()-start>300:raise TimeoutError('Native scoring model failed cold loading')
                time.sleep(2)
        assert info['model_path']==str(model)and info['weight_version']==sha(marker)
        (output/'ACTUAL_MODEL_INFO.json').write_text(json.dumps(info,indent=2)+'\n')
        with(output/'UNIQUE_ROW_NLL.jsonl').open('x')as stream:
            for pool in pools:
                cache=load_from_disk(str(F/pool/'cache-131072'))['validation']
                indices=[json.loads(line)for line in(R/'supplemental-nll-label-index-r1'/(pool+'-131072.jsonl')).open()]
                rows={r['row_index']:r for r in indices if r['split']=='validation'}
                assert set(rows)==set(range(len(cache)))
                losses=[];tokens=0;loss_sum=0.;categories=defaultdict(lambda:[0.,0]);stages=defaultdict(lambda:[0.,0]);tasks=defaultdict(list)
                for index in range(len(cache)):
                    item=rows[index];row=cache[index]
                    assert digest(row['input_ids'])==item['input_sha256']and digest(row['labels'])==item['labels_sha256']
                    positions={i for i,v in enumerate(row['labels'])if v!=-100};assert positions
                    payload=dict(input_ids=row['input_ids'],return_logprob=True,return_text_in_logprobs=False,
                        logprob_start_len=min(positions)-1,sampling_params=request_options,stream=False)
                    request_start=time.monotonic();response=query('/generate',payload)
                    raw=output/'raw'/(pool+'-'+str(index)+'.json.gz')
                    with gzip.open(raw,'wt',encoding='utf-8')as blob:json.dump(dict(request=payload,response=response),blob,ensure_ascii=False)
                    values=response['meta_info']['input_token_logprobs'];offset=len(row['input_ids'])-len(values)
                    assert 0<=offset<=min(positions)and[v[1]for v in values]==row['input_ids'][offset:]
                    total=0.;seen=set();local=defaultdict(lambda:[0.,0]);target=defaultdict(lambda:[0.,0])
                    for span in item['spans']:
                        for position in range(span['start'],span['end']):
                            assert position in positions and position not in seen;seen.add(position)
                            loss=-values[position-offset][0];assert math.isfinite(loss)
                            for destination,key in [(categories,span['category']),(local,span['category']),
                                    (stages,span['decision_stage']),(target,span['call_id'])]:
                                destination[key][0]+=loss;destination[key][1]+=1
                            total+=loss
                    assert seen==positions
                    mean=total/len(positions);losses.append(mean);loss_sum+=total;tokens+=len(positions);tasks[item['task_id']].append(mean)
                    record=dict(pool=pool,row_index=index,task_id=item['task_id'],trial_id=item['trial_id'],
                        sample_sha256=item['sample_sha256'],input_tokens=len(row['input_ids']),supervised_tokens=len(positions),
                        nll_sum=total,sample_mean_nll=mean,category_nll={k:v[0]/v[1]for k,v in local.items()},
                        category_tokens={k:v[1]for k,v in local.items()},
                        per_original_call={k:dict(nll_sum=v[0],supervised_tokens=v[1])for k,v in target.items()},
                        raw_request_response=str(raw.relative_to(output)),raw_request_response_sha256=sha(raw),
                        native_call_id=response['meta_info']['id'],input_logprob_offset=offset,elapsed_seconds=time.monotonic()-request_start)
                    stream.write(json.dumps(record,ensure_ascii=False)+'\n');stream.flush()
                    print(json.dumps(dict(tag=tag,pool=pool,completed_unique_rows=index+1,total_unique_rows=len(cache),latest_nll=mean)),flush=True)
                summaries[pool]=dict(unique_rows=len(losses),unique_tasks=len(tasks),sample_mean_nll=sum(losses)/len(losses),
                    token_mean_nll=loss_sum/tokens,supervised_tokens=tokens,
                    task_mean_nll=sum(sum(v)/len(v)for v in tasks.values())/len(tasks),
                    category_nll={k:v[0]/v[1]for k,v in categories.items()},category_tokens={k:v[1]for k,v in categories.items()},
                    decision_stage_nll={k:v[0]/v[1]for k,v in stages.items()})
        raw_manifest=output/'RAW_PAYLOAD_SHA256.json'
        raw_manifest.write_text(json.dumps({str(p.relative_to(output)):sha(p)for p in sorted((output/'raw').iterdir())},indent=2)+'\n')
        result=dict(passed=True,model=str(model),model_manifest_sha256=sha(marker),gpu_uuid=readiness['gpu_uuid'],
            raw_payload_manifest_sha256=sha(raw_manifest),
            summaries=summaries,unique_row_results_sha256=sha(output/'UNIQUE_ROW_NLL.jsonl'),
            deployment_sha256=sha(output/'AUDIT_DEPLOYMENT.json'),optimizer_updates=0,
            training_or_agent_sampling_recipe_changed=False,weight_or_checkpoint_selection_changed=False)
        (output/'NLL_AUDIT_COMPLETE.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result),flush=True)
    finally:
        subprocess.run(['systemctl','--user','stop',unit],check=True,timeout=60)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--model',type=Path,required=True);p.add_argument('--tag',required=True)
    p.add_argument('--pools',nargs='+',choices=['calibforge','tmax'],default=['calibforge'])
    args=p.parse_args();assert args.tag.replace('-','').isalnum();score(args.model,args.tag,args.pools)
