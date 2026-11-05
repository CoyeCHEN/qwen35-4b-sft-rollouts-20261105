"""One native recheck of the newly observed pre-command workdir timeout."""
import asyncio
import json
import os
from pathlib import Path
import recheck_pre_agent_setup17_r162 as native
import collection_readiness_r17 as deployment

R=deployment.R
IDENT='task_008760_0977d5f0'
original_plan=native.plan


def plan():
    value=original_plan();value['tasks']=[item for item in value['tasks'] if item['task_id']==IDENT]
    if len(value['tasks'])!=1:raise ValueError('Task admission changed; no extra environment pass')
    result=json.loads(Path(value['tasks'][0]['original_result']).read_text())
    if result.get('agent_execution') or 'Task workdir probe timed out after 30 seconds before command dispatch' not in result['exception_info']['exception_message']:
        raise ValueError('Different failure or actual Teacher evidence; preserve it')
    value.update(source_sha256=deployment.sha(Path(__file__)),original_helper_sha256=deployment.sha(R/'scripts/recheck_pre_agent_setup17_r162.py'),
        rationale='One complete original native pass after the recorded pre-command transport timeout; no workdir/resource/Task changes',
        preparation_capacity='One finite zero-model native preparation slot')
    return value


if __name__=='__main__':
    assert deployment.sha(R/'scripts/recheck_pre_agent_setup17_r162.py')=='b1c5239570bd37a017d6986dbbb20b4e9380fed7aae066226550f552cd3a2f4a'
    native.n=deployment;native.OLD=Path(deployment.DEPLOYMENT['controller_root'])
    native.S=R/'stream/workdir-transport-recheck17-r228';native.plan=plan
    os.environ['PATH']=deployment.DEPLOYMENT['native_client_bin']+':'+str(R/'client-bin-v2')+':'+os.environ['PATH']
    os.environ['SSH_AUTH_SOCK']='/home/chenkeyi/.local/share/harbor-rsi/near-r3-20261015/auth.sock'
    for key in ['DEEPSEEK_API_KEY','OPENAI_API_KEY','GH_TOKEN']:os.environ.pop(key,None)
    asyncio.run(native.main())
