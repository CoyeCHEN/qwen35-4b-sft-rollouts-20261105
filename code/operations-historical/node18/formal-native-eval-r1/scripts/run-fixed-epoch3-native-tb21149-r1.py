"""Nine preregistered native Harbor diagnostic Trials, separate from formal n3."""
import argparse
import asyncio
import copy
import importlib
import hashlib
import json
import os
from pathlib import Path
import urllib.request
from harbor.job import Job
from harbor.models.job.config import JobConfig
_audit=importlib.import_module('audit-native-context-accounting-r2')
inspect_trial,summary=_audit.inspect_trial,_audit.summary
apply_trial_overrides=importlib.import_module('run-formal-native-tb21149-r6').apply_trial_overrides

B=Path('/home/chenkeyi/.local/share/harbor-rsi')
R=B/'qwen35-new772-tb21-20261101'


async def main(stage):
    prereg=json.loads((R/'manifests/EPOCH3_DIAGNOSTIC_PREREGISTRATION.json').read_text())
    admission=json.loads((R/'manifests'/('EPOCH3_FIXED_SERVING_ADMISSION_'+stage+'.json')).read_text())
    assert hashlib.sha256((R/'manifests/EPOCH3_DIAGNOSTIC_PREREGISTRATION.json').read_bytes()).hexdigest()==admission['preregistration_sha256']
    assert admission['epoch']==3 and admission['model_is_final_epoch5'] is False
    registered=R/'manifests/REPAIRED_EPOCH3_18_TRIAL_PLAN_R1.json'
    assert hashlib.sha256(registered.read_bytes()).hexdigest()==admission['repaired_epoch3_plan_sha256']
    registered_trials=[t for t in json.loads(registered.read_text())['trials']if t['stage']==stage]
    cfg=json.loads((R/'configs/formal-native-job-r2.json').read_text())
    e2e=json.loads((R/'checks/CONTEXT_RECOVERY_FULL_WHEEL_E2E_ACCEPTANCE_R1.json').read_text())
    assert e2e['passed']and len(e2e['cases'])==6
    assert e2e['wheel_sha256']==admission['wheel_sha256']=='1d27eef1ca6696275f306d8c653f7a266a4c7aea7321f0d47fd01b739c27fa18'
    ready=json.loads((R/'checks/NEW11_INSTALL_PREFLIGHT_STATUS_R1.json').read_text())
    assert set(prereg['tasks'])<=set(ready['ready_task_ids'])
    agent=copy.deepcopy(cfg['agents'][1 if stage=='new-m1'else 2])
    model_id='qwen35-new772-'+stage+'-epoch3-fixed'
    agent['model_name']='openai/'+model_id
    agent['kwargs']['config']['model'].update(id=model_id,name='Qwen3.5-4B '+stage+' epoch3 diagnostic',baseUrl='http://172.17.0.1:18303/v1')
    tasks={Path(t['path']).name:t for t in cfg['tasks']}
    selected=[tasks[name]for name in prereg['tasks']];assert len(selected)==9
    cfg.update(job_name='qwen35-new772-'+stage+'-epoch3-fixed-diagnostic',n_attempts=1,n_concurrent_trials=2,
        tasks=selected,agents=[agent])
    plan=dict(trials=[dict(trial_name=Path(t['path']).name+'__'+stage+'-e3-fixed-r1',
        task_path=t['path'],model_name=agent['model_name'],agent_override_timeout_sec=max(10800,
        __import__('tomllib').loads((Path(t['path'])/'task.toml').read_text())['agent']['timeout_sec']))for t in selected])
    os.environ['SSH_AUTH_SOCK']=str(B/'near-r3-20261015/auth.sock');os.environ['OPENAI_API_KEY']='node18-local'
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open('http://172.17.0.1:18303/model_info',timeout=15)as response:info=json.loads(response.read())
    assert info['model_path']==admission['model_path'] and info['weight_version']==admission['weight_version']
    assert info.get('has_image_understanding')
    assert not (R/'jobs'/cfg['job_name']).exists(),'Preserve an existing diagnostic Job; do not repeat Trials'
    job=await Job.create(JobConfig.model_validate(cfg));assert len(job._trial_configs)==9
    profiles=json.loads((R/'configs/environment-profiles-agent-deps-r2.json').read_text())
    effective=apply_trial_overrides(job._trial_configs,plan,profiles,namespace='q35new772e3fixed'+stage.replace('-',''))
    job._remaining_trial_configs=job._trial_configs
    assert [t['trial_name']for t in effective]==[t['trial_name']for t in registered_trials]
    assert [t['task']['path']for t in effective]==[t['task_path']for t in registered_trials]
    (R/'manifests'/('EPOCH3_FIXED_ACTUAL_TRIALS_'+stage+'.json')).write_text(json.dumps(dict(trials=effective,
        formal_801_excluded=True,training_epoch4_and5_must_continue=True),indent=2)+'\n')
    rows=[];audit_lock=asyncio.Lock()
    async def ended(event):
        async with audit_lock:
            try:
                row=await asyncio.to_thread(inspect_trial,job.job_dir/event.trial_name)
                rows.append(row)
                (R/'checks'/('EPOCH3_FIXED_DIAGNOSTIC_ROWS_'+stage+'.jsonl')).write_text(''.join(json.dumps(r)+'\n'for r in rows))
                (R/'checks'/('EPOCH3_FIXED_DIAGNOSTIC_STATUS_'+stage+'.json')).write_text(json.dumps(summary(rows,9),indent=2)+'\n')
            except Exception as error:
                with(R/'logs/epoch3-fixed-audit-errors.jsonl').open('a')as stream:stream.write(json.dumps(dict(stage=stage,error=repr(error)))+'\n')
    job.on_trial_ended(ended)
    result=await job.run()
    assert len(result.trial_results)==9
    (R/'checks'/('EPOCH3_FIXED_DIAGNOSTIC_ALL_TERMINAL_'+stage+'.json')).write_text(json.dumps(dict(
        terminal=9,stage=stage,native_job_id=str(result.id),excluded_from_801=True,
        model_selection_or_recipe_changed=False,wheel_sha256=e2e['wheel_sha256']),indent=2)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('stage',choices=['new-m1','new-m2']);args=p.parse_args()
    asyncio.run(main(args.stage))
