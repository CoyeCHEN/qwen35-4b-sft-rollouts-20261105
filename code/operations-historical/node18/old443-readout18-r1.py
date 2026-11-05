"""Run the frozen old443 measured-row function on18, with explicit local bindings."""
import argparse
from collections import defaultdict
import gzip
import hashlib
import importlib
import json
import math
from pathlib import Path
import shutil
import subprocess
import sys
import time
import urllib.request
from datasets import load_from_disk

R=Path('/ssd/chenkeyi/qwen35-sft-772-20261101')
P=R/'old-four-arm'
C=Path('/data/chenkeyi/qwen35-sft-772-20261101/control')
A=R/'assets/source17-r1'
GPU='GPU-7b634c3e-13ae-5243-19dd-b6edddf9a543'
TAGS=['old-M1','old-M2']+[arm+'-epoch'+str(epoch)for arm in 'ABCD'for epoch in (1,3,5)]
sys.path.insert(0,str(P/'source/repository'));sys.path.insert(0,str(R))
from studies.qwen35_m2_full_causal.score_checkpoint import measured_row
from studies.qwen35_m2_causal_v2.common import digest
assets=importlib.import_module('snapshot-epoch-hf18-r2')


def sha(path):
    h=hashlib.sha256()
    with path.open('rb')as stream:
        for block in iter(lambda:stream.read(8*1024*1024),b''):h.update(block)
    return h.hexdigest()


def check_data():
    manifest=json.loads((P/'manifests/experiments.json').read_text())
    source=P/'source/repository/studies/qwen35_m2_full_causal/score_checkpoint.py'
    if sha(source)!=manifest['study_source_sha256']['score_checkpoint.py']:
        raise ValueError('Frozen measured-row implementation changed')
    original=json.loads((P/'manifests/evaluation443.json').read_text())
    data=load_from_disk(manifest['evaluation_dataset'])
    if len(data)!=443:raise ValueError('Expected443 encoded rows')
    tasks=set()
    for index,row in enumerate(data):
        identity=json.loads(row['identity_json']);tasks.add(identity['task_id'])
        if identity!=original['rows'][index]or identity['evaluation_index']!=index:
            raise ValueError('Old443 row identity differs')
        if digest(row['input_ids'])!=identity['input_sha256']:
            raise ValueError('Old443 input IDs differ')
        if len(set(row['target_positions']))!=len(row['target_positions']):
            raise ValueError('Duplicate supervised token positions')
        if len(row['target_positions'])!=len(row['target_categories']):
            raise ValueError('Old category-position count differs')
        labels=[-100]*len(row['input_ids'])
        for position in row['target_positions']:labels[position]=row['input_ids'][position]
        if digest(labels)!=identity['labels_sha256']:
            raise ValueError('Old443 labels differ')
    return data,dict(passed=True,unique_rows=443,unique_tasks=len(tasks),
        original_evaluation_manifest_sha256=sha(P/'manifests/evaluation443.json'),
        generation_prefix_positions_sha256=sha(P/'manifests/generation-prefix-positions.json'),
        measured_row_original_source_sha256=sha(source),
        runtime_dataset=str(Path(manifest['evaluation_dataset']).resolve()),
        original_encoded_ids_and_categories_unchanged=True,new_gpu_or_model_requests=0)


def model_source(tag):
    manifest=json.loads((P/'manifests/experiments.json').read_text())
    if tag=='old-M1':return A/'old-m1',dict(expected_weight_sha256=manifest['model_sha256'])
    if tag=='old-M2':
        proof=json.loads((R/'checks/OLD_M2_BASELINE18_DEPLOYMENT.json').read_text())
        if not proof['all_files_sha256_verified']:raise ValueError('OldM2 baseline is not sealed')
        return Path(proof['runtime_model_path']),dict(expected_weight_sha256=proof['original_weight_sha256'])
    arm,epoch=tag.split('-epoch');step=106*int(epoch)
    model=Path(manifest['arms'][arm]['output_dir'])/('checkpoint-'+str(step))
    marker=model/'CHECKPOINT_COMPLETE.json'
    if not marker.exists():raise ValueError('Wait for complete native old checkpoint '+tag)
    state=json.loads((model/'trainer_state.json').read_text())
    if state['global_step']!=step or abs(state['epoch']-int(epoch))>.01:
        raise ValueError('Old checkpoint dose differs')
    return model,dict(checkpoint_complete_sha256=sha(marker),optimizer_step=step,
        arm_config_sha256=manifest['arms'][arm]['config_sha256'])


