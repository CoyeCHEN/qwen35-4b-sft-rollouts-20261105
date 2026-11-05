"""Same Ceph owner: user admission pause, actual30 native NOP environments, no LLM."""
import fcntl,hashlib,json,os,socket,subprocess,time
from pathlib import Path
R=Path('/ssd/chenkeyi/qwen35-sft-772-20261101');C=Path('/data/chenkeyi/qwen35-sft-772-20261101/control');BASE=R/'environment-preflight30';PY=R/'env/harbor-native-eval-r1/bin/python'
def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,v):
 t=p.with_name(p.name+'.tmp');t.write_text(json.dumps(v,indent=2)+'\n');t.replace(p)
def props(u):return dict(x.split('=',1)for x in subprocess.check_output(['systemctl','--user','show',u,'-p','MainPID','-p','LoadState','-p','ActiveState','-p','Result'],text=True).splitlines())
def main():
 with(C/'unique-native-advance.lock').open('a')as lock:
  fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
  assert(C/'USER_ENV_PREFLIGHT30_PAUSE_R1.json').exists()
  release=read(BASE/'EXECUTION_RELEASE_R1.json')
  for n,s in release['source_sha256'].items():assert sha(R/n)==s,n
  owner=dict(kind='UNIQUE_NATIVE_ADVANCE_NODE18',host=socket.gethostname(),pid=os.getpid(),start_ticks=Path('/proc/self/stat').read_text().rsplit(')',1)[1].split()[19],boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip(),controller_unit='qwen35-772-native-advance-node18-20261102-r24-env30.service',deployment_revision='r24-user-requested-real-env30-before-new-evaluation',started_at=time.time(),entry='native_harbor_environment_preflight',collection_closed=True)
  write(C/'NATIVE_ADVANCE_OWNER.json',owner)
  unit='qwen35-env-preflight30-native-nop-20261102-r1.service'
  while True:
   state=dict(at=time.time(),owner=owner,status='USER_PAUSED_NEW_EVALUATION_ENV30_PREFLIGHT',no_new_model_evaluation_admission=True,model_generation_calls_in_preflight=0)
   try:
    p=props(unit)
    if p['LoadState']=='not-found':
     assert not(BASE/'jobs/qwen35-env-preflight30-native-nop-20261102-r1').exists()
     write(BASE/'ADMISSION_R1.json',dict(at=time.time(),unique_controller_owner=owner,source_sha256=sha(R/'run-env-preflight30-native18-r1.py')))
     cmd=['systemd-run','--user','--unit='+unit,'--property=MemoryMax=16G','--property=StandardOutput=append:'+str(BASE/'native-job-r1.log'),'--property=StandardError=append:'+str(BASE/'native-job-r1.log'),'--setenv=PYTHONPATH='+str(R)+':'+str(R/'formal-native-eval-r1/scripts'),str(PY),str(R/'run-env-preflight30-native18-r1.py')]
     subprocess.run(cmd,check=True,capture_output=True,text=True);p=props(unit)
    state['preflight_native_job']=p
    observed=subprocess.run([str(PY),str(R/'audit-env-preflight30-native18-r1.py')],capture_output=True,text=True,timeout=90)
    if observed.returncode:state['audit_error']=observed.stderr[-2000:]
    manifest=read(BASE/'ENV_PREFLIGHT_30_MANIFEST.json')if(BASE/'ENV_PREFLIGHT_30_MANIFEST.json').exists()else None
    if manifest:state['environment_progress']={k:manifest[k]for k in ['expected_unique_tasks','passed','failed','running','frozen']}
    if manifest and manifest['passed']==30:
     # Final binding and future untouched-task continuation remain explicit gates.
     state['status']='ENV30_ALL_REAL_CHECKS_PASS_FINAL_FREEZE_AND_RESUME_REQUIRED'
    if p['ActiveState']=='failed':state['preflight_job_failed_requires_repair']=True
   except Exception as error:state['blocker']=repr(error)
   write(C/'NATIVE_ADVANCE_STATUS.json',state);print(json.dumps(state),flush=True);time.sleep(20)
if __name__=='__main__':main()
