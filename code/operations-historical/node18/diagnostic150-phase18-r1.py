"""Existing native Harbor queues, explicit GPU replicas, one controller owner."""
import hashlib
import importlib
import json
from pathlib import Path
import shlex
import subprocess
import time
import urllib.request

R=Path('/ssd/chenkeyi/qwen35-sft-772-20261101');E=R/'formal-native-eval-r1'
C=Path('/data/chenkeyi/qwen35-sft-772-20261101/control')
serving=importlib.import_module('cold-native-serving18-r2')
PY=R/'env/serve-new11-r1/bin/python'
def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,v):
    temporary=p.with_name(p.name+'.tmp');temporary.write_text(json.dumps(v,indent=2)+'\n');temporary.replace(p)
def props(unit):return dict(x.split('=',1)for x in subprocess.check_output(['systemctl','--user','show',unit,'-p','LoadState','-p','ActiveState','-p','MainPID','-p','Result'],text=True).splitlines())
def info(port):
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open('http://127.0.0.1:'+str(port)+'/model_info',timeout=3)as response:return json.loads(response.read())


def forward():
    code="""import subprocess,json
unit='qwen35-new772-diag150-forward18-20261102-r1.service'
p=dict(x.split('=',1)for x in subprocess.check_output(['systemctl','--user','show',unit,'-p','LoadState','-p','ActiveState','-p','MainPID'],text=True).splitlines())
if p['LoadState']=='not-found':
 subprocess.run(['systemd-run','--user','--unit='+unit,'--property=Restart=on-failure','--property=RestartSec=10s','/usr/bin/ssh','-F','/home/chenkeyi/.local/share/harbor-rsi/qwen35-new772-tb21-20261101/ssh/node18.conf','-N','-L','172.17.0.1:18308:127.0.0.1:18308','-L','172.17.0.1:18309:127.0.0.1:18309','qwen35-new772-forward18'],check=True,capture_output=True,text=True)
print(json.dumps(p))
"""
    p=subprocess.run(['/usr/bin/ssh','-F',str(R/'control-ssh/formal-engine149-r1.conf'),'127.0.0.1','python3 -c '+shlex.quote(code)],capture_output=True,text=True,timeout=20,check=True)
    return json.loads(p.stdout)


def start_replica(model,replica):
    marker=R/'checks'/('USER_EVAL_SERVING_'+model['tag']+'_gpu'+str(replica['gpu_index'])+'.json')
    if marker.exists():
        saved=read(marker);assert saved['weight_version']==model['weight_version'];return saved
    assert sha(Path(model['model_manifest']))==model['weight_version']
    if replica.get('reuse_running'):
        live=info(replica['port']);assert live['model_path']==model['model_path']and live['weight_version']==model['weight_version']
        value=dict(model_tag=model['tag'],**replica,model_path=model['model_path'],weight_version=model['weight_version'],reused_running_cold_model=True,at=time.time());save(marker,value);return value
    raw=subprocess.check_output(['nvidia-smi','-i',str(replica['gpu_index']),'--query-gpu=uuid,memory.used','--format=csv,noheader,nounits'],text=True).strip().split(',')
    pids=subprocess.check_output(['nvidia-smi','-i',str(replica['gpu_index']),'--query-compute-apps=pid','--format=csv,noheader,nounits'],text=True).strip()
    assert raw[0].strip()==replica['gpu_uuid']and int(raw[1])<=4 and not pids,'Preserve another GPU owner'
    assert replica['gpu_uuid']in read(R/'new-sft/workspace/configs/runtime.json')['authorized_gpu_uuids']
    assert props(replica['unit'])['LoadState']=='not-found'
    assert not subprocess.check_output(['ss','-ltn','sport = :'+str(replica['port'])],text=True).splitlines()[1:]
    for item in read(Path(model['model_manifest']))['files']:
        name=item.get('path',item.get('name',item.get('file')));path=Path(model['model_path'])/name
        assert path.stat().st_size==item['bytes']and serving.sha(path)==item['sha256']
    seed=read(R/'checks/M0_NEW11_NATIVE_SERVING_COMMAND_R2.json')['command'];command=seed[seed.index(str(PY)):]
    command[command.index('--model-path')+1]=model['model_path'];command[command.index('--port')+1]=str(replica['port'])
    command+=['--served-model-name',model['model_id'],'--weight-version',model['weight_version']]
    env=dict(CUDA_VISIBLE_DEVICES=replica['gpu_uuid'],HF_HUB_OFFLINE='1',OMP_NUM_THREADS='4',
        PATH=str(PY.parent)+':/usr/local/cuda/bin:/usr/bin:/bin',TMPDIR=str(R/'tmp'),
        TRITON_CACHE_DIR=str(R/'cache/triton'),TORCH_EXTENSIONS_DIR=str(R/'cache/torch-extensions'),
        CUDA_CACHE_PATH=str(R/'cache/cuda'),XDG_CACHE_HOME=str(R/'cache/xdg'),HF_HOME=str(R/'cache/hf'))
    log=R/'logs'/('user-eval-'+model['tag']+'-gpu'+str(replica['gpu_index'])+'.log')
    argv=['systemd-run','--user','--unit='+replica['unit'],'--property=MemoryMax=96G',
        '--property=StandardOutput=append:'+str(log),'--property=StandardError=append:'+str(log)]
    argv+=['--setenv='+key+'='+value for key,value in env.items()];argv+=command
    subprocess.run(argv,check=True,capture_output=True,text=True)
    value=dict(model_tag=model['tag'],**replica,model_path=model['model_path'],weight_version=model['weight_version'],command=argv,at=time.time(),hot_weight_switch=False);save(marker,value);return value


