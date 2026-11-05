"""Opt-in CPU-only systemd/torchrun canaries, isolated from training and old queues."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import time
import uuid

from sft.runtime.checkpoint_archive import atomic_json
from sft.runtime.jobs import submit,status,process_matches
from sft.runtime.paths import workspace,runtime_config


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--workspace',required=True);args=parser.parse_args()
    os.environ['OPENHARNESS_SFT_WORKSPACE']=args.workspace
    root=workspace();config=runtime_config();stamp=uuid.uuid4().hex[:8];results={}
    job=submit('m1-64k',[],job_id='disconnect-'+stamp,probe_seconds=15)
    # This controller is itself a detached remote user service. Its submitting
    # SSH has already ended; no heartbeat is sent back to the workstation.
    try:submit('m1-64k',[],job_id=job['job_id'],probe_seconds=15)
    except FileExistsError:results['duplicate_job_rejected']=True
    deadline=time.monotonic()+45
    while time.monotonic()<deadline:
        live=status(job['job_id'])
        if live['status']=='completed':break
        time.sleep(1)
    assert live['status']=='completed'and live['returncode']==0
    # The final manifest is written just before the worker returns. Observe
    # actual exit too; a terminal JSON record alone is not cleanup evidence.
    for _ in range(30):
        if not process_matches(live['process']):break
        time.sleep(.2)
    assert not process_matches(live['process']), 'Completed CPU worker did not exit'
    results['disconnect_probe']=dict(unit=job['unit'],job_id=job['job_id'],seconds=15,completed=True,
                                    running_identity_after_completion=process_matches(live['process']))
    for name,signal in [('term','SIGTERM'),('kill','SIGKILL')]:
        job=submit('m1-64k',[],job_id=name+'-'+stamp,probe_seconds=60)
        for _ in range(30):
            live=status(job['job_id'])
            if live.get('process_identity_matches'):break
            time.sleep(.2)
        assert live.get('process_identity_matches')
        identity=live['process']
        if signal=='SIGTERM':subprocess.run(['systemctl','--user','stop',job['unit']],check=True,timeout=30)
        else:subprocess.run(['systemctl','--user','kill','--kill-who=main','--signal='+signal,job['unit']],check=True,timeout=15)
        for _ in range(30):
            if not process_matches(identity):break
            time.sleep(.2)
        assert not process_matches(identity)
        results[name]=dict(unit=job['unit'],signal=signal,process_gone=True,automatic_restart=False)
    # Real torchrun CPU/Gloo rank failure; never initialize CUDA or touch a GPU.
    directory=root/'jobs'/('elastic-'+stamp);directory.mkdir();unit=config['service_prefix']+'-elastic-'+stamp
    fixture=Path(__file__).parent/'canaries/rank_exit.py'
    args=['systemd-run','--user','--unit='+unit,'--property=Type=exec','--property=KillMode=control-group','--property=Restart=no',
        '--property=OOMPolicy=stop','--property=MemoryMax=4G','--property=CPUQuota=100%','--property=RuntimeMaxSec=90',
        '--property=TimeoutStopSec=20','--setenv=CUDA_VISIBLE_DEVICES=','--setenv=OMP_NUM_THREADS=1',
        '--setenv=OPENBLAS_NUM_THREADS=1','--property=StandardOutput=append:'+str(directory/'elastic.log'),
        '--property=StandardError=append:'+str(directory/'elastic.log'),config['python'],'-m','torch.distributed.run',
        '--standalone','--nproc-per-node=2','--max-restarts=0','--monitor-interval=0.2',str(fixture),str(directory)]
    subprocess.run(args,check=True,timeout=20,capture_output=True,text=True)
    for _ in range(100):
        state=subprocess.run(['systemctl','--user','show',unit,'-p','ActiveState','-p','Result','-p','ExecMainStatus'],text=True,capture_output=True,timeout=10).stdout
        if 'ActiveState=failed'in state:break
        time.sleep(.5)
    else:raise RuntimeError('Bounded CPU elastic canary did not finish; inspect its own RuntimeMaxSec unit')
    ranks=[json.loads((directory/f'rank-{rank}.json').read_text())for rank in range(2)]
    for rank in ranks:
        identity={k:rank[k]for k in ('pid','startticks','boot_id')}
        assert not process_matches(identity)and not rank['CUDA_initialized']
    results['native_elastic_rank_failure']=dict(unit=unit,ranks=2,remaining_ranks_gone=True,state=state,CUDA_initialized=False)
    atomic_json(root/'checks/remote-runtime-canaries.json',results)
    print(json.dumps(results,indent=2),flush=True)


if __name__=='__main__':main()
