"""Native disjoint pre-model setup continuation, or selected-model 267 campaign."""
import argparse,asyncio,importlib,json,os,subprocess,time,urllib.request
from collections import Counter
from pathlib import Path
from harbor.job import Job
from harbor.models.job.config import JobConfig
from harbor.models.trial.config import TrialConfig
base=importlib.import_module('run-user-evaluation-native18-r1')
prep=importlib.import_module('evaluation-preparation18-r1')
R=base.R;E=base.E;C=base.C;read=base.read;sha=base.sha;write=base.write


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
        base.native.apply_trial_overrides(job._trial_configs,dict(trials=ordered),read(E/'configs/environment-profiles-agent-deps-r2.json'),namespace='q35selected267')
    for trial,item in zip(job._trial_configs,ordered):
        prep.append_ipam(trial,tag,item['task_id'],item['repetition'])
    return ordered


async def main(tag,recovery=False):
    deployment,model,cfg,plan=configuration(tag,recovery)
    prefix='PRE_MODEL_ENV_RECOVERY_'+tag if recovery else 'SELECTED267'
    admission=read(E/'manifests'/(prefix+'_ADMISSION_R1.json'));owner=read(C/'NATIVE_ADVANCE_OWNER.json')
    assert owner==admission['unique_controller_owner']and admission['source_sha256']==sha(Path(__file__))
    assert(Path('/proc')/str(owner['pid'])/'stat').read_text().rsplit(')',1)[1].split()[19]==owner['start_ticks']
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}));lives=[]
    for replica in model['replicas']:
        with opener.open('http://127.0.0.1:'+str(replica['port'])+'/model_info',timeout=10)as response:live=json.load(response)
        assert live['model_path']==model['model_path']and live['weight_version']==sha(Path(model['model_manifest']));lives.append(live)
    os.environ['PATH']=base.native.D['transport']['private_client_bin']+':'+os.environ['PATH'];os.environ['TMPDIR']=str(R/'tmp');os.environ['OPENAI_API_KEY']='node18-local'
    assert subprocess.check_output(['docker','--host',base.native.D['task_engine']['native_endpoint'],'info','--format','{{.ID}}'],text=True,timeout=20).strip()==base.native.D['task_engine']['id']
    assert not(cfg.jobs_dir/cfg.job_name).exists(),'Never recreate existing native Jobs'
    job=await Job.create(cfg);ordered=configure_trials(job,tag,plan,recovery)
    for index,trial in enumerate(job._trial_configs):
        replica=model['replicas'][index%len(model['replicas'])]
        trial.agent.kwargs['config']['model']['baseUrl']='http://172.17.0.1:'+str(replica['port'])+'/v1'
    job._remaining_trial_configs=job._trial_configs
    write(E/'manifests'/(prefix+'_ACTUAL_TRIALS_R1.json'),dict(trials=[t.model_dump(mode='json')for t in job._trial_configs],native_job_id=str(job.id),source_sha256=sha(Path(__file__)),matrix_expected=model['new_trials'],pre_model_continuation=recovery))
    def progress():
        rows=[]
        for path in sorted(job.job_dir.glob('*/result.json')):
            result=read(path);rows.append(dict(trial_name=result['trial_name'],trial_id=result['id'],result_sha256=sha(path),reward=(result.get('verifier_result')or{}).get('rewards'),exception=(result.get('exception_info')or{}).get('exception_type'),agent_execution=result.get('agent_execution'),failure_phase=result.get('failure_phase')))
        write(E/'checks'/(prefix+'_STATUS_R1.json'),dict(at=time.time(),tag=tag,expected=model['new_trials'],terminal=len(rows),rows=rows,native_job_id=str(job.id),pre_model_continuation=recovery,raw_progress_only=True))
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
