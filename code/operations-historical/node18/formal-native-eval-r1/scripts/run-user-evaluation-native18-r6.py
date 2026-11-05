"""Native disjoint pre-model setup continuation, or selected-model 267 campaign."""
import argparse,asyncio,hashlib,importlib,json,os,subprocess,time,urllib.request
from collections import Counter
from pathlib import Path
from harbor.job import Job
from harbor.models.job.config import JobConfig
from harbor.models.trial.config import TrialConfig
base=importlib.import_module('run-user-evaluation-native18-r1')
prep=importlib.import_module('evaluation-preparation18-r1')
R=base.R;E=base.E;C=base.C;read=base.read;sha=base.sha;write=base.write
def read_jsonl_first(path):return json.loads(path.open().readline())


def configuration(tag,recovery=False):
    if not recovery:return base.configuration(tag)
    deployment=read(R/'configs/diagnostic150-five-model-r1.json')
    plan=read(E/'manifests'/('PRE_MODEL_ENV_RECOVERY_PLAN_'+tag+'_R1.json'))
    model=plan['model'];cfg=JobConfig.model_validate_json(base.native.selected_config(read(E/'manifests/FORMAL_801_TRIAL_PLAN.json')).read_text())
    names={x['task_id']for x in plan['trials']};cfg.tasks=[x for x in cfg.tasks if x.path.name in names]
    cfg.agents=[TrialConfig.model_validate(plan['trials'][0]['original_config']).agent]
    cfg.environment=TrialConfig.model_validate(plan['trials'][0]['original_config']).environment
    cfg.n_attempts=1;cfg.n_concurrent_trials=model['concurrency'];cfg.job_name=model['job_name'];cfg.jobs_dir=E/'jobs';cfg.retry.max_retries=0
    assert len(cfg.tasks)==model['new_trials']==len(plan['trials'])
    return deployment,model,cfg,plan


def configure_trials(job,tag,plan,recovery=False):
    by_identity={(x['task_id'],x['repetition']):x for x in plan['trials']};seen=Counter();ordered=[]
    for index,trial in enumerate(job._trial_configs):
        task=trial.task.path.name;seen[task]+=1;item=by_identity[(task,seen[task])];ordered.append(item)
        if recovery:
            evidence=prep.pre_model_failure(Path(item['original_trial_path']))
            assert evidence and evidence['result_sha256']==item['result_sha256']and evidence['config_sha256']==item['config_sha256']
            actual=TrialConfig.model_validate(item['original_config'])
            actual.trial_name=item['trial_name'];actual.trials_dir=job.job_dir;actual.job_id=job.id
            job._trial_configs[index]=actual
    if not recovery:
        base.native.apply_trial_overrides(job._trial_configs,dict(trials=ordered),read(R/'environment-preflight30/environment-profiles-recheck-r2.json'),namespace='q35selected267')
    for trial,item in zip(job._trial_configs,ordered):
        prep.append_ipam(trial,tag,item['task_id'],item['repetition'])
    return ordered


def pipeline_cache_plan(admission):
    path=Path(admission['public_pipeline_cache_plan_path'])
    assert path==E/'manifests/SELECTED267_PIPELINE_PUBLIC_CACHE_PLAN_R1.json'
    assert sha(path)==admission['public_pipeline_cache_plan_sha256']
    plan=read(path);source=Path(plan['source_sampling_manifest_path'])
    assert sha(source)==plan['source_sampling_manifest_sha256']=='76c5e01fcb0bc26809e7ae058f92c4933fd57ae32bdf91e4c8c4462331552a48'
    sampling=read(source);assert plan['source_public_cache_binding']==sampling['public_cache_binding']
    row=next(x for x in sampling['rows']if x['task_id']=='torch-pipeline-parallelism')
    assert plan['task_id']=='torch-pipeline-parallelism' and plan['runtime_spec_path']==row['spec']['path'] and plan['runtime_spec_sha256']==row['spec']['sha256']
    assert sha(Path(plan['runtime_spec_path']))==plan['runtime_spec_sha256']
    spec=read(Path(plan['runtime_spec_path']))
    assert spec['engine_id']==plan['expected_engine_id']==base.native.D['task_engine']['id']
    assert spec['expected_image_id']==plan['expected_image_id']==row['official_identity']['image_id']==sampling['public_cache_binding']['task_images'][plan['task_id']]
    for key in ['archive_receipt_sha256','archive_sha256']:assert plan[key]==sampling['public_cache_binding'][key]
    assert plan['inherited_materializer_sha256']==sampling['public_cache_binding']['materializer_sha256']
    assert plan['cached_torch_version']==plan['official_torch_pin']=='2.7.0'
    assert plan['project_namespace']=='q35selected267' and plan['excluded_direct271_task_ids']==['pytorch-model-cli','pytorch-model-recovery']
    return path,plan,spec


