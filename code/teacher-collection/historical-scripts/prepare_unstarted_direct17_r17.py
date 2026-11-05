"""Finite original-context builds and native checks on17, with zero model calls."""
import asyncio
import copy
import datetime
import fcntl
import hashlib
import ipaddress
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
import collection_readiness_r7 as n
from collection_attempts_r8 import attempt_counts
from collection_selection_r7 import active_rows
import run_collection_stream_r4 as c

S=n.R/'stream/direct17-native-source-r17'
E17='/home/chenkeyi/workspace/RSI/runtime-evidence/'+n.R.name
BUILDER=E17+'/scripts/build_tmax_native_oci_ssd17_r17.py'


def run(args,**kwargs):return subprocess.run(args,check=True,**kwargs)
def remote(code,*args,timeout=90):
    reply=run([*n.DEPLOYMENT['ssh'],n.DEPLOYMENT['host'],shlex.join([n.DEPLOYMENT['python17'],'-c',code,*args])],capture_output=True,text=True,timeout=timeout)
    return json.loads(reply.stdout)


def native_precheck_config(admitted,kind,index):
    cfg=n.native_config(admitted,kind);cfg.trials_dir=S/'trials'
    if kind=='install':cfg.agent.env={}
    network=n.R/'configs/direct17-native-precheck-r17'/(admitted['task_id']+'.json')
    subnet=str(ipaddress.ip_network((int(ipaddress.ip_address('10.242.0.0'))+index*16,28)))
    n.freeze(network,dict(networks=dict(default=dict(ipam=dict(config=[dict(subnet=subnet)])))))
    cfg.environment.extra_docker_compose=[network,*cfg.environment.extra_docker_compose[1:]]
    # Native RemoteDocker resolves these Path objects before a Trial starts.
    for path in cfg.environment.extra_docker_compose:path.expanduser().resolve()
    return cfg,subnet


