"""Single existing Ceph lock; native environment jobs and priority synthetic32."""
import fcntl,hashlib,importlib,json,os,socket,subprocess,sys,time
from pathlib import Path
R=Path('/ssd/chenkeyi/qwen35-sft-772-20261101'); C=Path('/data/chenkeyi/qwen35-sft-772-20261101/control'); B=R/'environment-preflight30'; S=R/'synthetic32'; PY=R/'env/harbor-native-eval-r1/bin/python'; E=R/'formal-native-eval-r1'
sys.path[:0]=[str(R),str(E/'scripts')]
from environment_evidence_audit_r5 import read,write,sha,audit
def props(u): return dict(x.split('=',1) for x in subprocess.check_output(['systemctl','--user','show',u,'-p','MainPID','-p','LoadState','-p','ActiveState','-p','Result'],text=True,timeout=5).splitlines())
def launch(unit,source,args,admission,owner,extra=None):
    status=props(unit)
    if status['LoadState']=='not-found':
        write(admission,dict(at=time.time(),unique_controller_owner=owner,source_sha256=sha(R/source),**(extra or {})))
        log=R/'logs'/(unit+'.log'); command=['systemd-run','--user','--unit='+unit,'--property=MemoryMax=16G','--property=StandardOutput=append:'+str(log),'--property=StandardError=append:'+str(log),'--setenv=PYTHONPATH='+str(R)+':'+str(E/'scripts'),str(PY),str(R/source)]+args
        subprocess.run(command,check=True,capture_output=True,text=True,timeout=8); status=props(unit)
    return status
def freeze(path):
    value=read(path); assert value['passed']==value['expected_unique_tasks'] and all(t['status']=='PASS' for t in value['tasks'])
    if not value.get('frozen'):
        value.update(frozen=True,frozen_at=time.time(),unique_controller_owner=read(C/'NATIVE_ADVANCE_OWNER.json')); write(path,value)
    return value
