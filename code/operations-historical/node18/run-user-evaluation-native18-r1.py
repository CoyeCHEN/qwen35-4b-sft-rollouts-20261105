"""Fixed 30-task native Harbor diagnostics; no formal801 results or retries."""
import argparse
from collections import Counter
import asyncio
import copy
import importlib
import json
import os
from pathlib import Path
import subprocess
import time
import urllib.request

from harbor.job import Job
from harbor.models.job.config import JobConfig

R=Path('/ssd/chenkeyi/qwen35-sft-772-20261101')
E=R/'formal-native-eval-r1'
C=Path('/data/chenkeyi/qwen35-sft-772-20261101/control')
native=importlib.import_module('run-formal-native-tb2118-r2')
inspect_trial=importlib.import_module('audit-native-response-qualification-r1').inspect_trial
analyze_behavior=importlib.import_module('audit_trial_behavior_new772_r3').analyze_behavior
metric=importlib.import_module('compare-formal801-readonly-r8')
aggregate=metric.aggregate
sha=native.sha
read=native.read
write=native.write


def configuration(tag):
    deployment=read(R/'configs/diagnostic150-five-model-r1.json')
    full=tag=='selected267'
    model=read(R/'checks/SELECTED267_MODEL_BINDING_R1.json')if full else read(R/'checks'/('DIAGNOSTIC150_MODEL_BINDING_'+tag+'.json'))
    plan=read(E/'manifests/SELECTED267_BOUND_TRIAL_PLAN_R1.json')if full else read(E/'manifests/DIAGNOSTIC150_TRIAL_PLAN_R1.json')
    assert plan['sampling_manifest_sha256']==deployment['sampling_manifest_sha256']
    expected=[x for x in plan['trials']if x['tag']==tag and not x.get('reuse_existing_trial')]
    assert len(expected)==model['new_trials'] and len({x['task_id']for x in expected})==(89 if full else 30)
    formal=read(E/'manifests/FORMAL_801_TRIAL_PLAN.json')
    source=native.selected_config(formal)
    cfg=JobConfig.model_validate_json(source.read_text())
    selected={Path(x.path).name:x for x in cfg.tasks}
    cfg.tasks=[selected[task]for task in dict.fromkeys(x['task_id']for x in expected)]
    agent=cfg.agents[model['source_agent_index']].model_copy(deep=True)
    agent.model_name='openai/'+model['model_id']
    agent.kwargs['config']['model'].update(id=model['model_id'],name=model['display_name'],
        baseUrl='http://172.17.0.1:'+str(model['replicas'][0]['port'])+'/v1')
    assert agent.kwargs['wheel_sha256']==deployment['wheel_sha256']
    assert sha(Path(agent.kwargs['wheel_path']))==deployment['wheel_sha256']
    cfg.agents=[agent];cfg.n_attempts=3 if full else 1;cfg.n_concurrent_trials=model['concurrency']
    cfg.job_name=model['job_name'];cfg.jobs_dir=E/'jobs';cfg.retry.max_retries=0
    cfg.environment.kwargs.update(endpoint=native.D['task_engine']['native_endpoint'],
        transfer_timeout_sec=native.D['task_engine']['transfer_timeout_sec'])
    return deployment,model,cfg,dict(trials=expected)