async def main():
    S.mkdir(parents=True,exist_ok=True)
    handoff=n.R/'checks/direct17-build-preparation-handoff-r17.json'
    transition=json.loads(handoff.read_text())
    if transition['status']!='OLD_PREPARERS_NATIVE_WORK_FINISHED_NEW_PRIVATE_BUILDER_AUTHORIZED':raise ValueError('Native preparation handoff is not complete')
    if any(Path('/proc/'+str(pid)).exists() for pid in transition['retired_preparer_pids']):raise ValueError('Old finite preparer still alive')
    lock=(S/'worker.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    plan_file=n.R/'manifests/TMAX_UNSTARTED_DIRECT_SSD17_R13.json';plan=json.loads(plan_file.read_text())
    staged=n.R/'checks/direct17-context-staging-r13.json'
    if json.loads(staged.read_text())['plan_sha256']!=n.sha(plan_file):raise ValueError('Staged context plan differs')
    builder_sha=n.sha(n.R/'scripts/build_tmax_native_oci_ssd17_r17.py')
    build_config=n.R/'configs/campaign-build17-r17.json';build_deployment=json.loads(build_config.read_text())
    if build_deployment['runtime_engine_id']!=n.NODE['engine_id'] or build_deployment['socket']!=n.DEPLOYMENT['environment']['kwargs']['remote_socket_path']:
        raise ValueError('Preparation/build/runtime deployment identities differ')
    probe="import hashlib,json,sys;from pathlib import Path;p=Path(sys.argv[1]);print(json.dumps({'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}))"
    if remote(probe,BUILDER)['sha256']!=builder_sha:raise ValueError('Accepted native builder source differs')
    if remote(probe,E17+'/configs/campaign-build17-r17.json')['sha256']!=n.sha(build_config):raise ValueError('Campaign build deployment differs across metadata mirrors')
    n.freeze(S/'PLAN.json',dict(source_plan=str(plan_file),source_plan_sha256=n.sha(plan_file),tasks=plan['tasks'],handoff=str(handoff),handoff_sha256=n.sha(handoff),
        source_sha256=n.sha(Path(__file__)),builder_sha256=builder_sha,node='17',engine_id=n.NODE['engine_id'],
        build_deployment=str(build_config),build_deployment_sha256=n.sha(build_config),
        build_concurrency=1,native_precheck_concurrency=1,teacher_dispatches=0,model_calls=0,
        prepared_copy='New deployment-specific external image-pin copies; original Tasks and earlier prepared copies remain immutable',
        precheck_network='Separate native zero-model bridge CIDRs10.242/16 avoid overlap with an independently preparing same Task; teacher retains the frozen10.241/16 network contract'))
    queue=TrialQueue(n_concurrent=1,retry_config=RetryConfig(max_retries=0));results={}
    def state(current,stage):
        value=dict(pid=os.getpid(),checked_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),status='FINITE_DIRECT17_NATIVE_PREPARATION',
            planned_tasks=len(plan['tasks']),observed_tasks=len(results),current_task_id=current,stage=stage,
            counts={x:list(results.values()).count(x) for x in set(results.values())},model_calls=0,teacher_dispatches=0,
            node='17',engine_id=n.NODE['engine_id'],build_concurrency=1,native_precheck_concurrency=1)
        tmp=S/'state.tmp';tmp.write_text(json.dumps(value,indent=2));tmp.replace(S/'state.json')
    for index,item in enumerate(plan['tasks']):
        ident=item['task_id'];out=dict(task_id=ident,pool='tmax',status='ENV_FAILED',node='17',model_calls=0,teacher_dispatches=0)
        admitted=None
        try:
            if attempt_counts().get(ident,0):
                out.update(status='ALREADY_STARTED_TASK_PRESERVED',reason='No image rebuild or Trial replay after actual admission');continue
            if n.sha(Path(item['old_basic_receipt']))!=item['old_basic_receipt_sha256']:
                raise ValueError('Original source receipt changed')
            row=next(x for x in active_rows(attempt_counts()) if x['task_id']==ident)
            base=n.prepare_identity(row)
            old=n.R/'stream/direct17-native-source-r14/environment-outcomes'/(ident+'.json')
            if old.exists():
                known=json.loads(old.read_text())
                if known['status']=='ENV_READY':
                    if known['engine_id']!=n.NODE['engine_id'] or known['deployment_config_sha256']!=n.CONFIG_SHA:raise ValueError('Old positive readiness belongs to another deployment')
                    previous=known['admitted_task'];prepared=Path(previous['prepared_task_path'])
                    if n.sha(prepared/'task.toml')!=previous['prepared_task_toml_sha256'] or n.sha(prepared/'instruction.md')!=row['instruction_sha256']:raise ValueError('Earlier prepared Task changed')
                    for artifact in previous['verifier_files']:
                        if n.sha(prepared/artifact['path'])!=artifact['sha256']:raise ValueError('Earlier official verifier changed')
                    for kind in ['install','nop']:
                        result=Path(known['native_'+kind+'_trial'])/'result.json'
                        if n.sha(result)!=known[kind+'_result_sha256']:raise ValueError('Earlier native Result changed')
                    out.update(status='EXISTING_VALIDATED_NATIVE17_READY_PRESERVED',reason='Reuse completed original CLI/NOP checks and existing Ready; no repeat',prior_ready=str(old),prior_ready_sha256=n.sha(old))
                    continue
            state(ident,'READING_COMPLETED_UNCHANGED_CONTEXT_BUILD_ON17')
            destination=n.NODE['ssd_root']+'/buildkit-rootless-r2/archives/'+ident+'/client-proxy-r3/build.json'
            observe="import json,sys;from pathlib import Path;p=Path(sys.argv[1]);print(p.read_text() if p.exists() else json.dumps({'absent':True}))"
            built=await asyncio.to_thread(remote,observe,destination)
            if built.get('absent'):
                state(ident,'BUILDING_UNCHANGED_CONTEXT_ON_PRIVATE17')
                command=shlex.join([n.DEPLOYMENT['python17'],BUILDER,ident,item['metadata']['source_manifest_sha256']])
                reply=await asyncio.to_thread(subprocess.run,[*n.DEPLOYMENT['ssh'],n.DEPLOYMENT['host'],command],stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,text=True,timeout=3800)
                built=await asyncio.to_thread(remote,observe,destination)
                out['native_build_returncode']=reply.returncode
            receipt=S/'build-receipts'/ident/'build.json';n.freeze(receipt,built)
            if built['status']!='ORIGINAL_NATIVE_OCI_ARCHIVE_BUILT_INITIAL_AND_VERIFIER_TESTS_PENDING' or not built['all_manifest_config_layer_hashes_verified']:
                raise ValueError('Original-context build did not complete; original build log retained')
            if built['source_context']!=item['metadata']:
                raise ValueError('Rebuild changed the original native context')
            image=built['native_manifest_digest']
            # The exact per-Task cache identity is immutable. If an earlier
            # accepted image arrived while building, retain that17 identity.
            existing=await asyncio.to_thread(remote,observe,E17+'/checks/cold-image-sizes-r1/'+ident+'.json')
            if not existing.get('absent') and existing['image_id']!=image:
                out.update(status='EXISTING_EXACT17_IMAGE_IDENTITY_PRESERVED',reason='A verified image was materialized on17 while this unchanged-context build ran; no earlier binding overwritten',existing_image_id=existing['image_id'],new_original_context_build=str(receipt));continue
            if attempt_counts().get(ident,0):
                out.update(status='ALREADY_STARTED_TASK_PRESERVED',reason='Actual admission occurred during source build; keep its original configuration',new_original_context_build=str(receipt));continue
            original_copy=Path(base['prepared_task_path']);new_copy=S/'prepared-tasks'/ident
            if new_copy.exists():raise FileExistsError('Never overwrite a prepared deployment copy')
            shutil.copytree(original_copy,new_copy)
            expected=tomllib.loads((original_copy/'task.toml').read_text());expected['environment']['docker_image']=image
            (new_copy/'task.toml').write_text(toml.dumps(expected))
            if tomllib.loads((new_copy/'task.toml').read_text())!=expected:raise ValueError('External image pin differs')
            for p in original_copy.rglob('*'):
                if p.is_file() and p.relative_to(original_copy)!=Path('task.toml') and n.sha(p)!=n.sha(new_copy/p.relative_to(original_copy)):
                    raise ValueError('Original Task member changed in external deployment copy')
            admitted=dict(base,prepared_task_path=str(new_copy),prepared_task_toml_sha256=n.sha(new_copy/'task.toml'),image_id=image,
                preparation_receipt=str(receipt),preparation_receipt_sha256=n.sha(receipt),
                previous_external_prepared_task=str(original_copy),previous_image_id=base['image_id'],deployment_image_binding_revision='r17')
            state(ident,'MATERIALIZING_AND_CHECKING_INITIAL_STATE_ON17')
            n.freeze(S/'image-materializations'/(ident+'.json'),await asyncio.to_thread(n.ensure_resident,admitted))
            n.freeze(S/'initial-outcomes'/(ident+'.json'),await asyncio.to_thread(n.initial,admitted))
            for kind in ['install','nop']:
                state(ident,'NATIVE_'+kind.upper()+'_ON17')
                # Only these NOP/install checks get a separate private bridge.
                # New teachers are created by the sole frozen R7 controller.
                cfg,subnet=native_precheck_config(admitted,kind,index)
                d=S/'dispatches'/str(uuid4());d.mkdir(parents=True);(d/'trial-config.json').write_text(cfg.model_dump_json(indent=2))
                n.freeze(d/'dispatch.json',dict(task_id=ident,pool='tmax',kind=kind,trial_name=cfg.trial_name,config_sha256=n.sha(d/'trial-config.json'),model_calls=0,precheck_only_subnet=subnet))
                result=await queue.submit(cfg);trial=S/'trials'/cfg.trial_name
                out['native_'+kind+'_trial']=str(trial);out[kind+'_result_sha256']=n.sha(trial/'result.json')
                n.freeze(S/'ssd-trial-archives'/(trial.name+'.json'),await asyncio.to_thread(n.archive_trial,trial))
                if result.exception_info or result.infrastructure_errors:raise ValueError('Native17 '+kind+' lifecycle failed: '+str(result.exception_info))
                if kind=='nop':out['nop_reward']=n.verify_nop(result,trial,admitted)
            if attempt_counts().get(ident,0):
                out.update(status='ALREADY_STARTED_TASK_PRESERVED',reason='Another already-started native Task admitted before preparation completed; no new image binding published');continue
            out.update(status='ENV_READY',admitted_task=admitted,engine_id=n.NODE['engine_id'],deployment_config_sha256=n.CONFIG_SHA,
                placement=admitted['deployment_assignment'],placement_sha256=admitted['deployment_assignment_sha256'],
                original_context_build=str(receipt),original_context_build_sha256=n.sha(receipt),teacher_success_not_implied=True,
                original_task_or_tests_modified=False,old_trial_configurations_modified=False,image_bytes_via149_by_this_preparer=0)
        except Exception as error:
            out.update(error_type=type(error).__name__,reason=str(error)[-1600:])
        finally:
            path=S/'environment-outcomes'/(ident+'.json');n.freeze(path,out)
            if out['status']=='ENV_READY':
                ready=dict(out,raw_outcome=str(path),raw_outcome_sha256=n.sha(path))
                digest=hashlib.sha256(json.dumps(ready,sort_keys=True).encode()).hexdigest()
                n.freeze(n.D/'ready-revisions'/ident/(digest+'.json'),ready)
            if admitted is not None:
                try:n.freeze(S/'image-release'/(ident+'.json'),await asyncio.to_thread(n.release_cold_cache,admitted))
                except Exception as error:n.freeze(S/'image-release-errors'/(ident+'.json'),dict(error_type=type(error).__name__,reason=str(error)[-800:]))
            results[ident]=out['status'];state(ident,'TASK_PREPARATION_TERMINAL')
            print(json.dumps(dict(task_id=ident,status=out['status'],reason=out.get('reason'))),flush=True)
    state(None,'FINITE_DIRECT17_NATIVE_PREPARATION_TERMINAL')
    n.freeze(S/'TERMINAL.json',json.loads((S/'state.json').read_text()))


if __name__=='__main__':
    os.environ['PATH']=str(n.R/'client-bin-v2')+':'+os.environ['PATH']
    for key in ['DEEPSEEK_API_KEY','GH_TOKEN','OPENAI_API_KEY']:os.environ.pop(key,None)
    asyncio.run(main())
