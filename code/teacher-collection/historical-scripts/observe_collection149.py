"""Once-per-existing-timer observation and existing SSH transport, no dispatch."""
import datetime
import hashlib
import json
import os
from pathlib import Path
import subprocess
import re

ROOT=Path('/home/chenkeyi/.local/share/harbor-rsi/qwen35-new-cf500-tmax500-20261029')


def collection_hook_result():
    reply=subprocess.run(['systemctl','--user','show','qwen35-tb21-monitor.service',
        '-p','ExecStartPost','--value'],capture_output=True,text=True,check=True,timeout=5)
    own=str(ROOT/'scripts/observe_collection.py')
    matches=[line for line in reply.stdout.splitlines() if own in line]
    if len(matches)!=1:raise ValueError('Collection monitor hook identity is ambiguous')
    line=matches[0]
    start=re.search(r'start_time=\[[^\]]*?(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) UTC\]',line)
    stop=re.search(r'stop_time=\[[^\]]*?(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) UTC\]',line)
    code=re.search(r'; code=([^ ;]+)',line);status=re.search(r'; status=(\d+)',line)
    if not all([start,stop,code,status]):return dict(status='CURRENT_HOOK_NOT_TERMINAL')
    duration=(datetime.datetime.fromisoformat(stop[1])-datetime.datetime.fromisoformat(start[1])).total_seconds()
    value=dict(observed_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        hook_script=own,started_at_utc=start[1],finished_at_utc=stop[1],
        exit_code=int(status[1]),exit_kind=code[1],duration_seconds=duration,
        hook_timeout_seconds=90,deadline_margin_seconds=90-duration,
        passed=code[1]=='exited' and int(status[1])==0,
        main_service_success_is_not_used_as_hook_success=True)
    target=ROOT/'checks/collection-monitor-last-hook-result-r28.json';pending=target.with_suffix('.tmp')
    pending.write_text(json.dumps(value,indent=2));os.replace(pending,target)
    return value


def read(name,keys):
    try:
        value=json.loads((ROOT/name).read_text());return {k:value.get(k)for k in keys}
    except (OSError,ValueError)as e:return dict(status='UNKNOWN',error=type(e).__name__)


