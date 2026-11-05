"""Freeze three factual zero-reward reviews; never modify a Task or Reward."""
import hashlib
import json
from pathlib import Path

R=Path('/home/chenkeyi/.local/share/harbor-rsi/qwen35-new-cf500-tmax500-20261029')
SPECS={
 'd1de9197-8437-4640-8eca-9c5b9a15773d':dict(
  task_id='data-science_20260415_182321_002',result_sha256='df9d14ecfa448dbf854d246860d6a831dedba6fae5beee191f0cd898c18fda84',
  classification='OFFICIAL_VERIFIER_SUBMITTED_PROGRAM_DEPENDENCY_FAILURE',module='dask',
  summary={'tests':6,'passed':5,'failed':1},failed_tests=['test_outputs.py::test_pipeline_runs_successfully'],
  failure_scope='The collected official test executes the submitted /app/pipeline.py; its subprocess cannot import dask. Five output checks passed.',
  scoring_interpretation='Official zero for submitted-program execution/portability; not a claim about aggregation accuracy or an outer pytest collection failure.'),
 '715898a2-43ef-44ef-875b-beb27d9d0c8a':dict(
  task_id='model-training_20260604_002443_004',result_sha256='e9756b1ae36cce67b6757bbd9068c56e4eb7b9fb8ff784616ac7b51586d9e765',
  classification='OFFICIAL_VERIFIER_ARTIFACT_DEPENDENCY_INCOMPATIBILITY',module='lightgbm',
  summary={'tests':7,'passed':4,'failed':3},failed_tests=['test_outputs.py::test_model_loadable','test_outputs.py::test_auc_on_private_test','test_outputs.py::test_brier_on_private_test'],
  failure_scope='Official tests were collected. pickle.load of the submitted model requires lightgbm, absent from the official isolated verifier dependency set.',
  scoring_interpretation='Preserve official zero as artifact/verifier dependency incompatibility. AUC and Brier were not evaluated; do not report predictive-quality failure or infer a native infrastructure exception.'),
 '48257c3d-7796-4510-90a3-08905243f135':dict(
  task_id='task_004900_ebeb969a',result_sha256='bb90383f39607f76f91cc21dedcd3b9600bd983ea9ae25354044eb9022b54ead',
  classification='OFFICIAL_VERIFIER_NESTED_TASK_TEST_IMPORT_FAILURE',module='src',
  summary={'tests':3,'passed':2,'failed':1},failed_tests=['test_final_state.py::test_pipeline_tests_pass'],
  failure_scope='All three outer official tests were collected. The assigned repository pytest command fails to import its provided src package; the outer test reports an assertion failure.',
  scoring_interpretation='Official zero for the required task-local pytest invocation. Nested collection error is recorded separately from outer verifier setup/collection failure; no numerical-precision conclusion is inferred.')
}


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def freeze(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('x') as f:json.dump(value,f,indent=2)


def main():
    rows={}
    for pool in ['CALIBFORGE','TMAX']:
        for line in (R/'indexes'/(pool+'_FAILURE_OR_PENDING_INDEX.jsonl')).open():
            row=json.loads(line)
            if row['trial_id'] in SPECS:rows[row['trial_id']]=row
    if set(rows)!=set(SPECS):raise ValueError('Review source trial set changed')
    references=[]
    for ident,spec in SPECS.items():
        row=rows[ident];result=Path(row['result_path']);native=json.loads(result.read_text());trial=result.parent
        if row['task_id']!=spec['task_id'] or row['classification']!='OFFICIAL_REWARD_ZERO_REQUIRES_VERIFIER_LOG_CLASSIFICATION':raise ValueError('Review identity/classification changed')
        if sha(result)!=spec['result_sha256'] or row['result_sha256']!=spec['result_sha256']:raise ValueError('Original Result bytes changed')
        if row['raw_reward']!=0 or not row['verifier_actually_completed'] or native.get('exception_info') or native.get('infrastructure_errors'):raise ValueError('Not the measured completed official zero')
        if (trial/'verifier/reward.txt').read_text().strip() not in ['0','0.0']:raise ValueError('Original reward file is not zero')
        log=trial/'verifier/test-stdout.txt';text=log.read_text()
        if "No module named '"+spec['module']+"'" not in text:raise ValueError('Missing dependency observation changed')
        ctrf=trial/'verifier/ctrf.json'
        if ctrf.exists():
            data=json.loads(ctrf.read_text())['results'];summary=data['summary']
            if any(summary[k]!=v for k,v in spec['summary'].items()) or summary.get('other',0) or summary.get('pending',0):raise ValueError('Official CTRF summary changed')
            failed=sorted(x['name'] for x in data['tests'] if x['status']=='failed')
            if failed!=sorted(spec['failed_tests']):raise ValueError('Official failed test identities changed')
        else:
            if spec['module']!='src' or 'collected 3 items' not in text or '1 failed, 2 passed' not in text:raise ValueError('Nested task-test summary changed')
            if 'test_bad_commit_hash PASSED' not in text or 'test_mre_script PASSED' not in text:raise ValueError('Outer task checks changed')
        task=Path(native['config']['task']['path'])
        value=dict(trial_id=ident,pool=row['pool'],task_id=spec['task_id'],
            previous_classification=row['classification'],**{k:v for k,v in spec.items() if k not in ['task_id','result_sha256']},
            result_path=str(result),result_sha256=spec['result_sha256'],
            verifier_stdout=str(log),verifier_stdout_sha256=sha(log),
            reward_path=str(trial/'verifier/reward.txt'),reward_sha256=sha(trial/'verifier/reward.txt'),
            official_verifier_members={str(p.relative_to(task)):sha(p) for p in sorted((task/'tests').rglob('*')) if p.is_file()},
            source_instruction_sha256=sha(task/'instruction.md'),
            ctrf_sha256=sha(ctrf) if ctrf.exists() else None,
            official_reward=0,official_reward_modified=False,teacher_success=False,
            teacher_prompt_or_environment_changed=False,source_sha256=sha(Path(__file__)))
        path=R/'checks/completed-verifier-zero-reviews-r113'/(ident+'.json');freeze(path,value)
        references.append(dict(trial_id=ident,path=str(path),sha256=sha(path)))
    path=R/'checks/COMPLETED_VERIFIER_ZERO_REVIEWS_R113.json'
    freeze(path,dict(reviews=references,model_calls=0,task_or_reward_changes=0,
        budget_or_attempt_counter_changes=0,scope='Existing completed official zeroes only; no new reward or success admission. Interpret dependency incompatibilities separately from numerical task quality.'))
    print(json.dumps(dict(reviewed=len(references),manifest=str(path),sha256=sha(path))))


if __name__=='__main__':main()