async def prepare_pipeline_cache(event,admission):
    path,plan,spec=pipeline_cache_plan(admission)
    assert event.config.task.path.name==plan['task_id']
    directory=Path(event.config.trials_dir)/event.trial_name
    files=list(directory.glob('remote-docker-*.jsonl'));assert len(files)==1
    identity=files[0].stem.removeprefix('remote-docker-');record=read_jsonl_first(files[0])
    assert record['identity']==identity and record['project'].startswith('q35selected267-')
    args=['docker','--host',base.native.D['task_engine']['native_endpoint']]
    ids=subprocess.check_output(args+['ps','-q','--filter','label=io.harbor.remote-docker.identity='+identity],text=True,timeout=20).split();assert len(ids)==1
    actual=json.loads(subprocess.check_output(args+['inspect',ids[0]],text=True,timeout=20))[0]
    assert actual['Image']==spec['expected_image_id']
    labels=actual['Config']['Labels'];assert labels['io.harbor.remote-docker.identity']==identity and labels['com.docker.compose.project']==record['project']
    import shlex
    command=['python3',plan['remote_materializer_path'],'--task-id',plan['task_id'],'--identity',identity,'--workspace',record['workspace'],'--receipt-sha256',plan['archive_receipt_sha256']]
    process=await asyncio.create_subprocess_exec('ssh','-p','18449','chenkeyi@127.0.0.1',shlex.join(command),stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE)
    raw_path=directory/'PUBLIC_PIPELINE_CACHE_PREPARATION_RAW_R1.json'
    try:stdout,stderr=await asyncio.wait_for(process.communicate(),timeout=600)
    except TimeoutError:
        if process.returncode is None:process.kill()
        await process.wait()
        write(raw_path,dict(status='UNKNOWN',error='Materializer SSH timed out; remote completion not confirmed',plan_path=str(path),plan_sha256=sha(path),model_generation_calls=0))
        raise RuntimeError('SELECTED267_PIPELINE_CACHE_PREPARATION_UNKNOWN') from None
    stdout_path=directory/'PUBLIC_PIPELINE_CACHE_PREPARATION_R1.stdout.bin';stderr_path=directory/'PUBLIC_PIPELINE_CACHE_PREPARATION_R1.stderr.bin'
    stdout_path.write_bytes(stdout);stderr_path.write_bytes(stderr)
    write(raw_path,dict(return_code=process.returncode,stdout_path=str(stdout_path),stdout_sha256=sha(stdout_path),stderr_path=str(stderr_path),stderr_sha256=sha(stderr_path),plan_path=str(path),plan_sha256=sha(path),model_generation_calls=0))
    assert process.returncode==0,stderr.decode(errors='replace')[-3000:]
    proof=json.loads(stdout)
    assert proof['task_id']==plan['task_id'] and proof['source_sha256']==plan['materializer_sha256'] and proof['archive_sha256']==plan['archive_sha256']
    assert proof['engine_id']==spec['engine_id'] and proof['image_id']==actual['Image'] and proof['identity']==identity
    assert proof['actual_private_cache']['passed'] and proof['actual_private_cache']['actual_private_cache_sha_verified'] and proof['model_generation_calls']==0
    assert proof['official_torch_pin']==proof['cached_torch_wheel_version']=='2.7.0' and proof['official_dependency_versions_not_overridden']
    assert proof['official_task_tests_reward_and_resources_unchanged'] and proof['no_hidden_tests_present_at_copy']
    proof.update(runtime_spec_path=plan['runtime_spec_path'],runtime_spec_sha256=plan['runtime_spec_sha256'],public_pipeline_cache_plan_path=str(path),public_pipeline_cache_plan_sha256=sha(path),raw_receipt_path=str(raw_path),raw_receipt_sha256=sha(raw_path))
    if 'selected_serving_roles_sha256'in admission:proof['selected267_serving_roles_sha256']=admission['selected_serving_roles_sha256']
    write(directory/'PUBLIC_DEPENDENCY_CACHE_PREPARATION_R1.json',proof)


