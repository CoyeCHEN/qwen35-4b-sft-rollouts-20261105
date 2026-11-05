"""Bind one completed original-process acceptance to the new Campaign, without replay."""
import copy
import hashlib
import json
from pathlib import Path

import collection_readiness_r13 as n
from collection_attempts_r8 import attempt_counts
from collection_selection_r7 import active_rows


def read(p):return json.loads(Path(p).read_text())


def main():
    approvals=[]
    image_doc=read(n.R/'manifests/PUBLIC_DEPENDENCY_IMAGE_APPROVALS_R76.json')
    for ident in n.DEPLOYMENT['new_native_acceptance_required_task_ids']:
        if attempt_counts().get(ident,0):raise ValueError('An attempted Task cannot change deployment binding')
        row=next(x for x in active_rows(attempt_counts()) if x['task_id']==ident)
        alias=None
        if ident in n.DEPLOYMENT['task_runtime_initialization']:
            source=Path(n.DEPLOYMENT['task_runtime_initialization'][ident]['native_acceptance'])
            raw=read(source);admitted=n.choose(raw['admitted_task']);native={kind:dict(trial=raw['native_'+kind+'_trial'],result_sha256=raw[kind+'_result_sha256']) for kind in ['install','nop']}
        else:
            item=next(x for x in image_doc['tasks'] if x['task_id']==ident)
            source=Path(item['path'])
            if n.sha(source)!=item['sha256']:raise ValueError('Approved exact public image changed')
            raw=read(source);admitted=n.prepare_identity(row);native=raw['native_results'];alias=raw['native_task_path_alias']
        for kind,item in native.items():
            trial=Path(item['trial']);path=trial/'result.json';result=read(path)
            if n.sha(path)!=item['result_sha256'] or result.get('exception_info') or result.get('infrastructure_errors') or not result['finished_at']:
                raise ValueError('Original native Result changed or was not completed normally')
            actual=copy.deepcopy(result['config']);expected=n.native_config(admitted,kind)
            if kind=='install':expected.agent.env={}
            expected=expected.model_dump(mode='json')
            if actual['task']['path']!=expected['task']['path']:
                if alias is None or actual['task']['path']!=alias['from_path'] or expected['task']['path']!=alias['to_path']:
                    raise ValueError('Undeclared native Task path alias')
                a=Path(alias['from_path']);b=Path(alias['to_path'])
                if any(n.sha(p)!=n.sha(b/p.relative_to(a)) for p in a.rglob('*') if p.is_file()):raise ValueError('Task alias changed bytes')
                actual['task']['path']=expected['task']['path']
            for value in [actual,expected]:
                value.pop('trial_name');value.pop('trials_dir');value['environment']['extra_docker_compose']=value['environment']['extra_docker_compose'][1:]
            if actual!=expected:raise ValueError('Native accepted configuration differs outside its dedicated subnet/directory/name and verified Task alias: '+ident+'/'+kind)
            if kind=='nop' and (not (result.get('verifier') or {}).get('finished_at') or (result.get('verifier_result') or {}).get('rewards',{}).get('reward')!=0):
                raise ValueError('Original official NOP verifier did not actually complete with zero')
        proof=dict(task_id=ident,pool='tmax',status='ENV_READY',source_sha256=n.sha(Path(__file__)),
            deployment_config_sha256=n.CONFIG_SHA,prior_native_acceptance=str(source),prior_native_acceptance_sha256=n.sha(source),
            native_results=native,verified_task_path_alias=alias,original_task_test_resource_deadline_changes=0,
            model_transport_or_teacher_loop_changes=0,teacher_success_not_implied=True,
            reason='Completed original initial tests, CLI installation and official NOP are reused with exact native configuration checks. Original Task source/tests/resources remain unchanged. Only the exact source-declared process and trusted initial/Verifier ps output width are added by this Campaign. All existing bindings remain unchanged.')
        path=n.R/'checks/deployment-r13-native-approvals-r105'/(ident+'.json');n.freeze(path,proof)
        ready=dict(task_id=ident,pool='tmax',status='ENV_READY',admitted_task=admitted,engine_id=n.NODE['engine_id'],
            deployment_config_sha256=n.CONFIG_SHA,placement=admitted['deployment_assignment'],placement_sha256=n.sha(Path(admitted['deployment_assignment'])),
            raw_outcome=str(path),raw_outcome_sha256=n.sha(path),nop_reward=0,teacher_success_not_implied=True)
        for kind,item in native.items():ready['native_'+kind+'_trial']=item['trial'];ready[kind+'_result_sha256']=item['result_sha256']
        digest=hashlib.sha256(json.dumps(ready,sort_keys=True).encode()).hexdigest();n.freeze(n.D/'ready-revisions'/ident/(digest+'.json'),ready)
        approvals.append(dict(task_id=ident,path=str(path),sha256=n.sha(path)))
    proxies=read(n.R/'checks/controller-r12-public-dependency-acceptance-r83.json')['approvals']
    for item in proxies:
        if n.sha(Path(item['path']))!=item['sha256']:raise ValueError('Existing public proxy approval changed')
    proof=dict(passed=True,controller_source_sha256=n.sha(n.R/'scripts/run_collection_stream_r13.py'),
        deployment_config_sha256=n.CONFIG_SHA,approvals=[*proxies,*approvals],new_native_ready_tasks=len(approvals),
        existing_approved_bindings_preserved=len(proxies),teacher_dispatches=0,official_task_or_test_changes=0)
    n.freeze(n.R/'checks/controller-r13-public-dependency-acceptance-r105.json',proof)
    print(json.dumps(proof))


if __name__=='__main__':main()