def sealed_model(tag):
    source,identity=model_source(tag)
    index=source/'model.safetensors.index.json'
    names=set(json.loads(index.read_text())['weight_map'].values())if index.exists()else{'model.safetensors'}
    if 'expected_weight_sha256'in identity:
        if names!={'model.safetensors'}or sha(source/'model.safetensors')!=identity['expected_weight_sha256']:
            raise ValueError('Old baseline original weight SHA differs')
    target=P/'epoch-models'/tag
    marker=target/'OLD_READOUT_HF_COMPLETE.json'
    if target.exists():
        proof=json.loads(marker.read_text())
        if proof['source_identity']!=identity or proof['source_path']!=str(source):
            raise ValueError('Preserve original old readout release')
        if not all(sha(target/f['name'])==f['sha256']for f in proof['files']):
            raise ValueError('Old readout HF changed')
        return target,marker
    staging=target.with_name(target.name+'.staging')
    if staging.exists():raise ValueError('Inspect interrupted old readout staging')
    staging.mkdir(parents=True)
    for name in sorted(names):
        original=source/name
        if original.is_symlink()or not original.is_file():raise ValueError('Unexpected source weight binding')
        import os
        os.link(original,staging/name)
    for name in ['config.json','generation_config.json','model.safetensors.index.json']:
        if(source/name).exists():shutil.copyfile(source/name,staging/name)
    for name,expected in assets.ASSETS.items():
        original=A/'student-tokenizer'/name
        if sha(original)!=expected:raise ValueError('Canonical asset changed')
        shutil.copyfile(original,staging/name)
    proof=dict(tag=tag,source_path=str(source),source_identity=identity,
        files=[dict(name=f.name,bytes=f.stat().st_size,sha256=sha(f))for f in sorted(staging.iterdir())],
        original_checkpoint_and_baselines_untouched=True,
        nll_input_ids_are_original_frozen_encoded_ids_no_template_rerender=True,
        canonical_tokenizer_assets_are_serving_packaging_only=True)
    (staging/marker.name).write_text(json.dumps(proof,indent=2)+'\n');staging.rename(target)
    return target,marker


