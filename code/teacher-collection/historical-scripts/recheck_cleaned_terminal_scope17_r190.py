"""Finite native recheck after the last exact terminal-scope cleanup."""
import asyncio
import json
import os
from pathlib import Path
import recheck_pre_agent_setup17_r162 as native

R=native.n.R
original_plan=native.plan


def plan():
    path=R/'checks/terminal-scope-cleanup-r190.json'
    proof=json.loads(path.read_text())
    if proof['task']['identity']!='80b095fe9b4444c2be864613cbfdde5d' or proof['engine_id']!=native.n.NODE['engine_id']:
        raise ValueError('Wrong preserved scope or Engine')
    if proof['status']!='PRESERVED_AND_OWNED_RESOURCES_CLEANED' or any(proof['remaining_owned_resources'].values()):
        raise ValueError('Cleanup is not complete')
    task=proof['task']
    assert native.n.sha(Path(task['original_result']))==task['original_result_sha256']
    value=original_plan()
    value['tasks']=[item for item in value['tasks'] if item['task_id']=='task_005689_e9f526cb']
    if len(value['tasks'])!=1:raise ValueError('Admission changed; no replay')
    value.update(source_sha256=native.n.sha(Path(__file__)),cleanup_proof=str(path),cleanup_proof_sha256=native.n.sha(path),
        preparation_capacity='One finite native zero-model slot; together with R184 at most two')
    return value


if __name__=='__main__':
    assert native.n.sha(R/'scripts/recheck_pre_agent_setup17_r162.py')=='b1c5239570bd37a017d6986dbbb20b4e9380fed7aae066226550f552cd3a2f4a'
    native.S=R/'stream/cleaned-terminal-scope-recheck17-r190'
    native.plan=plan
    os.environ['PATH']=native.n.DEPLOYMENT['native_client_bin']+':'+str(R/'client-bin-v2')+':'+os.environ['PATH']
    os.environ['SSH_AUTH_SOCK']='/home/chenkeyi/.local/share/harbor-rsi/near-r3-20261015/auth.sock'
    for key in ['DEEPSEEK_API_KEY','OPENAI_API_KEY','GH_TOKEN']:os.environ.pop(key,None)
    asyncio.run(native.main())
