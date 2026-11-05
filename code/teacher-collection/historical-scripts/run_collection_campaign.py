"""Finite campaign phase glue; all trial scheduling/lifecycle stays in Harbor Job.

Wait for the actual canary/data-preparation evidence, run one continuous first
pass, then at most one explicitly audited second attempt per unresolved task.
No model/provider/sandbox protocol or task/verifier file is changed here.
"""
import asyncio
from collections import Counter
import copy
import datetime
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import tomllib
from itertools import zip_longest

from harbor.job import Job
from harbor.models.job.config import JobConfig
from harbor.models.task.config import TaskConfig as NativeTaskConfig

ROOT=Path('/home/chenkeyi/.local/share/harbor-rsi/qwen35-new-cf500-tmax500-20261029')
TEACHER_SHA='bf9069d53ec81d6f53a1a93f35bd61a0a8eadb42deafb4fc1c6540bf10afba2c'
WHEEL_SHA='c686ba3f429d8257a060cf6b6a6e4c5aa7d740f33b2d59180d9a2717b55d0db8'
REVISIONS=dict(calibforge='c2fae4c1f536461142b2a89a8b9423a8bc376088',tmax='e3ded940596cc611c9815684ba51a7e8ee0cffc9')


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):return json.loads(path.read_text())


def state(phase,**details):
    value=dict(status=phase,pid=os.getpid(),checked_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        teacher_tasks_cap=1000,complete_attempts_cap=2000,per_task_attempts_cap=2,native_concurrency=8,
        teacher_config_sha256=TEACHER_SHA,wheel_sha256=WHEEL_SHA,**details)
    path=ROOT/'campaign-state.json';temporary=path.with_suffix('.tmp');temporary.write_text(json.dumps(value,indent=2));temporary.replace(path)
    print(json.dumps(value),flush=True)


def submitted_attempts():
    counts=Counter()
    for file in (ROOT/'jobs').glob('*/config.json'):
        config=read(file)
        if config.get('install_only') or not any(a.get('name')=='open-harness' for a in config.get('agents',[])):continue
        if config.get('n_attempts',1)!=1 or config.get('retry',{}).get('max_retries',0)!=0:
            raise ValueError('Unexpected native retries/replicates in this campaign')
        for task in config['tasks']:counts[Path(task['path']).name]+=1
    if sum(counts.values())>2000 or max(counts.values(),default=0)>2 or len(counts)>1000:
        raise ValueError('Existing campaign dispatch exceeds authorized limits')
    return counts


def eligible_taskset():
    gate=ROOT/'checks/CANARY_GATE.json';identity=ROOT/'manifests/TASKSET_READY.json'
    if not gate.exists() or not identity.exists():return None
    g=read(gate);ready=read(identity)
    if not g.get('passed') or not ready.get('all_environments_and_verifiers_ready'):return None
    if g.get('unique_canary_tasks_by_pool')!=dict(calibforge=8,tmax=8):raise ValueError('Canary scope differs')
    if g.get('teacher_config_sha256')!=TEACHER_SHA or g.get('wheel_sha256')!=WHEEL_SHA:
        raise ValueError('Canary and formal teacher identities differ')
    file=Path(ready['task_manifest_path'])
    if sha(file)!=ready['task_manifest_sha256']:raise ValueError('Final runnable task manifest changed')
    rows=[json.loads(line) for line in file.open()]
    if len(rows)!=1000 or len({r['task_id'] for r in rows})!=1000 or Counter(r['pool'] for r in rows)!=dict(calibforge=500,tmax=500):
        raise ValueError('Final scope must be 500 unique tasks in each pool')
    families={}
    runtime_images=[]
    for row in rows:
        if row['revision']!=REVISIONS[row['pool']] or row['split'] not in ['train','validation']:
            raise ValueError('Dataset revision or fixed split differs')
        family=(row['pool'],row['family_id'])
        if family in families and families[family]!=row['split']:raise ValueError('Task family split leakage')
        families[family]=row['split'];path=Path(row['prepared_task_path'])
        if sha(path/'instruction.md')!=row['instruction_sha256'] or sha(path/'task.toml')!=row['prepared_task_toml_sha256']:
            raise ValueError('Runnable task identity changed')
        original=tomllib.loads((path/'task.toml').read_text())
        native=NativeTaskConfig.model_validate(original)
        if row['pool']=='tmax' and (native.environment.workdir!='/home/user' or native.environment.env.get('HOME')!='/home/user'):
            raise ValueError('TMax original --pwd/HOME contract is not reproduced')
        if native.verifier.timeout_sec!=row['original_verifier_timeout_sec']:
            raise ValueError('Original verifier deadline changed')
        for key in ['cpus','memory_mb','storage_mb','gpus']:
            if getattr(native.environment,key)!=row['original_resources'][key]:raise ValueError('Original environment resources changed')
        if not row['verifier_files']:raise ValueError('Official verifier identities absent')
        for item in row['verifier_files']:
            relative=Path(item['relative_path'])
            if relative.is_absolute() or '..' in relative.parts or not str(relative).startswith('tests/'):
                raise ValueError('Invalid verifier identity path')
            if sha(path/relative)!=item['sha256']:raise ValueError('Official verifier bytes changed')
        runtime_images.append(native.environment.docker_image)
        if original.get('agent',{}).get('timeout_sec',0)>10800:
            raise ValueError('Common override would shorten an original deadline; explicit per-task policy required')
        if row['agent_timeout_override_sec']!=max(original.get('agent',{}).get('timeout_sec',0),10800):
            raise ValueError('Research agent timeout policy differs')
    attempts=submitted_attempts()
    if not set(attempts)<=set(r['task_id'] for r in rows):raise ValueError('Previously attempted task was replaced')
    inspected=json.loads(subprocess.run(['docker','image','inspect',*runtime_images],check=True,
        capture_output=True,text=True,timeout=120).stdout)
    if [x['Id'] for x in inspected]!=[r['image_id'] for r in rows]:raise ValueError('Prepared image identity changed')
    return rows,ready


