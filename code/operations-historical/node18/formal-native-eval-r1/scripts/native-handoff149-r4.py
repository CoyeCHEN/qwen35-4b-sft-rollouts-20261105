"""Restricted SSH admission for fixed native Harbor jobs; no Trial scheduling."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

R=Path('/home/chenkeyi/.local/share/harbor-rsi/qwen35-new772-tb21-20261101')
O=R.parent/'qwen35-old-m2-four-arm-20261101'
PY=str(R.parent/'qwen35-m1-m2-tb21-20261026/venv/bin/python')
MODES={
 'formal-n3':(R,'qwen35-new772-formal801-20261101','run-formal-native-tb21149-r4.py',[],
     'THREE_MODEL_COLD_SERVING_ADMISSION.json','FORMAL_801_ALL_TERMINAL.json','FORMAL_801_STATUS.json'),
 'new-m1-epoch3':(R,'qwen35-new772-new-m1-epoch3-20261101','run-epoch3-native-tb21149-r1.py',['new-m1'],
     'EPOCH3_SERVING_ADMISSION_new-m1.json','EPOCH3_DIAGNOSTIC_ALL_TERMINAL_new-m1.json','EPOCH3_DIAGNOSTIC_STATUS_new-m1.json'),
 'new-m2-epoch3':(R,'qwen35-new772-new-m2-epoch3-20261101','run-epoch3-native-tb21149-r1.py',['new-m2'],
     'EPOCH3_SERVING_ADMISSION_new-m2.json','EPOCH3_DIAGNOSTIC_ALL_TERMINAL_new-m2.json','EPOCH3_DIAGNOSTIC_STATUS_new-m2.json')}
TAGS=['old-M1','old-M2']+[a+'-epoch'+str(e)for a in 'ABCD'for e in (1,3,5)]
for tag in TAGS:
    MODES['old-'+tag]=(O,'qwen35-old-four-behavior-'+tag.lower()+'-20261101','run-old112-native149-r1.py',[tag],
        'SERVING_ADMISSION_'+tag+'.json','OLD112_ALL_TERMINAL_'+tag+'.json','OLD112_STATUS_'+tag+'.json')


def states():
    answer={}
    for mode,(root,unit,script,args,admission,complete,progress)in MODES.items():
        p=root/'checks'/complete;q=root/'checks'/progress
        answer[mode]=dict(unit=unit,complete=json.loads(p.read_text())if p.exists()else None,
            progress=json.loads(q.read_text())if q.exists()else None,
            systemd=subprocess.check_output(['systemctl','--user','show',unit,'-p','MainPID','-p','ActiveState','-p','Result'],text=True))
    return answer


def main():
    mode=os.environ.get('SSH_ORIGINAL_COMMAND','')
    if mode=='status':print(json.dumps(dict(at=time.time(),modes=states())));return
    if mode not in MODES:raise ValueError('Only fixed campaign actions are authorized')
    raw=sys.stdin.buffer.read(5*1024*1024+1)
    if len(raw)>5*1024*1024:raise ValueError('Oversized deployment admission')
    value=json.loads(raw);owner=value['unique_controller_owner']
    if not(owner['kind']=='UNIQUE_NATIVE_ADVANCE_NODE18'and owner['host']=='bm-220acn7'and owner['pid']>0
        and owner['collection_closed']and owner['old_four_deferred_until_801_terminal']):
        raise ValueError('Expected the sole Ceph-lock controller owner')
    root,unit,script,args,admission,complete,progress=MODES[mode]
    if value['native_runner_sha256']!=hashlib.sha256((root/'scripts'/script).read_bytes()).hexdigest():
        raise ValueError('Native deployment entry source changed')
    if mode=='formal-n3':
        if not(value['new_m1_epoch5_verified']and value['new_m2_epoch5_verified']):raise ValueError('Both final models must be admitted')
    elif mode.startswith('old-'):
        gate=json.loads((R/'checks/FORMAL_801_ALL_TERMINAL.json').read_text())
        if not gate['completed']or gate['actual_terminal']!=801 or not value['new_formal801_completed']:
            raise ValueError('Old behavior must wait for actual formal801 completion')
        if value['model_tag']!=args[0]:raise ValueError('Old model identity differs')
        if value['old112_plan_sha256']!=hashlib.sha256((O/'manifests/OLD112_NATIVE_DEPLOYMENT_PLAN_R1.json').read_bytes()).hexdigest():
            raise ValueError('Old112 preregistration changed')
    elif not(value['epoch']==3 and value['model_is_final_epoch5']is False):raise ValueError('Expected a separate E3 diagnostic')
    destination=root/'manifests'/admission;encoded=json.dumps(value,ensure_ascii=False,indent=2)+'\n'
    if destination.exists():
        if destination.read_text()!=encoded:raise ValueError('Preserve original immutable phase admission')
    else:destination.write_text(encoded)
    current=states()[mode]
    if current['complete']is None and 'ActiveState=inactive'in current['systemd']:
        existing=subprocess.check_output(['systemctl','--user','show',unit,'-p','LoadState','--value'],text=True).strip()
        if existing!='not-found':raise ValueError('An existing stopped/failed phase requires inspection, not blind redispatch')
        command=['systemd-run','--user','--unit='+unit,'--property=MemoryMax=4G',
            '--property=StandardOutput=append:'+str(root/'logs'/(mode+'.log')),
            '--property=StandardError=append:'+str(root/'logs'/(mode+'.log')),
            '--setenv=SSH_AUTH_SOCK=/home/chenkeyi/.local/share/harbor-rsi/near-r3-20261015/auth.sock',
            '--setenv=OPENAI_API_KEY=node18-local',PY,str(root/'scripts'/script)]+args
        subprocess.run(command,check=True,capture_output=True,text=True)
    print(json.dumps(dict(mode=mode,at=time.time(),state=states()[mode],
        scheduling='Native Harbor Job/TrialQueue only; node18 holds original cross-node phase lock')))


if __name__=='__main__':main()
