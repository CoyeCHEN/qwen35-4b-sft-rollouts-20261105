"""The existing sole controller starts two explicitly authorized native Jobs."""
import hashlib
import importlib
import json
import os
from pathlib import Path
import shlex
import subprocess
import time
import urllib.request

R=Path('/ssd/chenkeyi/qwen35-sft-772-20261101')
E=R/'formal-native-eval-r1'
C=Path('/data/chenkeyi/qwen35-sft-772-20261101/control')
serving=importlib.import_module('cold-native-serving18-r2')
PY=R/'env/serve-new11-r1/bin/python'


def read(path):return json.loads(path.read_text())
def save(path,value):
    temp=path.with_name(path.name+'.tmp');temp.write_text(json.dumps(value,indent=2)+'\n');temp.replace(path)
def props(unit):
    return dict(line.split('=',1)for line in subprocess.check_output(['systemctl','--user','show',unit,
        '-p','LoadState','-p','ActiveState','-p','MainPID','-p','Result'],text=True).splitlines())


def forward():
    script="""import subprocess,json
unit='qwen35-new772-gpu78-forward18-20261102-r1.service'
p=dict(x.split('=',1)for x in subprocess.check_output(['systemctl','--user','show',unit,'-p','LoadState','-p','ActiveState','-p','MainPID'],text=True).splitlines())
if p['LoadState']=='not-found':
 subprocess.run(['systemd-run','--user','--unit='+unit,'--property=Restart=on-failure','--property=RestartSec=10s','/usr/bin/ssh','-F','/home/chenkeyi/.local/share/harbor-rsi/qwen35-new772-tb21-20261101/ssh/node18.conf','-N','-L','172.17.0.1:18306:127.0.0.1:18306','-L','172.17.0.1:18307:127.0.0.1:18307','qwen35-new772-forward18'],check=True,capture_output=True,text=True)
print(json.dumps(p))
"""
    result=subprocess.run(['/usr/bin/ssh','-F',str(R/'control-ssh/formal-engine149-r1.conf'),'127.0.0.1',
        'python3 -c '+shlex.quote(script)],capture_output=True,text=True,check=True,timeout=20)
    return json.loads(result.stdout)


def deploy(model):
    marker=R/'checks'/('DIAGNOSTIC30_SERVING_'+model['tag']+'.json')
    manifest=Path(model['model_manifest']);version=serving.sha(manifest)
    if marker.exists():
        value=read(marker);assert value['weight_version']==version
        return value
    if model.get('reuse_service'):
        value=dict(model,weight_version=version,reused_existing_service=True,at=time.time())
        save(marker,value);return value
    observed=subprocess.check_output(['nvidia-smi','-i',str(model['gpu_index']),
        '--query-gpu=uuid,memory.used','--format=csv,noheader,nounits'],text=True).strip().split(',')
    assert observed[0].strip()==model['gpu_uuid']and int(observed[1])==0,'Preserve another GPU owner'
    assert not subprocess.check_output(['ss','-ltn','sport = :'+str(model['port'])],text=True).splitlines()[1:]
    assert props(model['serving_unit'])['LoadState']=='not-found'
    for item in read(manifest)['files']:
        name=item.get('name',item.get('path',item.get('file')));path=Path(model['model_path'])/name
        assert path.stat().st_size==item['bytes']and serving.sha(path)==item['sha256']
    seed=read(R/'checks/M0_NEW11_NATIVE_SERVING_COMMAND_R2.json')['command']
    command=seed[seed.index(str(PY)):]
    command[command.index('--model-path')+1]=model['model_path'];command[command.index('--port')+1]=str(model['port'])
    command+=['--served-model-name',model['model_id'],'--weight-version',version]
    env=dict(CUDA_VISIBLE_DEVICES=model['gpu_uuid'],HF_HUB_OFFLINE='1',OMP_NUM_THREADS='4',
        PATH=str(PY.parent)+':/usr/local/cuda/bin:/usr/bin:/bin',TMPDIR=str(R/'tmp'),
        TRITON_CACHE_DIR=str(R/'cache/triton'),TORCH_EXTENSIONS_DIR=str(R/'cache/torch-extensions'),
        CUDA_CACHE_PATH=str(R/'cache/cuda'),XDG_CACHE_HOME=str(R/'cache/xdg'),HF_HOME=str(R/'cache/hf'))
    argv=['systemd-run','--user','--unit='+model['serving_unit'],'--property=MemoryMax=96G',
        '--property=StandardOutput=append:'+str(R/'logs'/('gpu78-serving-'+model['tag']+'.log')),
        '--property=StandardError=append:'+str(R/'logs'/('gpu78-serving-'+model['tag']+'.log'))]
    argv+=['--setenv='+key+'='+value for key,value in env.items()];argv+=command
    subprocess.run(argv,capture_output=True,text=True,check=True)
    value=dict(model,weight_version=version,command=argv,at=time.time(),hot_weight_switching=False)
    save(marker,value);return value


