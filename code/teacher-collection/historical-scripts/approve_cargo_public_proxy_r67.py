"""Reuse the completed exact Cargo-only native acceptance, without replay."""
import copy
import hashlib
import json
from pathlib import Path

import collection_readiness_r11 as n
from collection_attempts_r8 import attempt_counts
from collection_selection_r7 import active_rows


def main():
    ident='task_009221_2c5f3e9f'
    if attempt_counts().get(ident,0):raise ValueError('Already started; preserve its existing configuration')
    source=n.R/'stream/public-dependency-native17-r63/environment-outcomes'/(ident+'.json')
    old=json.loads(source.read_text())
    if old['status']!='ENV_READY':raise ValueError('Exact public dependency native acceptance is not Ready')
    plan=n.R/'stream/public-dependency-native17-r63/PLAN.json'
    if json.loads(plan.read_text())['source_sha256']!=n.sha(n.R/'scripts/accept_public_dependencies17_r63.py'):
        raise ValueError('Frozen native source changed')
    row=next(x for x in active_rows(attempt_counts()) if x['task_id']==ident)
    admitted=n.prepare_identity(row)
    if admitted['image_id']!=old['admitted_task']['image_id'] or admitted['prepared_task_toml_sha256']!=old['admitted_task']['prepared_task_toml_sha256']:
        raise ValueError('Original Task or image changed')
    native={}
    for kind in ['install','nop']:
        trial=Path(old['native_'+kind+'_trial']);p=trial/'result.json';raw=json.loads(p.read_text())
        if n.sha(p)!=old[kind+'_result_sha256'] or not raw['finished_at'] or raw.get('exception_info') or raw.get('infrastructure_errors'):
            raise ValueError('Native acceptance was not cleanly completed')
        actual=copy.deepcopy(raw['config']);expected=n.native_config(admitted,kind)
        if kind=='install':expected.agent.env={}
        expected=expected.model_dump(mode='json')
        for doc in [actual,expected]:
            doc.pop('trial_name');doc.pop('trials_dir')
            doc['environment']['extra_docker_compose']=doc['environment']['extra_docker_compose'][1:]
        if actual!=expected:raise ValueError('Native binding differs beyond the bounded precheck network/name/directory')
        if kind=='nop':
            if n.verify_nop(type('Result',(),dict(exception_info=None,infrastructure_errors=[]))(),trial,admitted)!=0:
                raise ValueError('Unexpected original NOP result')
        native[kind]=dict(trial=str(trial),result_sha256=n.sha(p))
    approval=dict(task_id=ident,pool='tmax',status='ENV_READY',source_sha256=n.sha(Path(__file__)),
        source_outcome=str(source),source_outcome_sha256=n.sha(source),native_results=native,
        deployment_config_sha256=n.CONFIG_SHA,public_dependency=n.DEPLOYMENT['task_public_dependencies'][ident],
        original_task_test_image_resource_deadline_changes=0,teacher_model_transport_changes=0,
        reason='Original initial test, CLI installation and official NOP completed on17. Only CARGO_HTTP_PROXY added for public crate downloads; actual model service remains direct. No teacher replay.')
    path=n.R/'checks/cargo-public-proxy-approval-r67.json';n.freeze(path,approval)
    ready=dict(old,admitted_task=admitted,deployment_config_sha256=n.CONFIG_SHA,
        placement=admitted['deployment_assignment'],placement_sha256=n.sha(Path(admitted['deployment_assignment'])),
        raw_outcome=str(path),raw_outcome_sha256=n.sha(path))
    digest=hashlib.sha256(json.dumps(ready,sort_keys=True).encode()).hexdigest()
    dest=n.D/'ready-revisions'/ident/(digest+'.json');n.freeze(dest,ready)
    print(json.dumps(dict(task_id=ident,ready=str(dest),native_nop_reward=old['nop_reward'],teacher_dispatches=0)))


if __name__=='__main__':main()
