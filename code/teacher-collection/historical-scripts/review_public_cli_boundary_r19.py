"""Review completed native17 checks for the public techcorp packaging goal.

No Task, official verifier, image or original Result is modified. This review
does not run a teacher and cannot turn a teacher failure into a success.
"""
import datetime
import hashlib
import json
from pathlib import Path

import collection_readiness_r7 as n
from collection_attempts_r8 import attempt_counts
from collection_selection_r7 import active_rows

IDENT='software-engineering_20260419_182351_009'


def main():
    if attempt_counts().get(IDENT,0):raise ValueError('Review only a never-attempted Task')
    if n.blocking_review(IDENT):raise ValueError('A trusted negative boundary review remains')
    row=next(x for x in active_rows(attempt_counts()) if x['task_id']==IDENT)
    admitted=n.prepare_identity(row)
    source=Path(row['source_path'])
    instruction=(source/'instruction.md').read_text()
    dockerfile=(source/'environment/Dockerfile').read_text()
    if 'all CLI commands available' not in instruction:
        raise ValueError('Public software installation assignment changed')
    if '.venv/bin/pip install -e ./techcorp-cli' not in dockerfile:
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
        if Path(config['task']['path'])!=Path(admitted['prepared_task_path']):raise ValueError('Native check used another prepared Task')
        trial=n.R/'stream/collection-r4/trials'/value['trial_name']
        result=json.loads((trial/'result.json').read_text())
        if result.get('exception_info') or result.get('infrastructure_errors') or not result.get('finished_at'):
            raise ValueError('Infrastructure failure cannot be reclassified')
        if value['kind']=='nop':
            if not (result.get('verifier') or {}).get('finished_at') or (result.get('verifier_result') or {}).get('rewards',{}).get('reward')!=0:
                raise ValueError('Original NOP verifier did not complete with zero')
            logs=list((trial/'verifier').glob('test-*.txt'))
            text='\n'.join(q.read_text(errors='replace') for q in logs)
            if 'techcorp command not found in PATH' not in text or 'Missing [project.scripts] section in techcorp-cli/pyproject.toml' not in text:
                raise ValueError('Actual failure differs from the public installation boundary')
            if '6 failed, 1 passed' not in text or 'PASSED ../tests/test_outputs.py::test_namespace_packages_importable' not in text or 'ERROR collecting' in text or 'No module named pytest' in text:
                raise ValueError('Official test execution was not established')
        native[value['kind']]=dict(trial=str(trial),result_sha256=n.sha(trial/'result.json'))
    if set(native)!={'install','nop'}:raise ValueError('Both original native checks are required')
    for artifact in admitted['verifier_files']:
        if n.sha(Path(admitted['prepared_task_path'])/artifact['path'])!=artifact['sha256']:
            raise ValueError('Official verifier changed')
    if attempt_counts().get(IDENT,0):raise ValueError('Task was attempted during review')
    review_file=n.R/'checks/native-environment-reviews-r10'/(IDENT+'.json')
    reason='The public assignment explicitly requires repairing the techcorp namespace packaging configuration and making all CLI commands available. The missing techcorp executable is precisely its unconfigured public project.scripts entry point. All seven official verifier tests ran: the namespace import test passed and the six CLI/configuration assertions failed. The untouched nested project integration suite also ran all20 tests. No executable, packaging file, official test, image, or reward is modified by this review.'
    review=dict(task_id=IDENT,pool='calibforge',status='ENV_READY',reviewed_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        review_source=str(Path(__file__)),review_source_sha256=n.sha(Path(__file__)),missing_modules=[],prior_outcome=str(prior),prior_outcome_sha256=n.sha(prior),native_results=native,
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
