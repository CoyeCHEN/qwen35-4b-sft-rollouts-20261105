"""Promote existing exact native proofs, preserving the unsolved NOP timeout."""
import ast
import copy
import datetime
import hashlib
import json
from pathlib import Path
import re
import sys

import collection_readiness_r11 as n
from collection_attempts_r8 import attempt_counts
from collection_selection_r7 import active_rows


def read(p): return json.loads(Path(p).read_text())


def main():
    plan_path=n.R/'manifests/VERIFIER_PUBLIC_PROXY_CANDIDATES_R55.json'
    plan=read(plan_path)
    frozen=n.R/'stream/verifier-env-proxy-candidates17-r55/PLAN.json'
    if read(frozen)['source_sha256']!=n.sha(n.R/'scripts/accept_verifier_env_proxy_candidates17_r55.py'):
        raise ValueError('Frozen native probe source changed')
    approvals=[]
    for item in plan['tasks']:
        ident=item['task_id']
        if attempt_counts().get(ident,0):raise ValueError('Already attempted; retain existing deployment')
        row=next(x for x in active_rows(attempt_counts()) if x['task_id']==ident)
        admitted=n.prepare_identity(row)
        if admitted['image_id']!=item['image_id'] or admitted['prepared_task_toml_sha256']!=item['prepared_task_toml_sha256']:
            raise ValueError('Original Task/image changed')
        old_path=n.R/'stream/verifier-env-proxy-candidates17-r55/environment-outcomes'/(ident+'.json')
        old=read(old_path);native={};raw={}
        for kind in ['install','nop']:
            trial=Path(old['native_'+kind+'_trial']);path=trial/'result.json';result=read(path)
            if n.sha(path)!=old[kind+'_result_sha256'] or not result['finished_at'] or result.get('infrastructure_errors'):
                raise ValueError('Prior native result/cleanup identity differs')
            actual=copy.deepcopy(result['config']);expected=n.native_config(admitted,kind)
            if kind=='install':
                expected.agent.env={}
                for key in plan['verifier_public_dependency_env']:expected.verifier.env.pop(key,None)
            expected=expected.model_dump(mode='json')
            for doc in [actual,expected]:
                doc.pop('trial_name');doc.pop('trials_dir')
                # Dedicated bounded precheck subnet differs from the teacher subnet.
                doc['environment']['extra_docker_compose']=doc['environment']['extra_docker_compose'][1:]
            if actual!=expected:raise ValueError('Existing native proof differs beyond its dedicated subnet/name/directory')
            exception=(result.get('exception_info') or {}).get('exception_type')
            if kind=='install' and exception:raise ValueError('CLI install did not complete normally')
            native[kind]=dict(trial=str(trial),result_sha256=n.sha(path),exception_type=exception)
            raw[kind]=result
        goal_exception=ident=='software-engineering_20260414_211453_003'
        extra={}
        if goal_exception:
            if native['nop']['exception_type']!='VerifierTimeoutError' or raw['nop'].get('verifier_result') is not None:
                raise ValueError('Keep the actual NOP timeout and absent Reward')
            probe_dir=n.R/'stream/cf-native-verifier-env-bootstrap17-r60/probes'/ident
            probe=read(probe_dir/'PROBE.json')
            if not probe['native_cleanup_completed'] or probe['official_verifier_runs']!=0 or {s['name']:s['return_code'] for s in probe['steps']}!={'original_public_bootstrap_only':0,'trusted_official_test_collection':0,'public_assigned_hang_reproduction':1,'no_reward_written':0}:
                raise ValueError('Exact native-env bootstrap/discovery/public Goal probe failed')
            if read(probe_dir/'effective-verifier-env.json')['candidate']!=n.native_config(admitted,'nop').verifier.env:
                raise ValueError('Diagnostic did not inherit the actual native Verifier environment')
            instruction=(Path(admitted['prepared_task_path'])/'instruction.md').read_text()
            if 'deadlock' not in instruction.lower() or 'ProcessPoolExecutor' not in instruction:
                raise ValueError('Public assignment does not establish the deadlock boundary')
            collect=probe_dir/'trusted_official_test_collection-stdout.txt'
            if not re.search(r'^5 tests collected in [\d.]+s$',collect.read_text(),re.M):raise ValueError('Original five tests did not load')
            goal=probe_dir/'public_assigned_hang_reproduction-stdout.txt'
            if 'Process timed out after 60s (likely deadlock)' not in goal.read_text():raise ValueError('Original public deadlock not reproduced')
            tree=ast.parse((Path(admitted['prepared_task_path'])/'tests/test_outputs.py').read_bytes())
            if len([x for x in tree.body if isinstance(x,ast.FunctionDef) and x.name.startswith('test_')])!=5:raise ValueError('Official test count differs')
            extra=dict(preflight_exception='PUBLICLY_ASSIGNED_UNSOLVED_DEADLOCK',original_nop_verifier_completed=False,
                original_nop_reward=None,public_diagnostic=str(probe_dir/'PROBE.json'),public_diagnostic_sha256=n.sha(probe_dir/'PROBE.json'),
                test_collection=str(collect),test_collection_sha256=n.sha(collect),public_goal_probe=str(goal),public_goal_probe_sha256=n.sha(goal))
            reward=None
        else:
            if native['nop']['exception_type']:raise ValueError('Official NOP did not complete')
            reward=n.verify_nop(type('Result',(),dict(exception_info=None,infrastructure_errors=[]))(),Path(native['nop']['trial']),admitted)
            if reward!=0:raise ValueError('Unexpected unchanged-task NOP result')
        approval=dict(task_id=ident,pool='calibforge',status='ENV_READY',reviewed_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
            source_sha256=n.sha(Path(__file__)),source_outcome=str(old_path),source_outcome_sha256=n.sha(old_path),
            deployment_config_sha256=n.CONFIG_SHA,native_results=native,public_dependency=n.DEPLOYMENT['task_public_dependencies'][ident],
            official_task_test_image_resource_deadline_changes=0,teacher_model_transport_changes=0,teacher_success_not_implied=True,
            reason='Same original Task and image; native Verifier-only public package proxy. The real official NOP Result is retained. Qualified teacher success still requires completed official reward1, normal Agent closure, Recorder and full target audit.',**extra)
        approval_path=n.R/'checks/cf-verifier-proxy-approvals-r64'/(ident+'.json')
        if '--validate-only' not in sys.argv:
            n.freeze(approval_path,approval)
            ready=dict(task_id=ident,pool='calibforge',status='ENV_READY',admitted_task=admitted,engine_id=n.NODE['engine_id'],
                deployment_config_sha256=n.CONFIG_SHA,placement=admitted['deployment_assignment'],placement_sha256=n.sha(Path(admitted['deployment_assignment'])),
                raw_outcome=str(approval_path),raw_outcome_sha256=n.sha(approval_path),nop_reward=reward,teacher_success_not_implied=True,**extra)
            for kind,p in native.items():ready['native_'+kind+'_trial']=p['trial'];ready[kind+'_result_sha256']=p['result_sha256']
            digest=hashlib.sha256(json.dumps(ready,sort_keys=True).encode()).hexdigest()
            n.freeze(n.D/'ready-revisions'/ident/(digest+'.json'),ready)
        approvals.append(dict(task_id=ident,nop_reward=reward,goal_exception=goal_exception))
    print(json.dumps(dict(validated=True,ready_published='--validate-only' not in sys.argv,approvals=approvals,teacher_dispatches=0)))


if __name__=='__main__':main()
