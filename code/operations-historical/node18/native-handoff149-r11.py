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
 'formal-n3':(R,'qwen35-new772-formal801-20261101','run-formal-native-tb21149-r9.py',[],
     'THREE_MODEL_COLD_SERVING_ADMISSION.json','FORMAL_801_ALL_TERMINAL.json','FORMAL_801_STATUS.json'),
 'new-m1-epoch3':(R,'qwen35-new772-new-m1-epoch3-20261101','run-epoch3-native-tb21149-r1.py',['new-m1'],
     'EPOCH3_SERVING_ADMISSION_new-m1.json','EPOCH3_DIAGNOSTIC_ALL_TERMINAL_new-m1.json','EPOCH3_DIAGNOSTIC_STATUS_new-m1.json'),
 'new-m2-epoch3':(R,'qwen35-new772-new-m2-epoch3-20261101','run-epoch3-native-tb21149-r1.py',['new-m2'],
     'EPOCH3_SERVING_ADMISSION_new-m2.json','EPOCH3_DIAGNOSTIC_ALL_TERMINAL_new-m2.json','EPOCH3_DIAGNOSTIC_STATUS_new-m2.json')}
MODES['new11-install-preflight']=(R,'qwen35-new772-new11-install-preflight-20261102','run-new11-install-preflight149-r1.py',[],
    'NEW11_INSTALL_PREFLIGHT_ADMISSION_R1.json','NEW11_INSTALL_PREFLIGHT_ALL_TERMINAL_R1.json','NEW11_INSTALL_PREFLIGHT_STATUS_R1.json')
for stage in ['new-m1','new-m2']:
    MODES[stage+'-epoch3-fixed']=(R,'qwen35-new772-'+stage+'-epoch3-fixed-20261102','run-fixed-epoch3-native-tb21149-r1.py',[stage],
        'EPOCH3_FIXED_SERVING_ADMISSION_'+stage+'.json','EPOCH3_FIXED_DIAGNOSTIC_ALL_TERMINAL_'+stage+'.json','EPOCH3_FIXED_DIAGNOSTIC_STATUS_'+stage+'.json')
MODES['new-m1-epoch3-unstarted']=(R,'qwen35-new772-new-m1-e3-original-five-20261102-r1','run-e3-original-unstarted149-r1.py',[],
    'EPOCH3_ORIGINAL_UNSTARTED_SERVING_ADMISSION_R1.json','E3_ORIGINAL_UNSTARTED_ALL_TERMINAL_R1.json','E3_ORIGINAL_UNSTARTED_STATUS_R1.json')
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
    recovery=R/'recovery/e3-controller-oom-20261102-r1'
    item=answer['new-m1-epoch3-unstarted']
    item['original_oom_snapshot_sha256']=hashlib.sha256((R/'checks/E3_NATIVE_CONTROLLER_OOM_SNAPSHOT_R1.json').read_bytes()).hexdigest()
    item['original_orphans']={}
    for task,file in [('regex-log','RAW_RECORDER_VALIDATION.json'),('chess-best-move','ORIGINAL_ORPHAN_AGENT_CLOSED_AND_ARCHIVED.json')]:
        path=recovery/task/file
        item['original_orphans'][task]=dict(terminal_evidence_exists=path.exists(),evidence_sha256=hashlib.sha256(path.read_bytes()).hexdigest()if path.exists()else None,primary_classification='UNKNOWN_CONTROLLER_OOM_INTERRUPTED')
    watch=recovery/'chess-best-move/ORPHAN_DEADLINE_STATUS.json'
    item['chess_orphan_watch']=json.loads(watch.read_text())if watch.exists()else None
    return answer