def config_for(name,rows):
    cfg=copy.deepcopy(read(ROOT/'configs/canary-summary-cf.json'))
    if sha(ROOT/'configs/teacher-native-11tools-summary-r1.json')!=TEACHER_SHA:raise ValueError('Frozen teacher configuration changed')
    if cfg['agents'][0]['kwargs']['wheel_sha256']!=WHEEL_SHA:raise ValueError('Harness wheel differs')
    cf=[r for r in rows if r['pool']=='calibforge'];tf=[r for r in rows if r['pool']=='tmax']
    interleaved=[r for pair in zip_longest(cf,tf) for r in pair if r is not None]
    cfg.update(job_name=name,n_attempts=1,n_concurrent_trials=8,retry=dict(max_retries=0),tasks=[dict(path=r['prepared_task_path']) for r in interleaved])
    cfg['environment']['kwargs']['project_namespace']='cftmaxformal20261030'
    return JobConfig.model_validate(cfg)


async def run_native(name,rows):
    if not rows:return
    attempts=submitted_attempts()
    if sum(attempts.values())+len(rows)>2000 or any(attempts[r['task_id']]>=2 for r in rows):
        raise ValueError('Dispatch would exceed research attempt cap')
    destination=ROOT/'jobs'/name
    if destination.exists():
        raise FileExistsError('Existing native job needs observation/resume; never replay under another identity')
    config=config_for(name,rows);file=ROOT/'configs'/(name+'.json')
    with file.open('x') as stream:stream.write(config.model_dump_json(indent=2))
    state('RUNNING_NATIVE_JOB',job_name=name,tasks=len(rows),config_sha256=sha(file))
    job=await Job.create(config)
    await job.run()
    state('NATIVE_JOB_TERMINAL_AWAITING_QUALIFICATION',job_name=name)


async def main():
    if not os.environ.get('DEEPSEEK_API_KEY'):raise RuntimeError('Authorized key absent from private controller environment')
    if not read(ROOT/'checks/scoped-ssh-client2-native-install8.json')['passed']:raise ValueError('Native SSH concurrency proof absent')
    while True:
        prepared=eligible_taskset()
        if prepared is not None:break
        state('WAITING_FOR_CANARY_AND_ALL_1000_ENVIRONMENTS',submitted_attempts=sum(submitted_attempts().values()),
            required_files=['checks/CANARY_GATE.json','manifests/TASKSET_READY.json'])
        await asyncio.sleep(1200)
    rows,ready=prepared;counts=submitted_attempts()
    first=[r for r in rows if counts[r['task_id']]==0]
    # Membership is fixed before dispatch; native Harbor continuously fills slots.
    await run_native('cf-tmax-formal-first-pass-summary-r1-20261030',first)
    while True:
        plan_file=ROOT/'manifests/SECOND_ATTEMPT_PLAN.json'
        if plan_file.exists():
            plan=read(plan_file)
            if plan.get('qualification_complete') and plan.get('task_manifest_sha256')==ready['task_manifest_sha256']:break
        state('WAITING_FOR_COMPLETE_FIRST_PASS_QUALIFICATION')
        await asyncio.sleep(1200)
    counts=submitted_attempts();wanted=set(plan['task_ids']);mapping={r['task_id']:r for r in rows}
    if not wanted<=set(mapping):raise ValueError('Second-attempt plan contains a task outside the frozen set')
    if any(counts[t]!=1 for t in wanted):raise ValueError('Second-attempt task was not tried exactly once')
    if wanted&set(plan['qualified_success_task_ids']):raise ValueError('Qualified task must stop immediately')
    await run_native('cf-tmax-formal-second-pass-summary-r1-20261030',[mapping[t] for t in sorted(wanted)])
    state('COLLECTION_TERMINAL_FINAL_DATA_AUDIT_PENDING',submitted_attempts=sum(submitted_attempts().values()))


if __name__=='__main__':
    os.environ['PATH']=str(ROOT/'client-bin-v2')+':'+os.environ['PATH']
    os.environ['SSH_AUTH_SOCK']='/home/chenkeyi/.local/share/harbor-rsi/near-r3-20261015/auth.sock'
    async def entry():
        loop=asyncio.get_running_loop();current=asyncio.current_task()
        loop.add_signal_handler(signal.SIGTERM,current.cancel)
        try:await main()
        except asyncio.CancelledError:
            state('CANCELLED_REQUIRES_NATIVE_RESOURCE_AUDIT');raise
    try:asyncio.run(entry())
    except KeyboardInterrupt:state('CANCELLED_REQUIRES_NATIVE_RESOURCE_AUDIT');raise
    except Exception as error:state('CONTROLLER_ERROR_REQUIRES_INSPECTION',error_type=type(error).__name__,error=str(error));raise
