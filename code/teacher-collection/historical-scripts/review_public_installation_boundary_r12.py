"""Reuse completed native17 checks for an explicitly incomplete software setup.

No Task, official verifier, image or original Result is modified. This review
does not run a teacher and cannot turn a teacher failure into a success.
"""
import datetime
import hashlib
import json
from pathlib import Path

import collection_readiness_r7 as n
import run_collection_stream_r4 as c
from collection_selection_r7 import active_rows

IDENT='system-administration_20260414_080620_009'


def main():
    row=next(x for x in active_rows(c.attempt_counts()) if x['task_id']==IDENT)
    admitted=n.prepare_identity(row)
    source=Path(row['source_path'])
    instruction=(source/'instruction.md').read_text()
    dockerfile=(source/'environment/Dockerfile').read_text()
    if 'logrotate configuration works without errors' not in instruction:
        raise ValueError('Public software installation assignment changed')
    if '# Install minimal dependencies - solver needs to install additional tools' not in dockerfile:
        raise ValueError('Original explicit solver-installation boundary changed')
    prior=n.D/'environment-failures'/(IDENT+'.json')
    if json.loads(prior.read_text())['reason']!='Original verifier executable/dependency failed to start':
        raise ValueError('Unexpected original rejection')
    native={}
    for p in (n.R/'stream/collection-r4/dispatches').glob('*/dispatch.json'):
        value=json.loads(p.read_text())
        if value.get('task_id')!=IDENT or value['kind'] not in ['install','nop']:continue
        config_file=p.parent/'trial-config.json';config=json.loads(config_file.read_text())
        if config['environment']['kwargs']['project_namespace']!=n.DEPLOYMENT['environment']['kwargs']['project_namespace']:continue
        if n.sha(config_file)!=value['config_sha256']:raise ValueError('Native configuration changed')
        if value['kind'] in native:raise ValueError('Ambiguous current17 native check')
        if config['environment']['kwargs']!=n.native_config(admitted,value['kind']).environment.kwargs:
            raise ValueError('Native check belongs to a different runtime')
        trial=n.R/'stream/collection-r4/trials'/value['trial_name']
        result=json.loads((trial/'result.json').read_text())
        if result.get('exception_info') or result.get('infrastructure_errors') or not result.get('finished_at'):
            raise ValueError('Infrastructure failure cannot be reclassified')
        if value['kind']=='nop':
            if not (result.get('verifier') or {}).get('finished_at') or (result.get('verifier_result') or {}).get('rewards',{}).get('reward')!=0:
                raise ValueError('Original NOP verifier did not complete with zero')
            logs=list((trial/'verifier').glob('test-*.txt'))
            text='\n'.join(q.read_text(errors='replace') for q in logs)
            if 'rsync: command not found' not in text or "No such file or directory: 'logrotate'" not in text:
                raise ValueError('Actual failure differs from the public installation boundary')
            if '7 failed' not in text or 'ERROR collecting' in text or 'No module named pytest' in text:
                raise ValueError('Official test execution was not established')
        native[value['kind']]=dict(trial=str(trial),result_sha256=n.sha(trial/'result.json'))
    if set(native)!={'install','nop'}:raise ValueError('Both original native checks are required')
    for artifact in admitted['verifier_files']:
        if n.sha(Path(admitted['prepared_task_path'])/artifact['path'])!=artifact['sha256']:
            raise ValueError('Official verifier changed')
    review_file=n.R/'checks/native-environment-reviews-r10'/(IDENT+'.json')
    reason='The public task asks to repair the archival system and logrotate; its original Dockerfile explicitly requires the solver to install additional tools. Missing rsync/logrotate in this untouched NOP workspace is part of that unsolved installation state. Official pytest executed all seven tests and completed with genuine zero; no verifier dependency or test was installed or altered by this review.'
    review=dict(task_id=IDENT,pool='calibforge',status='ENV_READY',reviewed_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        missing_modules=[],prior_outcome=str(prior),prior_outcome_sha256=n.sha(prior),native_results=native,
        original_verifier_logs=[dict(path=str(q),sha256=n.sha(q)) for q in logs],
        public_instruction=str(source/'instruction.md'),public_instruction_sha256=n.sha(source/'instruction.md'),
        original_dockerfile=str(source/'environment/Dockerfile'),original_dockerfile_sha256=n.sha(source/'environment/Dockerfile'),
        review_reason=reason,controller_admission='Reuse only the completed original native17 checks; normal teacher budget, verifier, qualification and split rules remain in force',
        model_calls=0,raw_failure_preserved=True,task_or_test_modifications=0,teacher_success_not_implied=True)
    n.freeze(review_file,review)
    ready=dict(task_id=IDENT,pool='calibforge',status='ENV_READY',admitted_task=admitted,
        engine_id=n.NODE['engine_id'],deployment_config_sha256=n.CONFIG_SHA,
        placement=admitted['deployment_assignment'],placement_sha256=admitted['deployment_assignment_sha256'],
        nop_reward=0,teacher_success_not_implied=True,raw_outcome=str(review_file),raw_outcome_sha256=n.sha(review_file))
    for kind in ['install','nop']:
        ready['native_'+kind+'_trial']=native[kind]['trial'];ready[kind+'_result_sha256']=native[kind]['result_sha256']
    digest=hashlib.sha256(json.dumps(ready,sort_keys=True).encode()).hexdigest()
    destination=n.D/'ready-revisions'/IDENT/(digest+'.json');n.freeze(destination,ready)
    print(json.dumps(dict(task_id=IDENT,status='ENV_READY',review=str(review_file),ready=str(destination),model_calls=0)))


if __name__=='__main__':main()
