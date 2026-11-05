"""Bounded native evidence observation; this command never dispatches work."""
import json
from pathlib import Path
import subprocess
import time
import os

R=Path('/ssd/chenkeyi/qwen35-sft-772-20261101')
C=Path('/data/chenkeyi/qwen35-sft-772-20261101/control')
W=R/'new-sft/workspace'


def command(args):
    result=subprocess.run(args,capture_output=True,text=True,timeout=15)
    return dict(returncode=result.returncode,stdout=result.stdout,stderr=result.stderr[-500:])


def load(path):
    return json.loads(path.read_text()) if path.exists() else None


def events(path):
    if not path.exists():return []
    with path.open('rb') as stream:
        size=path.stat().st_size
        start=max(0,size-512*1024)
        header=stream.read(min(128*1024,start)) if start else b''
        stream.seek(start)
        tail=stream.read().splitlines()
        if start:tail=tail[1:]
        # Keep the original real train_begin when a long native log outgrows the tail.
        lines=(header.splitlines()[:-1] if header else [])+tail
    rows=[]
    for line in lines:
        try:rows.append(json.loads(line))
        except json.JSONDecodeError:continue
    return rows


def observed_run(folder):
    rows=events(folder/'preflight-evidence-rank0.jsonl')
    begins=[x for x in rows if x.get('event')=='train_begin']
    updates=[x for x in rows if x.get('event')=='optimizer_step']
    metrics=[x for x in rows if x.get('event')=='metrics']
    last=updates[-1]if updates else {}
    return dict(real_cuda_train_begin=bool(begins or updates),
        actual_optimizer_step=last.get('global_step'),last_update_time=last.get('time'),
        last_update_age_seconds=time.time()-last['time']if last else None,
        finite_gradients=all(v['finite'] for v in last.get('gradients',{}).values())if last else None,
        parameter_update_observed=last.get('parameter_update_observed'),
        max_memory_allocated=last.get('peak_allocated_bytes'),max_memory_reserved=last.get('peak_reserved_bytes'),
        latest_metrics=metrics[-1].get('metrics')if metrics else None,
        actual_parallelism=begins[-1].get('parallelism')if begins else None,
        native_checkpoint_names=sorted(p.name for p in folder.glob('checkpoint-*')if(p/'CHECKPOINT_COMPLETE.json').exists()),
        trainer_state=load(folder/'trainer_state.json'),
        hf_export=load(folder/'HF_EXPORT_COMPLETE.json'))


def main():
    start=time.monotonic()
    state=dict(kind='READ_ONLY_NODE18_TRAINING_OBSERVATION_V6',checked_at=time.time(),
        automatic_dispatch=False,execution_node='18',collection_closed=True,
        data_release=load(R/'frozen-data-772-r3/DATA_RELEASE.json'),
        stage_order=['NEW-M1','NEW-M2','TB21 n3 801 trials','old four deferred'],
        native_advance=load(C/'NATIVE_ADVANCE_STATUS.json'),gpu_allocation=load(C/'FORMAL_GPU_ALLOCATION.json'))
    state['units']=command(['systemctl','--user','show',
        'qwen35-772-native-advance-node18-20261101-r2.service',
        'qwen35-capacity772-128k-dp4-20261101-r6.service',
        'qwen35-772-new-sft-new772-new-cf416-m1.service',
        'qwen35-772-new-sft-new772-new-cf416-tmax356-m2.service',
        '-p','Id','-p','ActiveState','-p','SubState','-p','MainPID','-p','Result'])
    state['gpu']=command(['nvidia-smi','--query-gpu=index,uuid,memory.total,memory.used,utilization.gpu','--format=csv,noheader,nounits'])
    state['gpu_processes']=command(['nvidia-smi','--query-compute-apps=gpu_uuid,pid,process_name,used_memory','--format=csv,noheader,nounits'])
    state['capacity']={p.name:observed_run(p)for p in (R/'runs').glob('verify-capacity772-*')}
    state['formal_runs']={name:observed_run(R/'runs'/name)for name in ['new-m1-cf416-128k-e5','new-m2-tmax356-128k-e5']}
    state['formal_native_jobs']={p.parent.name:load(p)for p in (W/'jobs').glob('new772-*/job.json')}
    state['formal_new_m1_m2_started']=any(x['real_cuda_train_begin']for x in state['formal_runs'].values())
    state['current_stage']='NEW_M1_M2_NATIVE_TRAINING'if state['formal_new_m1_m2_started']else'REAL_CAPACITY_ACCEPTANCE'
    state['old_four_deferred']=load(C/'OLD_FOUR_SAFE_DEFERRAL.json')
    state['observation_seconds']=time.monotonic()-start
    path=C/'CURRENT_EXECUTION_STATUS.json';temp=path.with_name(path.name+'.tmp-'+str(os.getpid()))
    temp.write_text(json.dumps(state));temp.replace(path)
    print(json.dumps(state))


if __name__=='__main__':main()