def validate_formal_protocol(value):
    protocol=value['native_extended_protocol_admissions']
    if set(protocol)!={'m0','new-m1-e5','new-m2-e5'}:raise ValueError('All3 actual extended native CLI admissions are required')
    if {p['model_id']for p in protocol.values()}!=set(value['models']):raise ValueError('Distinct actual cold models are required')
    for tag,proof in protocol.items():
        if proof['model_id']!='qwen35-new772-'+tag:raise ValueError('Protocol proof tag differs from frozen model alias')
        if proof['wheel_sha256']!='1d27eef1ca6696275f306d8c653f7a266a4c7aea7321f0d47fd01b739c27fa18':raise ValueError('Formal protocol wheel differs')
        if len(proof['proof_sha256'])!=64 or len(bytes.fromhex(proof['proof_sha256']))!=32:raise ValueError('Invalid actual protocol proof SHA')
        if value['models'][proof['model_id']]['weight_version']!=proof['weight_version']:raise ValueError('Actual protocol model differs from cold serving admission')


def main():
    mode=os.environ.get('SSH_ORIGINAL_COMMAND','')
    if mode=='status':print(json.dumps(dict(at=time.time(),modes=states())));return
    if mode=='formal-n3':raise ValueError('Formal801 write authority moved to the sole node18 controller; this149 entry is disabled')
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
    if mode=='new11-install-preflight':
        if value['actual_model_attempts_expected']!=0:raise ValueError('Install-only preflight must not sample the model')
    elif mode=='formal-n3':
        if not(value['new_m1_epoch5_verified']and value['new_m2_epoch5_verified']):raise ValueError('Both final models must be admitted')
        e2e=json.loads((R/'checks/CONTEXT_RECOVERY_FULL_WHEEL_E2E_ACCEPTANCE_R1.json').read_text())
        setup=json.loads((R/'checks/NEW11_INSTALL_PREFLIGHT_ALL_TERMINAL_R1.json').read_text())
        if not(e2e['passed']and len(e2e['cases'])==6 and setup['passed']and setup['ready']==89):raise ValueError('Formal readiness gates incomplete')
        validate_formal_protocol(value)
    elif mode=='new-m1-epoch3-unstarted':
        snapshot=json.loads((R/'checks/E3_NATIVE_CONTROLLER_OOM_SNAPSHOT_R1.json').read_text())
        if not(value['epoch']==3 and value['model_is_final_epoch5']is False):raise ValueError('Expected the existing E3 model')
        if value['original_unstarted_tasks']!=snapshot['unstarted_tasks_in_original_preregistered_order']:raise ValueError('Only original never-started tasks may continue')
        if value['original_oom_snapshot_sha256']!=hashlib.sha256((R/'checks/E3_NATIVE_CONTROLLER_OOM_SNAPSHOT_R1.json').read_bytes()).hexdigest():raise ValueError('OOM evidence changed')
    elif mode.startswith('old-'):
        gate=json.loads((R/'checks/FORMAL_801_ALL_TERMINAL.json').read_text())
        if not(gate['completed']and gate['actual_terminal']==801 and value['new_formal801_completed']
            and gate['response_qualification_completed']
            and hashlib.sha256((R/'checks/TB21_N3_FULL_COMPARISON_R7.json').read_bytes()).hexdigest()==gate['full_comparison_sha256']):
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
        command=['systemd-run','--user','--unit='+unit,'--property=MemoryMax=16G',
            '--property=StandardOutput=append:'+str(root/'logs'/(mode+'.log')),
            '--property=StandardError=append:'+str(root/'logs'/(mode+'.log')),
            '--setenv=SSH_AUTH_SOCK=/home/chenkeyi/.local/share/harbor-rsi/near-r3-20261015/auth.sock',
            '--setenv=OPENAI_API_KEY=node18-local',PY,str(root/'scripts'/script)]+args
        subprocess.run(command,check=True,capture_output=True,text=True)
    print(json.dumps(dict(mode=mode,at=time.time(),state=states()[mode],
        scheduling='Native Harbor Job/TrialQueue only; node18 holds original cross-node phase lock')))


if __name__=='__main__':main()
