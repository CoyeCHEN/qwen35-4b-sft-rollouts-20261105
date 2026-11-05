"""Observe the14 fixed old-study models and invoke the existing finite NLL reader."""
import importlib
import json
from pathlib import Path
import subprocess
import time

R=Path('/ssd/chenkeyi/qwen35-sft-772-20261101')
P=R/'old-four-arm'
C=Path('/data/chenkeyi/qwen35-sft-772-20261101/control')
GPU='GPU-7b634c3e-13ae-5243-19dd-b6edddf9a543'


def advance(state):
    gate=importlib.import_module('resume-old-four-native18-r2').admitted()
    if not gate['admitted']:
        state['old443_readouts']='DEFERRED_UNTIL_ACTUAL_FORMAL_801_COMPLETE'
        return
    plan=json.loads((P/'manifests/behavior-pre-registration.json').read_text())
    expected=['old-M1','old-M2']+[a+'-epoch'+str(e)for a in 'ABCD'for e in (1,3,5)]
    if set(plan['models'])!=set(expected):raise ValueError('Old14 model preregistration differs')
    observed=[];experiments=json.loads((P/'manifests/experiments.json').read_text())
    for tag in expected:
        output=P/'readouts443'/tag;complete=output/'OLD443_NLL_COMPLETE.json'
        if complete.exists():
            proof=json.loads(complete.read_text())
            if not proof['passed']or proof['tag']!=tag or proof['unique_rows']!=443:
                raise ValueError('Old443 coverage/identity differs')
            observed.append(dict(tag=tag,status='complete',proof=str(complete)));continue
        unit='qwen35-old443-reader-'+tag.lower()+'-20261101-r1.service'
        props=dict(x.split('=',1)for x in subprocess.check_output(['systemctl','--user','show',unit,
            '-p','LoadState','-p','MainPID','-p','ActiveState','-p','Result'],text=True).splitlines())
        if props['ActiveState']=='active':
            observed.append(dict(tag=tag,status='native_readout_running',unit=props));break
        if output.exists()or props['LoadState']!='not-found':
            observed.append(dict(tag=tag,status='prior_native_readout_requires_inspection',unit=props));break
        if not tag.startswith('old-'):
            arm,epoch=tag.split('-epoch')
            if not(Path(experiments['arms'][arm]['output_dir'])/('checkpoint-'+str(106*int(epoch)))/'CHECKPOINT_COMPLETE.json').exists():continue
        actual=subprocess.check_output(['nvidia-smi','-i','5','--query-gpu=uuid,memory.used',
            '--format=csv,noheader,nounits'],text=True).strip().split(',')
        if actual[0].strip()!=GPU:raise ValueError('Old NLL GPU5 identity changed')
        if int(actual[1])!=0:
            observed.append(dict(tag=tag,status='waiting_for_idle_authorized_gpu5'));break
        command=['systemd-run','--user','--unit='+unit,'--property=MemoryMax=96G',
            '--property=StandardOutput=append:'+str(R/'logs'/('old443-'+tag+'.log')),
            '--property=StandardError=append:'+str(R/'logs'/('old443-'+tag+'.log')),
            str(R/'env/train-r1/bin/python'),str(R/'old443-readout18-r1.py'),'--tag',tag]
        subprocess.run(command,check=True,capture_output=True,text=True)
        observed.append(dict(tag=tag,status='native_finite_readout_submitted',gpu_uuid=GPU));break
    state['old443_readouts']=observed
    p=C/'OLD443_NATIVE_READOUT_STATUS.json';tmp=p.with_name(p.name+'.tmp')
    tmp.write_text(json.dumps(dict(at=time.time(),readouts=observed,planned_models=14,
        actual_complete=sum(x['status']=='complete'for x in observed),
        rows_per_model=443,unique_tasks_per_model=100,only_after_new_formal801=True),indent=2)+'\n');tmp.replace(p)
