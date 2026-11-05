"""One finite native retry for two still-blocked setup paths; zero model calls."""
import asyncio
import json
import os
from pathlib import Path
import recheck_pre_agent_setup17_r162 as native
import collection_readiness_r17 as deployment

R=deployment.R
original_plan=native.plan
IDS={'task_000153_8140f89f','task_001587_0949d03f'}


def plan():
    current=json.loads((R/'stream/collection-r4/deployment-r17/state.json').read_text())
    if current['runtime_engine_id']!=deployment.NODE['engine_id']:raise ValueError('Runtime changed')
    diagnosis=R/'stream/public-setup-timeout-diagnostics17-r191/TERMINAL.json'
    result=json.loads(diagnosis.read_text())
    item=next(x for x in result['outcomes'] if x['task_id']=='task_001587_0949d03f')
    if item['steps'][0]['return_code']!=0 or not item['native_cleanup_complete']:
        raise ValueError('Native original managed-Python transport was not actually recovered')
    value=original_plan();value['tasks']=[item for item in value['tasks'] if item['task_id'] in IDS]
    if {item['task_id'] for item in value['tasks']}!=IDS:raise ValueError('Admission changed; do not replay')
    value.update(source_sha256=deployment.sha(Path(__file__)),original_helper_sha256=deployment.sha(R/'scripts/recheck_pre_agent_setup17_r162.py'),
        public_diagnosis=str(diagnosis),public_diagnosis_sha256=deployment.sha(diagnosis),
        rationale='Original managed Python retrieval succeeded after the recorded setup timeout; retry complete CLI/NOP once without dependency/resource changes',
        preparation_capacity='One extra native zero-model slot; alongside R211 at most two finite diagnostic slots')
    return value


if __name__=='__main__':
    assert deployment.sha(R/'scripts/recheck_pre_agent_setup17_r162.py')=='b1c5239570bd37a017d6986dbbb20b4e9380fed7aae066226550f552cd3a2f4a'
    native.n=deployment
    native.S=R/'stream/remaining-tmax-setup-recheck17-r212'
    native.plan=plan
    os.environ['PATH']=deployment.DEPLOYMENT['native_client_bin']+':'+str(R/'client-bin-v2')+':'+os.environ['PATH']
    os.environ['SSH_AUTH_SOCK']='/home/chenkeyi/.local/share/harbor-rsi/near-r3-20261015/auth.sock'
    for key in ['DEEPSEEK_API_KEY','OPENAI_API_KEY','GH_TOKEN']:os.environ.pop(key,None)
    asyncio.run(native.main())
