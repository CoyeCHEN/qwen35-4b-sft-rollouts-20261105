"""Finite original native checks for three pre-Teacher CLI installation timeouts."""
import asyncio
import json
import os
from pathlib import Path
import recheck_pre_agent_setup17_r162 as native
import collection_readiness_r19 as deployment

R=deployment.R
IDS={'task_001026_bfbfc014','task_001833_0008f93b','task_003660_31110d11'}
original_plan=native.plan


def plan():
    value=original_plan();value['tasks']=[item for item in value['tasks'] if item['task_id'] in IDS]
    if not 1<=len(value['tasks'])<=3:raise ValueError('Task admission changed; no extra environment pass')
    for task in value['tasks']:
        result=json.loads(Path(task['original_result']).read_text())
        if result.get('agent_execution') or result['exception_info']['exception_type']!='AgentSetupTimeoutError':
            raise ValueError('Different failure or actual Teacher evidence; preserve it')
    value.update(source_sha256=deployment.sha(Path(__file__)),original_helper_sha256=deployment.sha(R/'scripts/recheck_pre_agent_setup17_r162.py'),
        rationale='One complete original native pass after recorded CLI installation command timeouts; no resources, setup budget, Task or official tests changed',
        preparation_capacity='One finite zero-model native preparation slot')
    return value


if __name__=='__main__':
    assert deployment.sha(R/'scripts/recheck_pre_agent_setup17_r162.py')=='b1c5239570bd37a017d6986dbbb20b4e9380fed7aae066226550f552cd3a2f4a'
    native.n=deployment;native.OLD=Path(deployment.DEPLOYMENT['controller_root'])
    native.S=R/'stream/cli-install-timeout-recheck17-r243';native.plan=plan
    os.environ['PATH']=deployment.DEPLOYMENT['native_client_bin']+':'+str(R/'client-bin-v2')+':'+os.environ['PATH']
    os.environ['SSH_AUTH_SOCK']='/home/chenkeyi/.local/share/harbor-rsi/near-r3-20261015/auth.sock'
    for key in ['DEEPSEEK_API_KEY','OPENAI_API_KEY','GH_TOKEN']:os.environ.pop(key,None)
    asyncio.run(native.main())
