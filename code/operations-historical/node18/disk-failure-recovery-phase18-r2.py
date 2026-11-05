"""Admit two fixed, proven zero-model continuations after real storage repair."""
import hashlib
import importlib
import json
import os
from pathlib import Path
import shlex
import subprocess
import time

R=Path('/ssd/chenkeyi/qwen35-sft-772-20261101')
C=Path('/data/chenkeyi/qwen35-sft-772-20261101/control')
E=R/'formal-native-eval-r1'
from environment_evidence_audit_r3 import read,write,sha

SCOPES={
    'new-m1-e3-diag':('r3','R3','a1400c81324a6a2018c517c925c3bd7f201c9d7e57380a52718d88472e461b8a'),
    'new-m2-e1-diag':('r2','R2','a29c6e0d1cd0911ee18e97006e7b3f29b08f1c40144d39ff52134345e4104e3b'),
    'new-m1-e5-diag':('r3','R3','4c2cffd705bc2e4d3bfd8bcf96ad6403faf50bf8bf2f44918271d06fa3fb3806'),
}
REMOTE_R2='/home/chenkeyi/.local/share/harbor-rsi/qwen35-new772-tb21-20261101/scripts/materialize-public-verifier-cache149-r2.py'

def ssh(args,timeout=20,input=None):
    env=dict(os.environ)
    env['PATH']=str(R/'formal-controller18-client-bin-r1')+':'+env['PATH']
    return subprocess.run(['ssh','-p','18449','chenkeyi@127.0.0.1',shlex.join(args)],input=input,
                          capture_output=True,text=True,timeout=timeout,env=env)

def advance(owner,state,launch):
    assert read(C/'NATIVE_ADVANCE_OWNER.json')==owner
    worker=importlib.import_module('run-accepted-common30-disk-recovery18-r3')
    rows=[]
    # This is a read-only capacity observation until the real minimum is met.
    program="import os,json;v=os.statvfs('/');print(json.dumps(dict(available_bytes=v.f_bavail*v.f_frsize,free_bytes=v.f_bfree*v.f_frsize,available_inodes=v.f_favail)))"
    process=ssh(['python3','-c',program],timeout=10)
    assert process.returncode==0,process.stderr[-1000:]
    capacity=json.loads(process.stdout)
    state['engine149_storage']=dict(at=time.time(),**capacity)
    for tag,(directory_revision,suffix,expected_sha) in SCOPES.items():
        out=R/('disk-failure-recovery-'+directory_revision)/tag
        plan_path=out/('PLAN_'+suffix+'.json');assert sha(plan_path)==expected_sha
        plan=read(plan_path);admission=out/('ADMISSION_'+suffix+'.json')
        unit=plan['recovery_job_name']+'.service'
        if admission.exists():
            rows.append(dict(tag=tag,status='REGISTERED_NEVER_REDISPATCH_FROM_UNIT_GC',
                admission_sha256=sha(admission),unit=unit,
                progress=read(out/('PROGRESS_'+suffix+'.json')) if (out/('PROGRESS_'+suffix+'.json')).exists() else None))
            continue
        assert directory_revision=='r3','Preserve the admitted healthy R2 Job; never reconstruct missing admission'
        if capacity['available_bytes']<64*1024**3 or capacity['available_inodes']<=0:
            rows.append(dict(tag=tag,status='WAITING_REAL_STORAGE_REPAIR',
                fixed_zero_model_tasks=len(plan['trials']),minimum_available_bytes=64*1024**3,
                available_bytes=capacity['available_bytes'],no_model_or_environment_dispatched=True))
            continue
        # The same actual fsync/readback probe is repeated inside each new worker.
        staging='/home/chenkeyi/.local/share/harbor-rsi/qwen35-new772-tb21-20261101/staging'
        request=dict(staging_root=staging,docker_root_dir='/var/lib/docker')
        probe=ssh(['python3','-c',worker.DISK_PROBE,json.dumps(request)],timeout=20)
        proof=json.loads(probe.stdout)
        assert probe.returncode==0 and proof['passed'],dict(stderr=probe.stderr[-1000:],proof=proof)
        proof_path=out/('STORAGE_REPAIR_FSYNC_'+str(time.time_ns())+'.json')
        write(proof_path,dict(at=time.time(),actual_probe=proof,
            probe_source_sha256=hashlib.sha256(worker.DISK_PROBE.encode()).hexdigest()))
        # New helper only; the frozen R1 used by healthy Trials is untouched.
        source=R/'materialize-public-verifier-cache149-r2.py';digest=sha(source)
        install="import hashlib,pathlib,sys; p=pathlib.Path(sys.argv[1]); b=sys.stdin.buffer.read(); assert hashlib.sha256(b).hexdigest()==sys.argv[2]; old=p.read_bytes() if p.exists() else None; assert old is None or old==b; p.write_bytes(b) if old is None else None; print(hashlib.sha256(p.read_bytes()).hexdigest())"
        installed=ssh(['python3','-c',install,REMOTE_R2,digest],input=source.read_text(),timeout=15)
        assert installed.returncode==0 and installed.stdout.strip()==digest,installed.stderr[-1000:]
        gate=R/'formal-controller18-docker-admission-r5/bin/docker'
        policy=C/'ENV_PREFLIGHT30_DOCKER_ADMISSION_POLICY_R5.json'
        extra=dict(plan_path=str(plan_path),plan_sha256=expected_sha,
            disk_repair_verified=True,disk_repair_proof_path=str(proof_path),disk_repair_proof_sha256=sha(proof_path),
            output_directory=str(out),docker_admission_bin=str(gate.parent),docker_wrapper_sha256=sha(gate),
            docker_admission_policy_path=str(policy),docker_admission_policy_sha256=sha(policy),
            fixed_zero_model_tasks=len(plan['trials']),recovery_does_not_replace_first_pass=True)
        result=launch(unit,'run-accepted-common30-disk-recovery18-r3.py',[str(admission)],admission,owner,extra)
        rows.append(dict(tag=tag,status='NATIVE_ZERO_MODEL_CONTINUATION_ADMITTED',unit=unit,registered=result))
    state['bounded_disk_failure_continuations']=rows
    if any(x['status']=='WAITING_REAL_STORAGE_REPAIR' for x in rows):
        state['status']='HEALTHY_EVALUATIONS_CONTINUE_STORAGE_BLOCKS_NEW_ENVIRONMENTS'

if __name__=='__main__':raise SystemExit('Only the existing unique controller may call advance')