async def main(tag,recovery=False):
    deployment,model,cfg,plan=configuration(tag,recovery)
    prefix='PRE_MODEL_ENV_RECOVERY_'+tag if recovery else 'SELECTED267'
    admission=read(E/'manifests'/(prefix+'_ADMISSION_R1.json'));owner=read(C/'NATIVE_ADVANCE_OWNER.json')
    assert owner==admission['unique_controller_owner']and admission['source_sha256']==sha(Path(__file__))
    if not recovery:
        assert sha(R/'environment-preflight30/environment-profiles-recheck-r2.json')==admission['environment_profiles_sha256']
        pipeline_cache_plan(admission)
    assert(Path('/proc')/str(owner['pid'])/'stat').read_text().rsplit(')',1)[1].split()[19]==owner['start_ticks']
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}));lives=[]
    for replica in model['replicas']:
        with opener.open('http://127.0.0.1:'+str(replica['port'])+'/model_info',timeout=10)as response:live=json.load(response)
        assert live['model_path']==model['model_path']and live['weight_version']==sha(Path(model['model_manifest']));lives.append(live)
    gate=R/'formal-controller18-docker-admission-r5/bin/docker';policy=C/'ENV_PREFLIGHT30_DOCKER_ADMISSION_POLICY_R5.json'
    assert admission['docker_wrapper_path']==str(gate) and admission['docker_policy_path']==str(policy)
    assert admission['docker_wrapper_sha256']==sha(gate)=='e49628bfe9a49d9a2c845fceee53f388bc5d45272ab6136a076bf3f735287a6c'
    assert admission['docker_policy_sha256']==sha(policy)=='a92eab38738cff4245138c6d86087973f0f8e04cddc0297ef5c4113f729b3d35'
    os.environ['PATH']=str(gate.parent)+':'+base.native.D['transport']['private_client_bin']+':'+os.environ['PATH'];os.environ['TMPDIR']=str(R/'tmp');os.environ['OPENAI_API_KEY']='node18-local'
    engine=json.loads(subprocess.check_output(['docker','--host',base.native.D['task_engine']['native_endpoint'],'info','--format','{{json .}}'],text=True,timeout=20))
    assert engine['ID']==base.native.D['task_engine']['id']
    storage=importlib.import_module('run-accepted-common30-disk-recovery18-r2')
    assert sha(Path(storage.__file__))==admission['storage_probe_worker_sha256']=='a554a4c6c95f0411c11e393c81548a493a1f42f9f24ad6a7a700952c1ca36649'
    assert hashlib.sha256(storage.DISK_PROBE.encode()).hexdigest()==admission['storage_probe_code_sha256']=='df9643fa3167d751be597f71e9860c37974230b20da29767110704cfb41ad9f9'
    storage_logs=E/'checks/selected267-storage-gates-r1';storage_logs.mkdir(exist_ok=True)
    async def disk_gate(phase):
        import shlex
        request={'staging_root':base.native.D['task_engine']['staging_root'],'docker_root_dir':engine['DockerRootDir']}
        command=['python3','-c',storage.DISK_PROBE,json.dumps(request)]
        process=await asyncio.create_subprocess_exec('ssh','-p','18449','chenkeyi@127.0.0.1',shlex.join(command),stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE)
        try:stdout,stderr=await asyncio.wait_for(process.communicate(),timeout=45)
        except TimeoutError:
            if process.returncode is None:process.kill()
            await process.wait()
            write(storage_logs/(str(time.time_ns())+'.json'),dict(at_node18=time.time(),phase=phase,passed=False,status='UNKNOWN',error='SSH fsync probe timed out; remote temporary-file cleanup unconfirmed',remote_probe_file_prefix='.q35-disk-recovery-fsync-',new_model_calls=0))
            raise RuntimeError('SELECTED267_STORAGE_GATE_UNKNOWN') from None
        receipt=dict(at_node18=time.time(),phase=phase,ssh_return_code=process.returncode,probe_source_sha256=admission['storage_probe_code_sha256'],stderr=stderr.decode(errors='replace')[-2000:],stdout=stdout.decode(errors='replace'),new_model_calls=0)
        write(storage_logs/(str(time.time_ns())+'.json'),receipt)
        if process.returncode:raise RuntimeError('SELECTED267_STORAGE_GATE_FAILED: '+receipt['stdout'][-3000:]+receipt['stderr'])
        proof=json.loads(stdout)
        assert all(proof[k]for k in ['passed','fsync_file_passed','fsync_directory_passed','readback_passed','probe_file_removed']),'SELECTED267_STORAGE_GATE_INCOMPLETE'
        assert proof['minimum_available_bytes']==64*1024**3 and all(row['available_bytes']>=64*1024**3 and row['available_inodes']>0 for kind in ['before','after']for row in proof[kind]),'SELECTED267_STORAGE_GATE_BELOW_64_GIB'

    assert not(cfg.jobs_dir/cfg.job_name).exists(),'Never recreate existing native Jobs'
    await disk_gate('immediately-before-native-job')
    job=await Job.create(cfg);ordered=configure_trials(job,tag,plan,recovery)
    for index,trial in enumerate(job._trial_configs):
        replica=model['replicas'][index%len(model['replicas'])]
        trial.agent.kwargs['config']['model']['baseUrl']='http://172.17.0.1:'+str(replica['port'])+'/v1'
    job._remaining_trial_configs=job._trial_configs
    async def agent_started(event):
        assert event.result.environment_setup.finished_at and event.result.agent_setup.finished_at
        assert event.result.agent_execution is None and event.result.agent_result is None
        directory=Path(event.config.trials_dir)/event.trial_name
        if not recovery and event.config.task.path.name=='torch-tensor-parallelism':
            binding=admission['public_verifier_cache_binding']
            assert sha(Path(admission['public_verifier_cache_binding_path']))==admission['public_verifier_cache_binding_sha256']
            assert sha(Path(binding['runtime_spec_path']))==binding['runtime_spec_sha256']
            spec=read(Path(binding['runtime_spec_path']));files=list(directory.glob('remote-docker-*.jsonl'));assert len(files)==1
            identity=files[0].stem.removeprefix('remote-docker-');record=read_jsonl_first(files[0])
            args=['docker','--host',base.native.D['task_engine']['native_endpoint']]
            ids=subprocess.check_output(args+['ps','-q','--filter','label=io.harbor.remote-docker.identity='+identity],text=True,timeout=20).split();assert len(ids)==1
            actual=json.loads(subprocess.check_output(args+['inspect',ids[0]],text=True,timeout=20))[0]
            assert actual['Image']==spec['expected_image_id'] and spec['engine_id']==base.native.D['task_engine']['id']
            import shlex
            command=['python3',binding['remote_materializer_path'],'--identity',identity,'--workspace',record['workspace'],'--receipt-sha256',binding['archive_receipt_sha256']]
            process=await asyncio.create_subprocess_exec('ssh','-p','18449','chenkeyi@127.0.0.1',shlex.join(command),stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE)
            stdout,stderr=await asyncio.wait_for(process.communicate(),timeout=600)
            assert process.returncode==0,stderr.decode(errors='replace')[-3000:]
            proof=json.loads(stdout);assert proof['source_sha256']==binding['materializer_sha256'] and proof['archive_sha256']==binding['archive_sha256'] and proof['actual_private_cache']['passed'] and proof['model_generation_calls']==0
            proof.update(runtime_spec_path=binding['runtime_spec_path'],runtime_spec_sha256=binding['runtime_spec_sha256'],selected267_serving_roles_sha256=admission['selected_serving_roles_sha256'])
            write(directory/'PUBLIC_DEPENDENCY_CACHE_PREPARATION_R1.json',proof)
        if not recovery and event.config.task.path.name=='torch-pipeline-parallelism':await prepare_pipeline_cache(event,admission)
        write(directory/'ACTUAL_AGENT_START_SELECTED267_R3.json',dict(at=time.time(),native_trial_uuid=str(event.trial_id),task_id=event.config.task.path.name,model=model['model_id']))
        progress()
    async def trial_started(event):await disk_gate('before-environment:'+event.trial_name)
    job.on_trial_started(trial_started)
    job.on_agent_started(agent_started)
    write(E/'manifests'/(prefix+'_ACTUAL_TRIALS_R1.json'),dict(trials=[t.model_dump(mode='json')for t in job._trial_configs],native_job_id=str(job.id),source_sha256=sha(Path(__file__)),matrix_expected=model['new_trials'],pre_model_continuation=recovery))
    def progress():
        rows=[]
        for path in sorted(job.job_dir.glob('*/result.json')):
            result=read(path);rows.append(dict(trial_name=result['trial_name'],trial_id=result['id'],result_sha256=sha(path),reward=(result.get('verifier_result')or{}).get('rewards'),exception=(result.get('exception_info')or{}).get('exception_type'),agent_execution=result.get('agent_execution'),failure_phase=result.get('failure_phase')))
        write(E/'checks'/(prefix+'_STATUS_R1.json'),dict(at=time.time(),tag=tag,expected=model['new_trials'],terminal=len(rows),rows=rows,native_job_id=str(job.id),pre_model_continuation=recovery,raw_progress_only=True,actual_agent_starts=len(list(job.job_dir.glob('*/ACTUAL_AGENT_START_SELECTED267_R3.json')))))
    async def ended(event):progress()
    job.on_trial_ended(ended);progress();result=await job.run();assert len(result.trial_results)==model['new_trials'];progress()
    write(E/'checks'/(prefix+'_NATIVE_ALL_TERMINAL_R1.json'),dict(at=time.time(),terminal=model['new_trials'],native_job_id=str(job.id)))
    rows=[];byname={x['trial_name']:x for x in ordered}
    for path in sorted(job.job_dir.glob('*/result.json')):
        row=base.inspect_trial(path.parent)
        try:row['behavior']=base.analyze_behavior(path.parent)
        except Exception as error:row['behavior_audit_error']=repr(error)
        item=byname[row['trial_name']];row['repetition']=item['repetition']
        if recovery:row['pre_model_environment_continuation_of']=dict(trial_path=item['original_trial_path'],trial_id=item['original_trial_id'],result_sha256=item['result_sha256'])
        rows.append(row)
    row_path=E/'checks'/(prefix+'_ROWS_R1.jsonl');row_path.write_text(''.join(json.dumps(x)+'\n'for x in rows))
    write(E/'checks'/(prefix+'_AUDIT_COMPLETE_R1.json'),dict(at=time.time(),terminal=len(rows),native_job_id=str(job.id),summary=base.aggregate(rows,model['new_trials']),rows_sha256=sha(row_path),wheel_sha256=deployment['wheel_sha256'],original_results_preserved=True,pre_model_continuation=recovery))
    if not recovery:
        metric=base.metric;write(E/'checks/SELECTED267_COMPARISON_R1.json',dict(complete=True,expected=267,terminal=len(rows),winner=read(R/'checks/WINNER_FROM_COMMON30_SELECTION_R1.json'),overall=base.aggregate(rows,267),rounds={str(i):base.aggregate([r for r in rows if r['repetition']==i],89)for i in [1,2,3]},at_least_one_confirmed_task_fraction=len({r['task_id']for r in rows if metric.scoring_admitted(r)and(r['reward']or{}).get('reward')==1})/89,rows_sha256=sha(row_path),checkpoint_selected_on_30_subset_of89=True,not_an_unselected_holdout_estimate=True))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('tag');parser.add_argument('--recovery',action='store_true');args=parser.parse_args();assert args.recovery or args.tag=='selected267';asyncio.run(main(args.tag,args.recovery))