def advance(owner,state):
    config=read(R/'configs/diagnostic30-four-model-r1.json')
    assert read(C/'NATIVE_ADVANCE_OWNER.json')==owner
    assert config['authorized_gpu_indices']==[6,7]and config['expected_trials']==120
    state['gpu78_forward']=forward();observed=[]
    models=[]
    for item in config['models']:
        binding=R/'checks'/('DIAGNOSTIC30_MODEL_BINDING_'+item['tag']+'.json')
        if binding.exists():
            models.append(read(binding));continue
        model=dict(item)
        if item['tag']=='new-m2-e1-diag':
            prior=next((x for x in config['models'] if x['tag']in ['new-m1-e5-diag','new-m2-e3-diag'] and (E/'checks'/('DIAGNOSTIC30_NATIVE_ALL_TERMINAL_'+x['tag']+'.json')).exists()),None)
            if prior is None:
                observed.append(dict(tag=item['tag'],status='WAITING_ONE_AUTHORIZED_DIAGNOSTIC_GPU'));continue
            # Stop only the completed diagnostic's own cold service before reuse.
            if props(prior['serving_unit'])['ActiveState']=='active':
                subprocess.run(['systemctl','--user','stop',prior['serving_unit']],check=True,timeout=60)
            for key in ['gpu_index','gpu_uuid','port']:model[key]=prior[key]
        save(binding,model);models.append(model)
    # Start both cold servers before waiting for either one to become ready.
    for model in models:
        complete=E/'checks'/('DIAGNOSTIC30_NATIVE_ALL_TERMINAL_'+model['tag']+'.json')
        if not complete.exists():deploy(model)
    for model in models:
        complete=E/'checks'/('DIAGNOSTIC30_NATIVE_ALL_TERMINAL_'+model['tag']+'.json')
        if complete.exists():
            assert read(complete)['terminal']==model['new_trials']
            if not model.get('reuse_service') and props(model['serving_unit'])['ActiveState']=='active':
                subprocess.run(['systemctl','--user','stop',model['serving_unit']],check=True,timeout=60)
            observed.append(dict(tag=model['tag'],status='NATIVE_REGISTERED_TRIALS_TERMINAL',proof=str(complete)));continue
        deployed=read(R/'checks'/('DIAGNOSTIC30_SERVING_'+model['tag']+'.json'))
        opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
        try:
            with opener.open('http://127.0.0.1:'+str(model['port'])+'/model_info',timeout=3)as response:live=json.loads(response.read())
        except OSError:
            observed.append(dict(tag=model['tag'],status='COLD_STARTING',unit=props(model['serving_unit'])));continue
        assert live['model_path']==model['model_path']and live['weight_version']==deployed['weight_version']
        admission=E/'manifests'/('DIAGNOSTIC30_ADMISSION_'+model['tag']+'.json')
        unit=props(model['job_unit'])
        if not admission.exists():
            assert unit['LoadState']=='not-found'and not(E/'jobs'/model['job_name']).exists()
            probe="import urllib.request,json; p=urllib.request.build_opener(urllib.request.ProxyHandler({})); print(json.dumps(json.load(p.open('http://172.17.0.1:"+str(model['port'])+"/model_info',timeout=5))))"
            result=subprocess.run(['/usr/bin/ssh','-F',str(R/'control-ssh/formal-engine149-r1.conf'),'127.0.0.1',
                'python3 -c '+shlex.quote(probe)],capture_output=True,text=True,check=True,timeout=15)
            remote_info=json.loads(result.stdout)
            assert remote_info['model_path']==model['model_path']and remote_info['weight_version']==deployed['weight_version']
            save(admission,dict(unique_controller_owner=owner,at=time.time(),model=deployed,
                source_sha256=serving.sha(R/'run-30task-native-diagnostic18-r1.py'),
                plan_sha256=serving.sha(E/'manifests/DIAGNOSTIC30_120_TRIAL_PLAN_R1.json'),formal_801_excluded=True))
            subprocess.run(['systemd-run','--user','--unit='+model['job_unit'],'--property=MemoryMax=32G',
                '--property=StandardOutput=append:'+str(R/'logs'/('gpu78-native-'+model['tag']+'.log')),
                '--property=StandardError=append:'+str(R/'logs'/('gpu78-native-'+model['tag']+'.log')),
                str(R/'env/harbor-native-eval-r1/bin/python'),str(E/'scripts/run-30task-native-diagnostic18-r1.py'),
                model['tag']],capture_output=True,text=True,check=True)
        observed.append(dict(tag=model['tag'],status='NATIVE_JOB_REQUESTED_OR_RUNNING',unit=props(model['job_unit']),
            progress=read(E/'checks'/('DIAGNOSTIC30_STATUS_'+model['tag']+'.json'))if(E/'checks'/('DIAGNOSTIC30_STATUS_'+model['tag']+'.json')).exists()else None))
    value=dict(at=time.time(),expected=120,models=observed,unique_controller_owner=owner,
        formal_801_excluded=True,source_sha256=serving.sha(Path(__file__)))
    save(C/'DIAGNOSTIC30_DIAGNOSTIC_STATUS_R1.json',value);state['gpu78_diagnostics']=value