def run(tag):
    gate=importlib.import_module('resume-old-four-native18-r2').admitted()
    if not gate['admitted']:raise ValueError('Old GPU readouts wait until new formal801 completes')
    data,proof=check_data();model,marker=sealed_model(tag)
    output=P/'readouts443'/tag
    if output.exists():raise ValueError('Preserve prior old443 audit; never silently rescore')
    actual=subprocess.check_output(['nvidia-smi','-i','5','--query-gpu=uuid,memory.used',
        '--format=csv,noheader,nounits'],text=True).strip().split(',')
    if actual[0].strip()!=GPU or int(actual[1])!=0:raise ValueError('Authorized GPU5 is occupied')
    (output/'raw').mkdir(parents=True)
    prefixes={x['evaluation_index']:x for x in json.loads((P/'manifests/generation-prefix-positions.json').read_text())['positions']}
    seed=json.loads((R/'checks/M0_NEW11_NATIVE_SERVING_COMMAND_R2.json').read_text())['command']
    executable=str(R/'env/serve-new11-r1/bin/python');offset=seed.index(executable);server=seed[offset:]
    server[server.index('--model-path')+1]=str(model);server[server.index('--port')+1]='18305'
    server[server.index('--max-running-requests')+1]='1'
    server+=['--chunked-prefill-size','2048','--weight-version',sha(marker)]
    flags=[x for x in seed[:offset]if not x.startswith(('--unit=','--property=StandardOutput=',
        '--property=StandardError=','--property=Environment=CUDA_VISIBLE_DEVICES='))]
    unit='qwen35-old443-nll-'+tag.lower()+'-20261101.service'
    command=flags+['--unit='+unit,'--property=RuntimeMaxSec=21600',
        '--property=Environment=CUDA_VISIBLE_DEVICES='+GPU,
        '--property=StandardOutput=append:'+str(output/'server.log'),
        '--property=StandardError=append:'+str(output/'server.log')]+server
    deployment=dict(tag=tag,data=proof,model_path=str(model),model_release_sha256=sha(marker),
        source_sha256=sha(Path(__file__)),native_server_command=command,optimizer_updates=0,
        unpenalized_input_token_logprob=True,not_autonomous_success=True)
    (output/'DEPLOYMENT.json').write_text(json.dumps(deployment,indent=2)+'\n')
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
    def query(path,payload=None,timeout=300):
        request=urllib.request.Request('http://127.0.0.1:18305'+path,
            data=json.dumps(payload).encode()if payload is not None else None,headers={'Content-Type':'application/json'})
        with opener.open(request,timeout=timeout)as response:return json.loads(response.read())
    options=dict(temperature=0,max_new_tokens=1,top_k=-1,min_p=0,
        presence_penalty=0,frequency_penalty=0,repetition_penalty=1)
    groups=defaultdict(list)
    try:
        subprocess.run(command,check=True,capture_output=True,text=True)
        started=time.monotonic()
        while True:
            try:live=query('/model_info',timeout=5);break
            except OSError:
                if time.monotonic()-started>300:raise TimeoutError('Old readout cold load failed')
                time.sleep(2)
        if live['model_path']!=str(model)or live['weight_version']!=sha(marker):
            raise ValueError('Old NLL actual server identity differs')
        (output/'ACTUAL_MODEL_INFO.json').write_text(json.dumps(live,indent=2)+'\n')
        with(output/'UNIQUE_ROWS.jsonl').open('x')as stream:
            for index,row in enumerate(data):
                identity=json.loads(row['identity_json']);boundary=prefixes.get(index);probe=None;probe_raw=None
                if boundary:
                    prefix=row['input_ids'][:boundary['generation_prefix_tokens']]
                    if digest(prefix)!=boundary['prefix_sha256']:raise ValueError('Old actual generation prefix differs')
                    payload=dict(input_ids=prefix,return_logprob=True,return_text_in_logprobs=False,
                        token_ids_logprob=[248069,248058,248046,198],logprob_start_len=len(prefix)-1,
                        sampling_params=options,stream=False)
                    probe_response=query('/generate',payload)
                    probe={str(value[1]):math.exp(value[0])for value in probe_response['meta_info']['output_token_ids_logprobs'][0]}
                    raw=output/'raw'/(str(index)+'-generation-prefix.json.gz')
                    with gzip.open(raw,'wt',encoding='utf-8')as blob:json.dump(dict(request=payload,response=probe_response),blob)
                    probe_raw=dict(path=str(raw.relative_to(output)),sha256=sha(raw))
                payload=dict(input_ids=row['input_ids'],return_logprob=True,return_text_in_logprobs=False,
                    logprob_start_len=row['target_positions'][0]-1,sampling_params=options,stream=False)
                response=query('/generate',payload)
                values=response['meta_info']['input_token_logprobs'];shift=len(row['input_ids'])-len(values)
                if not 0<=shift<=min(row['target_positions']):raise ValueError('Invalid causal logprob offset')
                measured=measured_row(row,response)
                if boundary:
                    measured['first_generated_teacher_token_probability']=math.exp(values[boundary['generation_prefix_tokens']-shift][0])
                    measured['at_actual_generation_prefix_probabilities']=probe
                    measured['raw_generation_prefix_probe']=probe_raw
                raw=output/'raw'/(str(index)+'.json.gz')
                with gzip.open(raw,'wt',encoding='utf-8')as blob:json.dump(dict(request=payload,response=response),blob)
                measured.update(raw_response=str(raw.relative_to(output)),raw_response_sha256=sha(raw))
                stream.write(json.dumps(dict(identity=identity,**measured))+'\n');stream.flush()
                memberships=list(identity['memberships'])
                if identity['dataset']=='m2'and identity['split']=='validation'and'affected_validation'not in memberships:
                    memberships.append('unaffected_validation121')
                for group in memberships:groups[group].append((identity,measured))
                print(json.dumps(dict(tag=tag,unique_rows_completed=index+1,expected443=True)),flush=True)
        summary={}
        for group,items in groups.items():
            categories=defaultdict(lambda:[0.,0]);tasks=defaultdict(list)
            for identity,value in items:
                tasks[identity['task_id']].append(value['sample_nll'])
                for name,n in value['category_tokens'].items():
                    categories[name][0]+=value['category_nll'][name]*n;categories[name][1]+=n
            summary[group]=dict(unique_rows=len(items),unique_tasks=len(tasks),
                sample_mean_nll=sum(v['sample_nll']for _,v in items)/len(items),
                token_mean_nll=sum(v['nll_sum']for _,v in items)/sum(v['supervised_tokens']for _,v in items),
                category_nll={k:v[0]/v[1]for k,v in categories.items()},
                task_sample_means={k:sum(v)/len(v)for k,v in tasks.items()})
        raw_manifest=output/'RAW_PAYLOAD_SHA256.json'
        raw_manifest.write_text(json.dumps({str(p.relative_to(output)):sha(p)for p in sorted((output/'raw').iterdir())},indent=2)+'\n')
        complete=dict(passed=True,tag=tag,unique_rows=443,unique_tasks=proof['unique_tasks'],groups=summary,
            raw_payload_manifest_sha256=sha(raw_manifest),
            deployment_sha256=sha(output/'DEPLOYMENT.json'),unique_rows_sha256=sha(output/'UNIQUE_ROWS.jsonl'),
            actual_server_model_path=live['model_path'],old_measured_row_implementation_unchanged=True,
            optimizer_updates=0,autonomous_task_success_claimed=False)
        (output/'OLD443_NLL_COMPLETE.json').write_text(json.dumps(complete,indent=2)+'\n')
    finally:subprocess.run(['systemctl','--user','stop',unit],check=True,timeout=60)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--tag',choices=TAGS);parser.add_argument('--check-only',action='store_true')
    args=parser.parse_args()
    if args.check_only:print(json.dumps(check_data()[1]))
    elif args.tag is None:parser.error('--tag is required for actual scoring')
    else:run(args.tag)
