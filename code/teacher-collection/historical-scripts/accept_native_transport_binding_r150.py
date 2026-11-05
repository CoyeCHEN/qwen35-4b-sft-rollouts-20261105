"""Bind the already completed native SSH test to equivalent new native configs."""
import copy
import json
from pathlib import Path
import collection_readiness_r16 as n


def main():
    declaration=n.DEPLOYMENT['native_transport_full_acceptance'];source=Path(declaration['path'])
    if n.sha(source)!=declaration['sha256']:raise ValueError('Full native transport acceptance changed')
    value=json.loads(source.read_text());row=n.choose(value['admitted_task'])
    if value['status']!='NATIVE_SSH_POOL_CANDIDATE_ACCEPTED' or value['native_client_sha256']!=n.DEPLOYMENT['native_client_ssh_sha256']:raise ValueError('Another native SSH client was tested')
    for kind,item in value['native_results'].items():
        path=Path(item['trial'])/'result.json';raw=json.loads(path.read_text())
        if n.sha(path)!=item['result_sha256'] or raw.get('exception_info') or raw.get('infrastructure_errors'):raise ValueError('Original native test Result changed')
        actual=copy.deepcopy(raw['config']);expected=n.native_config(row,kind)
        if kind=='install':expected.agent.env={}
        expected=expected.model_dump(mode='json')
        for config in [actual,expected]:
            config.pop('trial_name');config.pop('trials_dir');config['environment']['extra_docker_compose']=config['environment']['extra_docker_compose'][1:]
        if actual!=expected:raise ValueError('Full native acceptance differs outside dedicated name/subnet/log directory')
        if kind=='nop' and (not (raw.get('verifier') or {}).get('finished_at') or raw['verifier_result']['rewards']['reward']!=0):raise ValueError('Official NOP did not finish normally')
    previous=n.R/'checks/controller-r14-public-dependency-acceptance-r122.json';old=json.loads(previous.read_text())
    for item in old['approvals']:
        if n.sha(Path(item['path']))!=item['sha256']:raise ValueError('An existing native public approval changed')
    proof=dict(passed=True,controller_source_sha256=n.sha(n.R/'scripts/run_collection_stream_r16.py'),deployment_config_sha256=n.CONFIG_SHA,
        approvals=old['approvals'],preserved_native_approvals=len(old['approvals']),full_native_transport_acceptance=str(source),full_native_transport_acceptance_sha256=n.sha(source),
        original_task_or_test_changes=0,new_native_model_trials=0,source_sha256=n.sha(Path(__file__)))
    n.freeze(n.R/'checks/controller-r16-public-dependency-acceptance-r150.json',proof);print(json.dumps(proof))


if __name__=='__main__':main()
