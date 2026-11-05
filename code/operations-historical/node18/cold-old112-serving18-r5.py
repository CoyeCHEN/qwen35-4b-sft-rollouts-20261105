"""Cold-start one of14 fixed old-study releases using the native SGLang CLI."""
import importlib
import json
from pathlib import Path
import subprocess
import urllib.request

R=Path('/ssd/chenkeyi/qwen35-sft-772-20261101')
P=R/'old-four-arm'
PY=R/'env/serve-new11-r1/bin/python'
GPU='GPU-9d89f519-51e1-68e2-b522-6e8c1bdc1130'
sha=importlib.import_module('snapshot-epoch-hf18-r2').sha
TAGS=['old-M1','old-M2']+[a+'-epoch'+str(e)for a in 'ABCD'for e in (1,3,5)]


def entry(tag):
    if tag not in TAGS:raise ValueError('Only14 preregistered old releases are authorized')
    target=P/'epoch-models'/tag;marker=target/'OLD_READOUT_HF_COMPLETE.json'
    return dict(tag=tag,model_path=str(target),model_manifest=str(marker),
        weight_version=sha(marker),model_id='qwen35-old-study-'+tag.lower(),
        gpu_uuid=GPU,unit='qwen35-old112-cold-'+tag.lower()+'-20261101.service',port=18303)


def start(tag):
    if not importlib.import_module('old-four-after-selected267-phase18-r5').selected267_gate()['passed']:
        raise ValueError('Old serving requires actual selected267 terminal and Recorder audit')
    importlib.import_module('old443-readout18-r5').sealed_model(tag)
    value=entry(tag);previous=P/'checks'/('OLD112_COLD_DEPLOYMENT_'+tag+'.json')
    if previous.exists():
        stored=json.loads(previous.read_text())
        if stored['weight_version']!=value['weight_version']:raise ValueError('Preserve original old deployment identity')
        return stored
    gpu=subprocess.check_output(['nvidia-smi','-i','4','--query-gpu=uuid,memory.used',
        '--format=csv,noheader,nounits'],text=True).strip().split(',')
    apps=subprocess.check_output(['nvidia-smi','--query-compute-apps=gpu_uuid,pid','--format=csv,noheader'],text=True)
    if gpu[0].strip()!=GPU or int(gpu[1])!=0 or any(line.startswith(GPU)for line in apps.splitlines()):
        raise ValueError('Preserve any existing GPU4 owner or CUDA allocation')
    if subprocess.check_output(['ss','-ltn','sport = :18303'],text=True).splitlines()[1:]:
        raise ValueError('Preserve an existing service on the owned diagnostic port')
    if sha(PY.parent.parent/'lib/python3.11/site-packages/sglang/srt/entrypoints/openai/serving_chat.py')!='b521132c6332a5a5796f2aad27e0837ebb376afcfddd1940415328f788821dfd':
        raise ValueError('Canonical native serving codec changed')
    release=json.loads(Path(value['model_manifest']).read_text())
    for member in release['files']:
        file=Path(value['model_path'])/member['name']
        if file.stat().st_size!=member['bytes']or sha(file)!=member['sha256']:
            raise ValueError('Old release changed: '+member['name'])
    seed=json.loads((R/'checks/M0_NEW11_NATIVE_SERVING_COMMAND_R2.json').read_text())['command']
    server=seed[seed.index(str(PY)):]
    server[server.index('--model-path')+1]=value['model_path'];server[server.index('--port')+1]='18303'
    server+=['--served-model-name',value['model_id'],'--weight-version',value['weight_version']]
    env=dict(CUDA_VISIBLE_DEVICES=GPU,PATH=str(PY.parent)+':/usr/local/cuda/bin:/usr/bin:/bin',
        HF_HUB_OFFLINE='1',OMP_NUM_THREADS='4',TMPDIR=str(R/'tmp'),
        TRITON_CACHE_DIR=str(R/'cache/triton'),TORCH_EXTENSIONS_DIR=str(R/'cache/torch-extensions'),
        CUDA_CACHE_PATH=str(R/'cache/cuda'),XDG_CACHE_HOME=str(R/'cache/xdg'),HF_HOME=str(R/'cache/hf'))
    command=['systemd-run','--user','--unit='+value['unit'],'--property=MemoryMax=96G',
        '--property=StandardOutput=append:'+str(R/'logs'/('old112-cold-'+tag+'.log')),
        '--property=StandardError=append:'+str(R/'logs'/('old112-cold-'+tag+'.log'))]
    command+=['--setenv='+k+'='+v for k,v in env.items()];command+=server
    subprocess.run(command,check=True,capture_output=True,text=True)
    value.update(command=command,hot_weight_switching=False,original_task_limits_and_ten_tools=True)
    previous.write_text(json.dumps(value,indent=2)+'\n');return value


def info(tag):
    value=entry(tag);opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open('http://127.0.0.1:18303/model_info',timeout=5)as response:live=json.loads(response.read())
    if live['model_path']!=value['model_path']or live['weight_version']!=value['weight_version']or not live.get('has_image_understanding'):
        raise ValueError('Actual old service identity/image capability differs')
    return value|dict(actual_model_info=live)


def stop(tag):
    # The phase calls this only after all8 Raw Results and native cleanup are closed.
    unit='qwen35-old112-cold-'+tag.lower()+'-20261101.service'
    status=dict(x.split('=',1)for x in subprocess.check_output(['systemctl','--user','show',unit,'-p','MainPID','-p','ActiveState'],text=True).splitlines())
    if status['ActiveState']=='inactive':return
    assert status['ActiveState']=='active'and int(status['MainPID'])>0
    info(tag)
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open('http://127.0.0.1:18303/get_load',timeout=5)as response:load=json.load(response)
    assert load and all(x['num_reqs']==x['num_waiting_reqs']==0 for x in load),'Preserve active or queued model requests'
    subprocess.run(['systemctl','--user','stop','qwen35-old112-cold-'+tag.lower()+'-20261101.service'],check=True,timeout=60)
