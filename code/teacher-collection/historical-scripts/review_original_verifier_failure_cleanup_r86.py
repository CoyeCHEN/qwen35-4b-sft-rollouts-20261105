"""Allow the unchanged selected Task with a documented original NOP limitation.

The original failed tests leave a non-daemon SMTP thread alive. Keep all real
timeouts and absent Rewards; actual teacher success still requires completed
official reward1 and every Recorder/Agent/Qwen qualification check.
"""
import ast
import hashlib
import json
from pathlib import Path
import re

import collection_readiness_r11 as n
from collection_attempts_r8 import attempt_counts
from collection_selection_r7 import active_rows

IDENT='task_008794_911eb529'


def read(p):return json.loads(Path(p).read_text())


def main():
    if attempt_counts().get(IDENT,0) or n.blocking_review(IDENT):raise ValueError('Only the original unattempted and unblocked Task may be reviewed')
    row=next(x for x in active_rows(attempt_counts()) if x['task_id']==IDENT);admitted=n.prepare_identity(row)
    task=Path(admitted['prepared_task_path']);instruction=task/'instruction.md'
    if n.sha(instruction)!=row['instruction_sha256'] or not all(text in instruction.read_text() for text in ['/home/user/deploy.git','pre-receive','SMTP']):raise ValueError('Public assignment changed')
    source=n.R/'sources/tmax/original-tasks'/IDENT/'test_final_state.py'
    if n.sha(source)!=n.sha(task/'tests/test_final_state.py'):raise ValueError('Original official test source changed')
    tree=ast.parse(source.read_bytes());goal=next(x for x in tree.body if isinstance(x,ast.FunctionDef) and x.name=='test_git_hook_functionality')
    calls=[x for x in ast.walk(goal) if isinstance(x,ast.Call)]
    thread=next(x for x in calls if ast.unparse(x.func)=='threading.Thread')
    if any(k.arg=='daemon' for k in thread.keywords) or any(isinstance(x,ast.Assign) and any(isinstance(y,ast.Attribute) and y.attr=='daemon' for y in x.targets) for x in ast.walk(goal)):
        raise ValueError('The observed non-daemon cleanup boundary changed')
    cleanup=next(x.lineno for x in calls if ast.unparse(x.func)=='smtp_stop.set')
    clone_assert=next(x.lineno for x in ast.walk(goal) if isinstance(x,ast.Assert) and isinstance(x.msg,ast.Constant) and x.msg.value=='Failed to clone deploy.git.')
    if clone_assert>=cleanup or any(isinstance(x,ast.Try) and x.finalbody for x in goal.body):raise ValueError('Failure-path cleanup is no longer unreachable')
    root=n.R/'stream/official-test-failure-cleanup17-r79';directory=root/'probes'/IDENT
    plan=read(root/'PLAN.json');probe=read(directory/'PROBE.json')
    if plan['source_sha256']!=n.sha(n.R/'scripts/probe_official_test_failure_cleanup17_r79.py') or plan['engine_id']!=n.NODE['engine_id']:
        raise ValueError('Frozen diagnostic source/Engine changed')
    expected={'trusted_official_test_collection':0,'unchanged_test_failure_cleanup_diagnostic':124,'no_reward_written':0}
    if {x['name']:x['return_code'] for x in probe['steps']}!=expected or not probe['native_cleanup_completed'] or not probe['official_test_bodies_executed'] or probe['official_verifier_runs']!=0:
        raise ValueError('Trusted diagnostic did not finish with its recorded boundaries')
    collect=directory/'trusted_official_test_collection-stdout.txt'
    stdout=directory/'unchanged_test_failure_cleanup_diagnostic-stdout.txt';stderr=directory/'unchanged_test_failure_cleanup_diagnostic-stderr.txt'
    if not re.search(r'^5 tests collected in [\d.]+s$',collect.read_text(),re.M):raise ValueError('Original tests did not load')
    if not re.search(r'^5 failed in [\d.]+s$',stdout.read_text(),re.M) or 'Failed to clone deploy.git.' not in stdout.read_text():raise ValueError('The original unsolved public repository did not cause the observed failures')
    if not all(text in stderr.read_text() for text in ['mock_smtp_server','socket.py','_shutdown']):raise ValueError('Actual worker/main shutdown stacks do not establish the cleanup hang')
    prior=n.R/'stream/original-runtime-process-native17-r71/environment-outcomes'/(IDENT+'.json');old=read(prior);native={}
    for kind in ['install','nop']:
        trial=Path(old['native_'+kind+'_trial']);path=trial/'result.json';raw=read(path)
        if n.sha(path)!=old[kind+'_result_sha256'] or not raw['finished_at'] or raw.get('infrastructure_errors'):raise ValueError('Original native Result changed')
        exception=(raw.get('exception_info') or {}).get('exception_type')
        if kind=='install' and exception:raise ValueError('CLI did not complete normally')
        if kind=='nop' and (exception!='VerifierTimeoutError' or raw.get('verifier_result') is not None):raise ValueError('Do not invent an official Reward or rewrite the original timeout')
        native[kind]=dict(trial=str(trial),result_sha256=n.sha(path),exception_type=exception)
    review=dict(task_id=IDENT,pool='tmax',status='ENV_READY',source_sha256=n.sha(Path(__file__)),native_results=native,
        original_verifier=str(source),original_verifier_sha256=n.sha(source),original_public_instruction_sha256=n.sha(instruction),
        diagnostic_plan=str(root/'PLAN.json'),diagnostic_plan_sha256=n.sha(root/'PLAN.json'),
        diagnostic_stdout=str(stdout),diagnostic_stdout_sha256=n.sha(stdout),diagnostic_stderr=str(stderr),diagnostic_stderr_sha256=n.sha(stderr),
        original_nop_verifier_completed=False,original_nop_reward=None,model_calls=0,teacher_attempts_before_review=0,
        official_test_resource_deadline_or_goal_changes=0,teacher_success_not_implied=True,
        reason='Known original Verifier limitation on an unsolved Goal: all5 original tests loaded and failed in0.03s because the assigned repository/hook/backup/cron were not implemented. The original non-daemon SMTP worker survives the clone assertion because cleanup is not in finally; a recorded stack shows socket.accept plus Python threading._shutdown. Original full120s NOP timeout and absent Reward remain unchanged. This permits a first teacher attempt with the unmodified official test. It is not normal completed NOP verification, a zero score, or teacher success. Only actually completed official reward1 with normal Agent closure, complete Recorder and Qwen audits can qualify.')
    path=n.R/'checks/original-verifier-failure-cleanup-review-r86.json';n.freeze(path,review)
    ready=dict(task_id=IDENT,pool='tmax',status='ENV_READY',admitted_task=admitted,engine_id=n.NODE['engine_id'],
        deployment_config_sha256=n.CONFIG_SHA,placement=admitted['deployment_assignment'],placement_sha256=n.sha(Path(admitted['deployment_assignment'])),
        raw_outcome=str(path),raw_outcome_sha256=n.sha(path),nop_reward=None,original_nop_verifier_completed=False,
        preflight_exception='ORIGINAL_VERIFIER_THREAD_CLEANUP_ON_UNSOLVED_GOAL',teacher_success_not_implied=True,reason=review['reason'])
    for kind,item in native.items():ready['native_'+kind+'_trial']=item['trial'];ready[kind+'_result_sha256']=item['result_sha256']
    digest=hashlib.sha256(json.dumps(ready,sort_keys=True).encode()).hexdigest();dest=n.D/'ready-revisions'/IDENT/(digest+'.json');n.freeze(dest,ready)
    print(json.dumps(dict(task_id=IDENT,ready=str(dest),actual_original_nop_reward=None,timeout_preserved=True,teacher_dispatches=0)))


if __name__=='__main__':main()