async def main(tag):
    deployment,model,cfg,plan=configuration(tag)
    admission=read(E/'manifests/SELECTED267_ADMISSION_R1.json')if tag=='selected267'else read(E/'manifests'/('DIAGNOSTIC150_ADMISSION_'+tag+'_R1.json'))
    owner=read(C/'NATIVE_ADVANCE_OWNER.json')
    assert owner==admission['unique_controller_owner']
    assert(Path('/proc')/str(owner['pid'])/'stat').read_text().rsplit(')',1)[1].split()[19]==owner['start_ticks']
    assert admission['source_sha256']==sha(Path(__file__))
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
    lives=[]
    for replica in model['replicas']:
        with opener.open('http://127.0.0.1:'+str(replica['port'])+'/model_info',timeout=10)as response:live=json.loads(response.read())
        assert live['model_path']==model['model_path']and live['weight_version']==sha(Path(model['model_manifest']))
        lives.append(live)
    live=lives[0]
    os.environ['PATH']=native.D['transport']['private_client_bin']+':'+os.environ['PATH']
    os.environ['TMPDIR']=str(R/'tmp');os.environ['OPENAI_API_KEY']='node18-local'
    assert subprocess.check_output(['docker','--host',native.D['task_engine']['native_endpoint'],
        'info','--format','{{.ID}}'],text=True,timeout=20).strip()==native.D['task_engine']['id']
    assert not(cfg.jobs_dir/cfg.job_name).exists(),'Never recreate or retry an existing diagnostic Job'
    job=await Job.create(cfg);assert len(job._trial_configs)==model['new_trials']
    by_identity={(x['task_id'],x['repetition']):x for x in plan['trials']};seen=Counter();ordered=[]
    for trial in job._trial_configs:
        task=trial.task.path.name;seen[task]+=1;ordered.append(by_identity[(task,seen[task])])
    plan['trials']=ordered
    effective=native.apply_trial_overrides(job._trial_configs,plan,
        read(E/'configs/environment-profiles-agent-deps-r2.json'),namespace='q35gpu78'+tag.replace('-',''))
    for index,trial in enumerate(job._trial_configs):
        replica=model['replicas'][index%len(model['replicas'])]
        trial.agent.kwargs['config']['model']['baseUrl']='http://172.17.0.1:'+str(replica['port'])+'/v1'
    effective=[trial.model_dump(mode='json')for trial in job._trial_configs]
    job._remaining_trial_configs=job._trial_configs
    write(E/'manifests'/('DIAGNOSTIC30_ACTUAL_TRIALS_'+tag+'.json'),dict(trials=effective,
        native_job_id=str(job.id),formal_801_excluded=True,source_sha256=sha(Path(__file__)),matrix_expected=30))
    status=E/'checks/SELECTED267_STATUS_R1.json'if tag=='selected267'else E/'checks'/('DIAGNOSTIC30_STATUS_'+tag+'.json')
    def raw_progress():
        rows=[]
        for path in sorted(job.job_dir.glob('*/result.json')):
            result=read(path)
            rows.append(dict(trial_name=result['trial_name'],trial_id=result['id'],result_sha256=sha(path),
                reward=(result.get('verifier_result')or{}).get('rewards'),
                verifier_return_code=(result.get('verifier_result')or{}).get('return_code'),
                exception=(result.get('exception_info')or{}).get('exception_type'),
                infrastructure_errors=result.get('infrastructure_errors'),recorder_audit_pending=True))
        write(status,dict(at=time.time(),tag=tag,expected=model['new_trials'],terminal=len(rows),native_job_id=str(job.id),
            model_path=model['model_path'],weight_version=live['weight_version'],rows=rows,
            formal_801_excluded=True,normal_qualified_success_not_inferred_from_raw_reward=True))
    async def ended(event):
        raw_progress()
    job.on_trial_ended(ended);raw_progress()
    result=await job.run();assert len(result.trial_results)==model['new_trials'];raw_progress()
    write((E/'checks/SELECTED267_NATIVE_ALL_TERMINAL_R1.json'if tag=='selected267'else E/'checks'/('DIAGNOSTIC30_NATIVE_ALL_TERMINAL_'+tag+'.json')),dict(at=time.time(),tag=tag,terminal=model['new_trials'],
        native_job_id=str(result.id),formal_801_excluded=True,recorder_audit_pending=True))
    rows=[]
    for path in sorted(job.job_dir.glob('*/result.json')):
        row=inspect_trial(path.parent)
        try:row['behavior']=analyze_behavior(path.parent)
        except Exception as error:row['behavior_audit_error']=repr(error)
        identity=by_identity[(row['task_id'],next(x['repetition']for x in plan['trials']if x['trial_name']==row['trial_name']))]
        row['repetition']=identity['repetition'];rows.append(row)
    row_path=E/'checks/SELECTED267_ROWS_R1.jsonl'if tag=='selected267'else E/'checks'/('DIAGNOSTIC30_ROWS_'+tag+'.jsonl')
    row_path.write_text(''.join(json.dumps(row)+'\n'for row in rows))
    write((E/'checks/SELECTED267_AUDIT_COMPLETE_R1.json'if tag=='selected267'else E/'checks'/('DIAGNOSTIC30_AUDIT_COMPLETE_'+tag+'.json')),dict(at=time.time(),tag=tag,terminal=model['new_trials'],
        native_job_id=str(result.id),summary=aggregate(rows,model['new_trials']),rows_sha256=sha(row_path),
        wheel_sha256=deployment['wheel_sha256'],formal_801_excluded=True,
        checkpoint_selected_only_by_user_common30_rule=tag=='selected267',original_results_recorders_and_rewards_preserved=True))
    if tag=='selected267':
        report=dict(complete=True,expected=267,terminal=len(rows),winner=read(R/'checks/WINNER_FROM_COMMON30_SELECTION_R1.json'),
            overall=aggregate(rows,267),rounds={str(i):aggregate([x for x in rows if x['repetition']==i],89)for i in [1,2,3]},
            at_least_one_confirmed_task_fraction=len({x['task_id']for x in rows if metric.scoring_admitted(x)and(x['reward']or{}).get('reward')==1})/89,
            rows_sha256=sha(row_path),original_results_and_rewards_unmodified=True,
            checkpoint_selected_on_30_subset_of89=True,not_an_unselected_holdout_estimate=True)
        write(E/'checks/SELECTED267_COMPARISON_R1.json',report)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('tag',choices=['new-m2-e1-diag','new-m2-e5-diag','selected267'])
    args=parser.parse_args();asyncio.run(main(args.tag))
