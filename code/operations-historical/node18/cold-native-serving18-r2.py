"""Deploy fixed model releases with native SGLang/systemd; no provider or queue abstraction."""
import hashlib
import importlib
import json
from pathlib import Path
import subprocess
import urllib.request

R=Path('/ssd/chenkeyi/qwen35-sft-772-20261101')
PY=R/'env/serve-new11-r1/bin/python'
def sha(p):
    h=hashlib.sha256()
    with p.open('rb')as f:
        for b in iter(lambda:f.read(8*1024*1024),b''):h.update(b)
    return h.hexdigest()


def identity(tag):
    models={
      'm0':('assets/source17-r1/student-tokenizer','checks/M0_FIXED_REVISION_WEIGHT_SHA.json',18300,0),
      'new-m1-e5':('runs/new-m1-cf416-128k-e5','runs/new-m1-cf416-128k-e5/HF_EXPORT_COMPLETE.json',18301,1),
      'new-m2-e5':('runs/new-m2-tmax356-128k-e5','runs/new-m2-tmax356-128k-e5/HF_EXPORT_COMPLETE.json',18302,2),
      'new-m1-epoch3':('epoch-models/new-m1-epoch3','epoch-models/new-m1-epoch3/EPOCH_MODEL_EXPORT_COMPLETE.json',18303,4),
      'new-m2-epoch3':('epoch-models/new-m2-epoch3','epoch-models/new-m2-epoch3/EPOCH_MODEL_EXPORT_COMPLETE.json',18303,4),
      'new-m1-epoch3-fixed':('epoch-models/new-m1-epoch3','epoch-models/new-m1-epoch3/EPOCH_MODEL_EXPORT_COMPLETE.json',18303,4),
      'new-m2-epoch3-fixed':('epoch-models/new-m2-epoch3','epoch-models/new-m2-epoch3/EPOCH_MODEL_EXPORT_COMPLETE.json',18303,4)}
    model,proof,port,gpu=models[tag]
    p=R/proof;assert p.is_file()
    return dict(tag=tag,model_path=str(R/model),weight_version=sha(p),model_manifest=str(p),port=port,gpu_index=gpu,
        model_id='qwen35-new772-'+tag,unit='qwen35-new772-cold-'+tag+'-20261101.service')


def start(tag):
    value=identity(tag)
    assets=importlib.import_module('snapshot-epoch-hf18-r1').ASSETS
    assert all(sha(Path(value['model_path'])/name)==digest for name,digest in assets.items())
    assert sha(PY.parent.parent/'lib/python3.11/site-packages/sglang/srt/entrypoints/openai/serving_chat.py')=='b521132c6332a5a5796f2aad27e0837ebb376afcfddd1940415328f788821dfd'
    previous=R/'checks'/('COLD_SERVING_DEPLOYMENT_'+tag+'.json')
    if previous.exists():
        saved=json.loads(previous.read_text());assert saved['weight_version']==value['weight_version']
        return saved
    gpu=subprocess.check_output(['nvidia-smi','-i',str(value['gpu_index']),'--query-gpu=uuid,memory.used',
        '--format=csv,noheader,nounits'],text=True).strip().split(',')
    assert int(gpu[1])<100,'Authorized GPU occupied; preserve the other task'
    allowed=json.loads((R/'new-sft/workspace/configs/runtime.json').read_text())['authorized_gpu_uuids']
    assert gpu[0].strip()==allowed[value['gpu_index']]
    release=json.loads(Path(value['model_manifest']).read_text())
    for member in release['files']:
        name=member.get('file',member.get('path',member.get('name')))
        file=Path(value['model_path'])/name
        assert file.stat().st_size==member['bytes'] and sha(file)==member['sha256'],'Cold model release changed: '+name
    assert not subprocess.check_output(['ss','-ltn','sport = :'+str(value['port'])],text=True).splitlines()[1:]
    seed=json.loads((R/'checks/M0_NEW11_NATIVE_SERVING_COMMAND_R2.json').read_text())['command']
    server=seed[seed.index(str(PY)):]
    server[server.index('--model-path')+1]=value['model_path']
    server[server.index('--port')+1]=str(value['port'])
    server+=['--served-model-name',value['model_id'],'--weight-version',value['weight_version']]
    env=dict(CUDA_VISIBLE_DEVICES=gpu[0].strip(),PATH=str(PY.parent)+':/usr/local/cuda/bin:/usr/bin:/bin',
        HF_HUB_OFFLINE='1',OMP_NUM_THREADS='4',TMPDIR=str(R/'tmp'),
        TRITON_CACHE_DIR=str(R/'cache/triton'),TORCH_EXTENSIONS_DIR=str(R/'cache/torch-extensions'),
        CUDA_CACHE_PATH=str(R/'cache/cuda'),XDG_CACHE_HOME=str(R/'cache/xdg'),HF_HOME=str(R/'cache/hf'))
    cmd=['systemd-run','--user','--unit='+value['unit'],'--property=MemoryMax=96G',
        '--property=StandardOutput=append:'+str(R/'logs'/('cold-'+tag+'.log')),
        '--property=StandardError=append:'+str(R/'logs'/('cold-'+tag+'.log'))]
    cmd+=['--setenv='+k+'='+v for k,v in env.items()]
    cmd+=server
    subprocess.run(cmd,check=True,capture_output=True,text=True)
    value.update(command=cmd,gpu_uuid=gpu[0].strip(),hot_weight_switching=False)
    previous.write_text(json.dumps(value,indent=2)+'\n')
    return value


def info(tag):
    value=identity(tag)
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open('http://127.0.0.1:'+str(value['port'])+'/model_info',timeout=5)as response:
        live=json.loads(response.read())
    assert live['model_path']==value['model_path'] and live['weight_version']==value['weight_version']
    assert live.get('has_image_understanding')
    return value|dict(actual_model_info=live)


def stop(tag):
    value=identity(tag)
    subprocess.run(['systemctl','--user','stop',value['unit']],check=True,timeout=60)
