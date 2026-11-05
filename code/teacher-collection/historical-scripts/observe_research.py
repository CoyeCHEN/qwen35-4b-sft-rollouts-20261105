"""Read-only observer attached to the existing 20-minute GPU Timer.

No scheduling, restart, signals, CUDA initialization, or model/API requests.
"""
import datetime
import json
from logging import getLogger, Formatter
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import subprocess

ROOT=Path('/home/chenkeyi/workspace/RSI/runtime-evidence/qwen35-new-cf500-tmax500-20261029')


def command(args):
    try:
        r=subprocess.run(args,capture_output=True,text=True,timeout=12)
        return dict(returncode=r.returncode,stdout=r.stdout,stderr=r.stderr[:1000])
    except (OSError,subprocess.TimeoutExpired)as e:return dict(status='UNKNOWN',error=type(e).__name__)


def artifact(name,keys):
    try:
        value=json.loads((ROOT/name).read_text())
        return {key:value.get(key)for key in keys}|{'source_file':name}
    except (OSError,ValueError)as e:return dict(status='UNKNOWN',error=type(e).__name__,source_file=name)


def main():
    now=datetime.datetime.now(datetime.timezone.utc)
    result=dict(checked_at=now.isoformat(),beijing_time=now.astimezone(datetime.timezone(datetime.timedelta(hours=8))).isoformat(),
        run_id=ROOT.name,observer_pid=os.getpid(),observation_only=True,
        gpu=command(['nvidia-smi','--query-gpu=index,uuid,memory.used,memory.total,utilization.gpu','--format=csv,noheader']),
        compute_processes=command(['nvidia-smi','--query-compute-apps=gpu_uuid,pid,process_name,used_memory','--format=csv,noheader']),
        authorized_gpu_indices=[0,1,2,3],authorized_gpu_uuids=[
            'GPU-bb31693b-95f6-4416-ec41-dd75511c2c59','GPU-0db8aea7-b003-06fb-d197-d047c1d67bcb',
            'GPU-d2499600-e80e-4fb8-40ef-b6f0f919d2d8','GPU-00f3c3df-16e0-f31f-4066-bdee4c8cdff2'],
        units=command(['systemctl','--user','show','qwen35-new-route-input-audit-20261029.service',
            'qwen35-new-route-input-audit-20261029-r1.service',
            'qwen35-new-route-input-audit-20261029-r2.service',
            'qwen35-serving-cold-hot-diagnostic-20261030.service',
            'qwen35-serving-paired-seeds-20261030.service',
            'qwen35-qwen-liger-loss-numeric-20261030.service',
            'qwen35-new-public-stage-unittest-20261030.service',
            'qwen35-new-route-full-target-nll-20261030.service',
            'qwen35-full-validation-nll-r2-20261030.service',
            'qwen35-new-route-loss-cpu-20261029-r1.service','openharness-sft-calibforge-ca057bd36f-advance.service',
            '-p','Id','-p','ActiveState','-p','MainPID','-p','Result','-p','ConditionResult']),
        input_audit=artifact('checks/frozen-input-collator-audit-r2.json', ['passed','counts','seconds','cuda_initialized']),
        numerical_loss=artifact('checks/causal-loss-cpu-r1.json',['passed','scope','cuda_initialized']),
        liger_gpu_loss=artifact('checks/qwen-liger-loss-gpu.json',['passed','scope','peak_allocated_bytes']),
        serving_diagnostic=artifact('checks/serving-cold-hot-comparison.json',['complete','inference','historical_token_exact_reproduction']),
        cf_tasks=artifact('checks/calibforge500-selection.json',['tasks','manifest_sha256','environment_ready','full_success_trajectory_count']))
    owners=[]
    for line in result['compute_processes'].get('stdout','').splitlines():
        fields=[x.strip()for x in line.split(',')]
        if len(fields)<2 or not fields[1].isdigit():continue
        try:
            status=(Path('/proc')/fields[1]/'status').read_text()
            uid=next(row.split()[1]for row in status.splitlines()if row.startswith('Uid:'))
            owners.append(dict(pid=int(fields[1]),uid=int(uid),gpu_uuid=fields[0]))
        except (OSError,StopIteration):owners.append(dict(pid=int(fields[1]),status='UNKNOWN_PROCESS_EXITED_OR_UNREADABLE'))
    result['gpu_process_owners']=owners
    path=ROOT/'logs/frozen-input-audit-r2.log'
    if not path.exists():path=ROOT/'logs/frozen-input-audit.log'
    if path.exists():
        with path.open('rb')as stream:
            stream.seek(max(0,path.stat().st_size-16384));lines=stream.read().decode(errors='replace').splitlines()
        progress=[]
        for line in lines:
            try:
                x=json.loads(line)
                if x.get('event')=='progress':progress.append(x)
            except ValueError:pass
        result['actual_latest_input_audit_progress']=progress[-1]if progress else None
    stat=os.statvfs('/ssd/chenkeyi')
    result['ssd_free_bytes']=stat.f_bavail*stat.f_frsize
    result['harbor149_observation']=artifact('checks/collection149-observation.json',
        ['checked_at','source_download','tmax_tasks','attempt_ledger','configured_dispatch_accounting','actual_native_teacher_jobs','environment_preparation','cf_image_preparation','tmax_image_preparation','native_request_accounting','units','observer_only'])
    try:
        stamp=result['harbor149_observation']['checked_at']
        age=(now-datetime.datetime.fromisoformat(stamp)).total_seconds()
        result['harbor149_observation']['cross_host_age_seconds']=age
        result['harbor149_observation']['remote_clock_ahead']=age<0
        result['harbor149_observation']['snapshot_age_seconds']=age if age>=0 else None
        received=(ROOT/'checks/collection149-observation.json').stat().st_mtime
        result['harbor149_observation']['local_receipt_age_seconds']=now.timestamp()-received
    except (KeyError,TypeError,ValueError):result['harbor149_observation']['snapshot_age_seconds']=None
    result['full_validation_nll']=artifact('checks/full-validation-serving-nll-r2.json',['complete','models','error_type','error'])
    logger=getLogger('new-research-observation');logger.setLevel('INFO')
    handler=RotatingFileHandler(ROOT/'logs/monitor.jsonl',maxBytes=8*1024**2,backupCount=4,encoding='utf-8')
    handler.setFormatter(Formatter('%(message)s'));logger.addHandler(handler)
    logger.info(json.dumps(result,ensure_ascii=False));handler.close();logger.removeHandler(handler)
    out=ROOT/'checks/monitor-latest.json';temporary=out.with_suffix('.tmp')
    temporary.write_text(json.dumps(result,ensure_ascii=False,indent=2));os.replace(temporary,out)
    print(json.dumps({'time':result['checked_at'],'observer':str(out),'no_dispatch_or_cleanup':True}))


if __name__=='__main__':main()