def main():
    with(C/'unique-native-advance.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        release=read(B/'EXECUTION_RELEASE_R6.json')
        for name,digest in release['source_sha256'].items(): assert sha(R/name)==digest,name
        owner=dict(kind='UNIQUE_NATIVE_ADVANCE_NODE18',host=socket.gethostname(),pid=os.getpid(),start_ticks=Path('/proc/self/stat').read_text().rsplit(')',1)[1].split()[19],boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip(),controller_unit='qwen35-772-native-advance-node18-20261102-r29-env-repair.service',deployment_revision='r29-explicit32-image-identity-and-native-resume',started_at=time.time(),entry='native_harbor',collection_closed=True)
        write(C/'NATIVE_ADVANCE_OWNER.json',owner)
        while True:
            start=time.monotonic(); state=dict(at=time.time(),owner=owner,status='ENVIRONMENT_REPAIR_AND_PRIORITY_SYNTHETIC32',new_common30_model_admission=False,runtime_injection_prohibited=True,old801_disabled=True)
            try:
                frozen=read(S/'FROZEN_USER_SYNTHETIC32_SOURCE_R2.json'); assert frozen['unique_variants']==32 and frozen['unique_seed_families']==14
                state['highest_priority_synthetic32']=dict(status='SOURCE_VERIFIED_NATIVE_PREPARATION',source_node='167',tasks=32,seed_families=14,manifest_sha256=sha(S/'FROZEN_USER_SYNTHETIC32_SOURCE_R2.json'),model='NEW-M1 Epoch3',not_official_tb21=True)
                state['synthetic32_prep']=launch('qwen35-user-synthetic32-prep-m1e3-n1-20261102-r1.service','run-user-synthetic32-native18-r1.py',['prep'],S/'prep-ADMISSION_R1.json',owner)
                deployment=read(S/'SYNTHETIC32_DEPLOYMENT_R3.json')
                state['synthetic32_explicit_recipe_rechecks']=launch('qwen35-user-synthetic32-original-recipe-recheck-20261102-r3.service','run-synthetic32-recipe-recheck18-r3.py',[],S/'RECHECK_ADMISSION_R3.json',owner,dict(tasks=deployment['explicit_original_recipe_rebuild_tasks'],reason='Original Dockerfile exact public inputs; independent private image; source167 image bit identity not claimed'))
                sm=audit('32')
                if sm['failed'] and not(S/'RECHECK_ADMISSION_R2.json').exists():
                    state['synthetic32_recheck']=launch('qwen35-user-synthetic32-env-recheck-20261102-r2.service','run-synthetic32-env-recheck18-r2.py',[],S/'RECHECK_ADMISSION_R2.json',owner,dict(tasks=[r['task_id']for r in sm['tasks']if r['status']=='FAIL'],reason='Project SSH transport repair; independent NOP identity; no model calls'))
                state['synthetic32_environment']={k:sm[k] for k in ['passed','failed','unknown','running','pending','frozen']}
                if sm['passed']==32:
                    freeze(S/'ENV_PREFLIGHT_32_MANIFEST.json')
                    state['synthetic32_eval']=launch('qwen35-user-synthetic32-eval-m1e3-n1-20261102-r3.service','run-user-synthetic32-native18-r3.py',['eval'],S/'eval-ADMISSION_R3.json',owner)
                for stage in ['prep','eval']:
                    p=S/(stage+('-NATIVE_PROGRESS_R3.json' if stage=='eval' else '-NATIVE_PROGRESS_R1.json'))
                    if p.exists():state['synthetic32_'+stage+'_progress']=read(p)
            except Exception as exc: state['synthetic32_blocker']=repr(exc)
            try:
                manifest=audit('30'); state['environment_progress']={k:manifest[k] for k in ['passed','failed','unknown','running','pending','frozen','audit_seconds','engine_query_count']}
                recheck=B/'RECHECK_ADMISSION_R2.json'
                if manifest['failed'] and not recheck.exists():
                    tasks=[r['task_id'] for r in manifest['tasks'] if r['status']=='FAIL']
                    state['environment_recheck']=launch('qwen35-env-preflight30-native-recheck-20261102-r2.service','run-env-preflight30-recheck18-r2.py',[],recheck,owner,dict(tasks=tasks,reason='Preserved initial setup/proxy/SSH/cleanup failures; native no-model recheck'))
                elif recheck.exists():state['environment_recheck']=props('qwen35-env-preflight30-native-recheck-20261102-r2.service')
                if manifest['failed'] and manifest['running']==0 and manifest['pending']==0 and props('qwen35-env-preflight30-native-recheck-20261102-r2.service')['ActiveState']!='active':
                    tasks=[r['task_id'] for r in manifest['tasks'] if r['status']=='FAIL']
                    state['environment_recheck3']=launch('qwen35-env-preflight30-native-recheck-20261102-r3.service','run-env-preflight30-recheck18-r3.py',[],B/'RECHECK_ADMISSION_R3.json',owner,dict(tasks=tasks,reason='Verified project SSH multiplex transport repair; retain all earlier failures'))
                if manifest['passed']==30:
                    freeze(B/'ENV_PREFLIGHT_30_MANIFEST.json'); p=B/'ENV_PREFLIGHT_30_MANIFEST.json'; write(C/'ENV_PREFLIGHT30_GATE_RELEASE_R1.json',dict(at=time.time(),manifest_path=str(p),manifest_sha256=sha(p),unique_controller_owner=owner))
                    state['new_common30_model_admission']=True
                    # A versioned native continuation module is admitted only after its
                    # explicit source release, avoiding any live Job mutation.
                    continuation=R/'resume-accepted-common30-r2.py'
                    if continuation.exists() and 'resume-accepted-common30-r2.py' in release['source_sha256']:
                        importlib.import_module('resume-accepted-common30-r2').advance(owner,state)
                    else:state['common30_resume_blocker']='Native continuation ledger/source acceptance pending; no model retry or live Job mutation'
            except Exception as exc: state['environment_blocker']=repr(exc)
            state['detached_trial_recovery']={p.parent.name:read(p) for p in (R/'detached-native-recovery-r1').glob('*/RECOVERY_EVIDENCE.json')}
            state['controller_cycle_seconds']=time.monotonic()-start; write(C/'NATIVE_ADVANCE_STATUS.json',state); print(json.dumps(state),flush=True); time.sleep(20)
if __name__=='__main__':main()
