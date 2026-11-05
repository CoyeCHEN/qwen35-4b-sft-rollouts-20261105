"""Restricted SSH deployment entry for three fixed native Harbor Jobs; no Trial scheduling."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

R=Path('/home/chenkeyi/.local/share/harbor-rsi/qwen35-new772-tb21-20261101')
PY='/home/chenkeyi/.local/share/harbor-rsi/qwen35-m1-m2-tb21-20261026/venv/bin/python'
MODES={
 'formal-n3':('qwen35-new772-formal801-20261101','run-formal-native-tb21149-r3.py',[],
     'THREE_MODEL_COLD_SERVING_ADMISSION.json','FORMAL_801_ALL_TERMINAL.json'),
 'new-m1-epoch3':('qwen35-new772-new-m1-epoch3-20261101','run-epoch3-native-tb21149-r1.py',['new-m1'],
     'EPOCH3_SERVING_ADMISSION_new-m1.json','EPOCH3_DIAGNOSTIC_ALL_TERMINAL_new-m1.json'),
 'new-m2-epoch3':('qwen35-new772-new-m2-epoch3-20261101','run-epoch3-native-tb21149-r1.py',['new-m2'],
     'EPOCH3_SERVING_ADMISSION_new-m2.json','EPOCH3_DIAGNOSTIC_ALL_TERMINAL_new-m2.json')}


def states():
    answer={}
    for mode,(unit,script,args,admission,complete)in MODES.items():
        p=R/'checks'/complete
        progress=R/'checks'/('FORMAL_801_STATUS.json'if mode=='formal-n3'else
            'EPOCH3_DIAGNOSTIC_STATUS_'+mode.replace('-epoch3','')+'.json')
        answer[mode]=dict(unit=unit,complete=json.loads(p.read_text())if p.exists()else None,
            progress=json.loads(progress.read_text())if progress.exists()else None,
            systemd=subprocess.check_output(['systemctl','--user','show',unit,'-p','MainPID','-p','ActiveState','-p','Result'],text=True))
    return answer


def main():
    mode=os.environ.get('SSH_ORIGINAL_COMMAND','')
    if mode=='status':print(json.dumps(dict(at=time.time(),modes=states())));return
    if mode not in MODES:raise ValueError('Only fixed native campaign actions are authorized')
    raw=sys.stdin.buffer.read(5*1024*1024+1)
    if len(raw)>5*1024*1024:raise ValueError('Oversized deployment admission')
    value=json.loads(raw)
    owner=value['unique_controller_owner']
    assert owner['kind']=='UNIQUE_NATIVE_ADVANCE_NODE18' and owner['host']=='bm-220acn7'
    assert owner['pid']>0 and owner['collection_closed'] and owner['old_four_deferred_until_801_terminal']
    unit,script,args,admission,complete=MODES[mode]
    assert value['native_runner_sha256']==hashlib.sha256((R/'scripts'/script).read_bytes()).hexdigest()
    if mode=='formal-n3':
        assert value['new_m1_epoch5_verified']and value['new_m2_epoch5_verified']
    else:assert value['epoch']==3 and value['model_is_final_epoch5']is False
    destination=R/'manifests'/admission
    encoded=json.dumps(value,ensure_ascii=False,indent=2)+'\n'
    if destination.exists():
        assert destination.read_text()==encoded,'Preserve the original immutable phase admission'
    else:destination.write_text(encoded)
    current=states()[mode]
    # A repeated acknowledgement cannot cause a second Job or a new Trial.
    if current['complete']is None and 'ActiveState=inactive' in current['systemd']:
        existing=subprocess.check_output(['systemctl','--user','show',unit,'-p','LoadState','--value'],text=True).strip()
        assert existing=='not-found','An existing failed/stopped phase requires inspection, not blind redispatch'
        cmd=['systemd-run','--user','--unit='+unit,'--property=MemoryMax=4G',
            '--property=StandardOutput=append:'+str(R/'logs'/(mode+'.log')),
            '--property=StandardError=append:'+str(R/'logs'/(mode+'.log')),
            '--setenv=SSH_AUTH_SOCK=/home/chenkeyi/.local/share/harbor-rsi/near-r3-20261015/auth.sock',
            '--setenv=OPENAI_API_KEY=node18-local',PY,str(R/'scripts'/script)]+args
        subprocess.run(cmd,check=True,capture_output=True,text=True)
    print(json.dumps(dict(mode=mode,at=time.time(),state=states()[mode],
        scheduling='Existing native Harbor Job/TrialQueue only; sole cross-node advancement authority remains node18 Ceph lock owner')))


if __name__=='__main__':main()