def ready(model):
    observed=[]
    for replica in model['replicas']:
        try:live=info(replica['port'])
        except OSError:return None
        assert live['model_path']==model['model_path']and live['weight_version']==model['weight_version']
        probe="import urllib.request,json;p=urllib.request.build_opener(urllib.request.ProxyHandler({}));print(json.dumps(json.load(p.open('http://172.17.0.1:"+str(replica['port'])+"/model_info',timeout=5))))"
        out=subprocess.run(['/usr/bin/ssh','-F',str(R/'control-ssh/formal-engine149-r1.conf'),'127.0.0.1','python3 -c '+shlex.quote(probe)],capture_output=True,text=True,check=True,timeout=15)
        remote=json.loads(out.stdout);assert remote==live
        observed.append(dict(replica=replica,model_info=live))
    return observed


def launch(model,owner,full=False):
    tag=model['tag'];admission=E/'manifests/SELECTED267_ADMISSION_R1.json'if full else E/'manifests'/('DIAGNOSTIC150_ADMISSION_'+tag+'_R1.json')
    status=props(model['job_unit'])
    if admission.exists():return dict(tag=tag,status='NATIVE_JOB_EXISTING',unit=status)
    live=ready(model)
    if live is None:return dict(tag=tag,status='COLD_SERVERS_STARTING')
    assert status['LoadState']=='not-found'and not(E/'jobs'/model['job_name']).exists()
    save(admission,dict(unique_controller_owner=owner,at=time.time(),model=model,replicas=live,
        source_sha256=sha(E/'scripts/run-user-evaluation-native18-r1.py'),old_801_excluded=True))
    subprocess.run(['systemd-run','--user','--unit='+model['job_unit'],'--property=MemoryMax=32G',
        '--property=StandardOutput=append:'+str(R/'logs'/('user-native-'+tag+'.log')),
        '--property=StandardError=append:'+str(R/'logs'/('user-native-'+tag+'.log')),
        str(R/'env/harbor-native-eval-r1/bin/python'),str(E/'scripts/run-user-evaluation-native18-r1.py'),tag],check=True,capture_output=True,text=True)
    return dict(tag=tag,status='NATIVE_JOB_STARTED',replicas=live,unit=props(model['job_unit']))


def advance(owner,state):
    assert read(C/'NATIVE_ADVANCE_OWNER.json')==owner
    cfg=read(R/'configs/diagnostic150-five-model-r1.json');state['user_scope']='COMMON30_FIVE_MODELS_THEN_WINNER89_N3'
    state['forward_extra']=forward()
    handover=R/'checks/DIAG150_IDLE_CARD_HANDOVER_R1.json'
    if not handover.exists():
        assert read(R/'checks/FORMAL_CONTROLLER18_M0_NATIVE_JOINT_ACCEPTANCE_R1.json')['passed']
        assert props('qwen35-formal-controller18-m0-native-joint-20261102-r1.service')['ActiveState']=='inactive'
        assert not(C/'native-phase-requests/formal-n3.json').exists()
        stopped=[]
        for tag in ['m0','new-m1-e5']:
            binding=read(R/'checks'/('COLD_SERVING_DEPLOYMENT_'+tag+'.json'));unit=binding['unit']
            assert info(binding['port'])['weight_version']==binding['weight_version']
            if props(unit)['ActiveState']=='active':subprocess.run(['systemctl','--user','stop',unit],check=True,timeout=60)
            stopped.append(dict(tag=tag,unit=unit,previous=binding))
        save(handover,dict(at=time.time(),completed_idle_services_stopped=stopped,
            healthy_gpu4_6_7_jobs_untouched=True,old801_never_dispatched=True))
    observed=[]
    for model in cfg['models']:
        if model.get('legacy_running'):
            marker=E/'checks'/('DIAGNOSTIC30_STATUS_'+model['tag']+'.json')
            observed.append(dict(tag=model['tag'],status='PRESERVED_NATIVE_JOB',unit=props(model['job_unit']),progress=read(marker)if marker.exists()else None));continue
        binding=R/'checks'/('DIAGNOSTIC150_MODEL_BINDING_'+model['tag']+'.json')
        if not binding.exists():save(binding,model)
        else:assert read(binding)==model
        for replica in model['replicas']:start_replica(model,replica)
    for model in cfg['models']:
        if model.get('legacy_running'):continue
        row=launch(model,owner);p=E/'checks'/('DIAGNOSTIC30_STATUS_'+model['tag']+'.json')
        row['progress']=read(p)if p.exists()else None;observed.append(row)
    value=dict(at=time.time(),expected=150,models=observed,unique_controller_owner=owner,
        user_requested_all_eight_gpus=True,old_801_auto_dispatch_disabled=True,selected_full_n3_trials=267)
    save(C/'DIAGNOSTIC30_DIAGNOSTIC_STATUS_R1.json',value);state['diagnostic150']=value
    state['status']='FIVE_MODEL_COMMON30_RUNNING'
