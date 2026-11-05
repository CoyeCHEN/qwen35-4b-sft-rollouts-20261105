"""One exact original public input-image/font candidate; native initial/CLI/official NOP."""
import asyncio
import datetime
import fcntl
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import toml
import tomllib
from uuid import uuid4

from harbor.models.job.config import RetryConfig
from harbor.trial.queue import TrialQueue
import collection_readiness_r11 as n
from collection_attempts_r8 import attempt_counts
from collection_selection_r7 import active_rows

S=n.R/'stream/public-font-image-native17-r74'
IDENT='task_001742_6788502c'


async def main():
    S.mkdir(parents=True,exist_ok=True)
    lock=(S/'worker.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    if (S/'PLAN.json').exists():raise FileExistsError('Inspect existing candidate; no implicit replay')
    builder=n.R/'scripts/build_original_public_image_font17_r72b.py'
    builder17='/home/chenkeyi/workspace/RSI/runtime-evidence/'+n.R.name+'/scripts/'+builder.name
    n.freeze(S/'PLAN.json',dict(tasks=[IDENT],source_sha256=n.sha(Path(__file__)),builder_sha256=n.sha(builder),
        node='17',engine_id=n.NODE['engine_id'],model_calls=0,teacher_dispatches=0,native_concurrency=1,
        active_controller_ready_publications=0))
    def state(stage):
        v=dict(pid=os.getpid(),checked_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
            current_task_id=IDENT,stage=stage,model_calls=0,teacher_dispatches=0)
        p=S/'state.tmp';p.write_text(json.dumps(v,indent=2));p.replace(S/'state.json')
    previous=n.R/'stream/public-pytest-image-native17-r69/TERMINAL.json'
    if not previous.exists():raise ValueError('Previous public-library native acceptance has not ended')
    n.freeze(S/'SLOT_ACCEPTANCE.json',dict(previous_terminal=str(previous),previous_terminal_sha256=n.sha(previous),
        maximum_independent_native_preparers=2,campaign_preparation_limit=n.DEPLOYMENT['preparation_concurrency'],
        concurrent_other_preparer='original-runtime-process-native17-r71',teacher_dispatches=0))
    if attempt_counts().get(IDENT,0):raise ValueError('Already attempted; preserve original identity')
    row=next(x for x in active_rows(attempt_counts()) if x['task_id']==IDENT)
    plan=json.loads((n.R/'manifests/TMAX_UNATTEMPTED_INITIAL_FAILURE_CONTEXTS_R58.json').read_text())
    item=next(x for x in plan['tasks'] if x['task_id']==IDENT);path=Path(item['old_basic_receipt'])
    if n.sha(path)!=item['old_basic_receipt_sha256']:raise ValueError('Original source/image receipt changed')
    original=n.prepared(n.choose(row),(path,json.loads(path.read_text())))
    declared_image=original['image_id']
    root=n.R/'stream/original-initial-failure-build17-r58'
    old_build=json.loads((root/'build-receipts'/IDENT/'build.json').read_text())
    old_task=root/'prepared-tasks'/IDENT
    expected=tomllib.loads((Path(original['prepared_task_path'])/'task.toml').read_text())
    expected['environment']['docker_image']=old_build['native_manifest_digest']
    if tomllib.loads((old_task/'task.toml').read_text())!=expected:raise ValueError('Original-context native17 base Task differs')
    for artifact in original['verifier_files']:
        if n.sha(old_task/artifact['path'])!=artifact['sha256']:raise ValueError('Official verifier bytes differ')
    original=dict(original,prepared_task_path=str(old_task),prepared_task_toml_sha256=n.sha(old_task/'task.toml'),image_id=old_build['native_manifest_digest'])
    remote=n.NODE['ssd_root']+'/original-public-image-font-r72b/build.json';local=S/'build.json'
    subprocess.run(['rsync','-a','-e',shlex.join(n.DEPLOYMENT['ssh']),n.DEPLOYMENT['host']+':'+remote,str(local)],check=True,timeout=120)
    built=json.loads(local.read_text())
    if built['original_image_id']!=original['image_id'] or built['source_sha256']!=n.sha(builder):
        raise ValueError('Candidate source/Engine/base image changed')
    if built['original_input_permission_initialization']!='chmod -R 777 /app':raise ValueError('Original input permission setup missing')
    code="import json,hashlib,subprocess;from pathlib import Path;b=json.loads(Path("+repr(remote)+").read_text());a=Path(b['archive']);assert hashlib.sha256(a.read_bytes()).hexdigest()==b['archive_sha256'];cli=['docker','--host',"+repr('unix://'+n.NODE['socket'])+"];assert subprocess.run(cli+['info','--format','{{.ID}}'],check=True,capture_output=True,text=True).stdout.strip()=="+repr(n.NODE['engine_id'])+";subprocess.run(cli+['image','load','--input',str(a)],check=True,capture_output=True,text=True);print(json.dumps({'loaded_image_id':b['image_id']}))"
    state('MATERIALIZING_HASHED_PUBLIC_FONT_CANDIDATE_ON_PRIVATE17')
    loaded=await asyncio.to_thread(subprocess.run,[*n.DEPLOYMENT['ssh'],n.DEPLOYMENT['host'],shlex.join([n.DEPLOYMENT['python17'],'-c',code])],check=True,capture_output=True,text=True,timeout=1800)
    n.freeze(S/'image-materialization.json',json.loads(loaded.stdout))
    old=Path(original['prepared_task_path']);prepared=S/'prepared-task';shutil.copytree(old,prepared)
    config=tomllib.loads((old/'task.toml').read_text());config['environment']['docker_image']=built['image_id']
    (prepared/'task.toml').write_text(toml.dumps(config))
    for p in old.rglob('*'):
        if p.is_file() and p.relative_to(old)!=Path('task.toml') and n.sha(p)!=n.sha(prepared/p.relative_to(old)):
            raise ValueError('Original Task/test bytes changed')
    admitted=dict(original,prepared_task_path=str(prepared),prepared_task_toml_sha256=n.sha(prepared/'task.toml'),
        image_id=built['image_id'],original_published_image_id=declared_image,exact_native17_base_image_id=original['image_id'])
    state('ORIGINAL_INITIAL_TEST_WITH_EXACT_PUBLIC_INPUT_IMAGE_ON17')
    n.freeze(S/'initial.json',await asyncio.to_thread(n.initial,admitted))
    queue=TrialQueue(n_concurrent=1,retry_config=RetryConfig(max_retries=0))
    out=dict(task_id=IDENT,pool='tmax',status='CANDIDATE_ENV_FAILED',admitted_task=admitted,
        original_image_id=original['image_id'],declared_prepared_source_image_id=declared_image,image_id=built['image_id'],build_receipt=str(local),build_receipt_sha256=n.sha(local),
        model_calls=0,teacher_dispatches=0,published_current_controller_ready=False)
    try:
        for kind in ['install','nop']:
            state('NATIVE_'+kind.upper()+'_ON17')
            cfg=n.native_config(admitted,kind);cfg.trials_dir=S/'trials'
            if kind=='install':cfg.agent.env={}
            network=S/'network.json';n.freeze(network,dict(networks=dict(default=dict(ipam=dict(config=[dict(subnet='10.249.228.0/28')])))))
            cfg.environment.extra_docker_compose=[network,*cfg.environment.extra_docker_compose[1:]]
            d=S/'dispatches'/str(uuid4());d.mkdir(parents=True);(d/'trial-config.json').write_text(cfg.model_dump_json(indent=2))
            n.freeze(d/'dispatch.json',dict(task_id=IDENT,pool='tmax',kind=kind,trial_name=cfg.trial_name,model_calls=0,config_sha256=n.sha(d/'trial-config.json')))
            result=await queue.submit(cfg);trial=S/'trials'/cfg.trial_name
            out['native_'+kind+'_trial']=str(trial);out[kind+'_result_sha256']=n.sha(trial/'result.json')
            n.freeze(S/'ssd-trial-archives'/(trial.name+'.json'),await asyncio.to_thread(n.archive_trial,trial))
            if result.exception_info or result.infrastructure_errors:raise ValueError('Native candidate lifecycle failure: '+str(result.exception_info))
            if kind=='nop':out['nop_reward']=n.verify_nop(result,trial,admitted)
        out['status']='CANDIDATE_ENV_READY_PENDING_IMAGE_BINDING_APPROVAL'
    except Exception as error:out.update(error_type=type(error).__name__,reason=str(error)[-1500:])
    n.freeze(S/'candidate-outcomes'/(IDENT+'.json'),out)
    state('PUBLIC_FONT_IMAGE_NATIVE_ACCEPTANCE_TERMINAL')
    n.freeze(S/'TERMINAL.json',out)
    print(json.dumps(dict(task_id=IDENT,status=out['status'],reason=out.get('reason'))),flush=True)


if __name__=='__main__':
    os.environ['PATH']=str(n.R/'client-bin-v2')+':'+os.environ['PATH']
    for key in ['DEEPSEEK_API_KEY','OPENAI_API_KEY','GH_TOKEN']:os.environ.pop(key,None)
    asyncio.run(main())