def main():
    now=datetime.datetime.now(datetime.timezone.utc)
    try:hook=collection_hook_result()
    except (OSError,ValueError,subprocess.SubprocessError)as error:hook=dict(status='HOOK_RESULT_UNOBSERVED',error_type=type(error).__name__)
    ledger=ROOT/'manifests/attempt-ledger.jsonl'
    count=sum(1 for line in ledger.open()if line.strip())if ledger.exists()else None
    teacher_jobs=[]
    submitted={}
    for config in sorted((ROOT/'jobs').glob('*/config.json')):
        try:
            job=json.loads(config.read_text())
            if job.get('install_only') or not any(a.get('name')=='open-harness' or str(a.get('import_path','')).endswith(':OpenHarnessAgent') for a in job.get('agents',[])):
                continue
            results=[json.loads(p.read_text())for p in config.parent.glob('*/result.json')]
            for task in job.get('tasks',[]):
                task_id=Path(task['path']).name
                submitted[task_id]=submitted.get(task_id,0)+1
            teacher_jobs.append(dict(job_id=config.parent.name,terminal_results=len(results),
                raw_completed_verifier_reward_one=sum(bool((r.get('verifier')or{}).get('finished_at')) and
                    (r.get('verifier_result')or{}).get('rewards',{}).get('reward')==1 for r in results),
                config_sha256=hashlib.sha256(config.read_bytes()).hexdigest(),
                configured_tasks=len(job.get('tasks',[])),
                configured_finish=[a.get('kwargs',{}).get('config',{}).get('finish',{}).get('enabled') for a in job.get('agents',[])],
                finish_environment=[a.get('env',{}).get('OPEN_HARNESS_FINISH') for a in job.get('agents',[])],
                native_request_accounting_enabled=[a.get('kwargs',{}).get('config',{}).get('tokenObservation',{}).get('enabled') for a in job.get('agents',[])],
                reward_does_not_imply_recorder_or_training_eligibility=True))
        except (OSError,ValueError,KeyError)as error:teacher_jobs.append(dict(job_id=config.parent.name,status='UNKNOWN',error=type(error).__name__))
    stream=[]
    for file in ROOT.glob('stream/*/dispatches/*/dispatch.json'):
        item=json.loads(file.read_text())
        if item['kind']!='teacher':continue
        submitted[item['task_id']]=submitted.get(item['task_id'],0)+1
        result=file.parents[2]/'trials'/item['trial_name']/'result.json'
        stream.append(dict(task_id=item['task_id'],trial_name=item['trial_name'],terminal=result.exists()))
    teacher_jobs.append(dict(native_queue_campaign=True,scope='streamed native TrialConfigs',
        configured_tasks=len(stream),terminal_results=sum(x['terminal'] for x in stream),
        source='stream/*/dispatches/*/dispatch.json; diagnostic-only dispatches excluded'))
    progress=read('progress.json',['checked_at','live_processes','terminal_teacher_trials'])
    try:
        progress['snapshot_age_seconds']=(now-datetime.datetime.fromisoformat(progress['checked_at'])).total_seconds()
    except (KeyError,TypeError,ValueError):progress['snapshot_age_seconds']=None
    r=dict(checked_at=now.isoformat(),beijing_time=now.astimezone(datetime.timezone(datetime.timedelta(hours=8))).isoformat(),
        observer_only=True,observer_pid=os.getpid(),
        collection_monitor_hook=hook,
        source_download=read('checks/tmax-download.json',['status','bytes','expected_bytes','expected_sha256']),
        tmax_tasks=read('checks/tmax500-selection.json',['selected_tasks','native_task_configs_valid','environments_built','manifest_sha256']),
        attempt_ledger=dict(path=str(ledger),recorded_rows=count,status='PRESENT' if ledger.exists() else 'UNKNOWN_MISSING_LEDGER'),
        actual_native_teacher_jobs=teacher_jobs,
        configured_dispatch_accounting=dict(submitted_attempts=sum(submitted.values()),
            distinct_task_ids=len(submitted),per_task_max=max(submitted.values(),default=0),
            within_numeric_caps=sum(submitted.values())<=2000 and len(submitted)<=1000 and max(submitted.values(),default=0)<=2,
            setup_failures_not_subtracted=True,not_a_billing_ledger=True),
        environment_preparation=progress,
        cf_image_preparation=read('checks/cf-image-preparation-v2.json',['status','planned_tasks','observed_tasks','counts']),
        tmax_image_preparation=read('checks/tmax-image-preparation-v2.json',['status','planned_tasks','observed_tasks','counts','final_verifier_acceptance']),
        native_request_accounting=read('checks/native-request-accounting-latest.json',
            ['observed_at','totals','submitted_attempts','independent_tasks','max_submitted_attempts_per_task',
             'numeric_caps_satisfied','unknown_provider_invoice','all_http_transport_retries_captured',
             'monetary_hard_cap_value','request_ledger','attempt_ledger']),
        missing_ledger_does_not_mean_zero_attempts=True)
    from collection_attempts_r8 import attempt_counts
    actual=attempt_counts()
    r['actual_or_conservative_attempt_accounting']=dict(source='collection_attempts_r8; unchanged across R8/R9',submitted_attempts=sum(actual.values()),distinct_task_ids=len(actual),per_task_max=max(actual.values(),default=0),within_actual_numeric_caps=sum(actual.values())<=2000 and len(actual)<=1000 and max(actual.values(),default=0)<=2,proved_setup_only_reservations_retained_separately=True)
    try:
        p=subprocess.run(['systemctl','--user','show','qwen35-new-route-tmax-source-20261029.service',
            'qwen35-new-route-tmax-select-20261029.service','qwen35-new-route-case-audit-20261029.service',
            '-p','Id','-p','MainPID','-p','ActiveState','-p','Result'],capture_output=True,text=True,timeout=12)
        r['units']=dict(returncode=p.returncode,stdout=p.stdout,stderr=p.stderr[:1000])
    except (OSError,subprocess.TimeoutExpired)as e:r['units']=dict(status='UNKNOWN',error=type(e).__name__)
    out=ROOT/'checks/collection149-observation.json';temporary=out.with_suffix('.tmp')
    temporary.write_text(json.dumps(r,indent=2));os.replace(temporary,out)
    # Reuse the already audited remote-only SSH connection, no local heartbeat.
    script="import sys,pathlib,json,os;p=pathlib.Path('/home/chenkeyi/workspace/RSI/runtime-evidence/qwen35-new-cf500-tmax500-20261029/checks/collection149-observation.json');d=json.load(sys.stdin);t=p.with_suffix('.transfer-tmp');t.write_text(json.dumps(d,indent=2));os.replace(t,p)"
    import shlex
    try:
        p=subprocess.run(['ssh','-S',str(Path.home()/'.ssh/cf17-20261028.sock'),'-o','BatchMode=yes',
            '-o','ConnectTimeout=5','chenkeyi@180.163.192.17','python3 -c '+shlex.quote(script)],
            input=json.dumps(r),capture_output=True,text=True,timeout=15)
        transfer=dict(returncode=p.returncode,stderr=p.stderr[:1000],healthy_jobs_signalled=False)
    except (OSError,subprocess.TimeoutExpired)as e:transfer=dict(status='UNKNOWN',error=type(e).__name__,healthy_jobs_signalled=False)
    (ROOT/'checks/observer-transfer.json').write_text(json.dumps(transfer,indent=2))
    print(json.dumps({'observed_at':r['checked_at'],'transfer':transfer}))


if __name__=='__main__':main()
