"""Native initial/install/official-NOP acceptance for the two mirror bindings."""
import asyncio
import json
import os
from pathlib import Path
import recheck_pre_agent_setup17_r162 as native
import collection_readiness_r18 as deployment

R=deployment.R
original_plan=native.plan
IDS={'data-processing_20260420_020307_002','video-processing_20260414_211532_001'}


def plan():
    candidate=R/'checks/signed-debian-deployment-r219.json'
    proposal=json.loads(candidate.read_text())
    if proposal['sha256']!=deployment.CONFIG_SHA or set(proposal['task_ids'])!=IDS or proposal['teacher_admission_granted']:
        raise ValueError('Native candidate belongs to another deployment or has admission authority')
    value=original_plan();value['tasks']=[item for item in value['tasks'] if item['task_id'] in IDS]
    if {item['task_id'] for item in value['tasks']}!=IDS:raise ValueError('Task admission changed; preserve it')
    value.update(source_sha256=deployment.sha(Path(__file__)),original_helper_sha256=deployment.sha(R/'scripts/recheck_pre_agent_setup17_r162.py'),
        candidate=str(candidate),candidate_sha256=deployment.sha(candidate),
        public_dependency_changes='Only declared read-only same-signed-suite Debian mirror source files; original image/Task/test/resource/deadline and model transport unchanged',
        preparation_capacity='One finite native zero-model slot; no Teacher permit')
    return value


if __name__=='__main__':
    assert deployment.sha(R/'scripts/recheck_pre_agent_setup17_r162.py')=='b1c5239570bd37a017d6986dbbb20b4e9380fed7aae066226550f552cd3a2f4a'
    native.n=deployment
    native.S=R/'stream/signed-debian-native-acceptance17-r220'
    native.plan=plan
    os.environ['PATH']=deployment.DEPLOYMENT['native_client_bin']+':'+str(R/'client-bin-v2')+':'+os.environ['PATH']
    os.environ['SSH_AUTH_SOCK']='/home/chenkeyi/.local/share/harbor-rsi/near-r3-20261015/auth.sock'
    for key in ['DEEPSEEK_API_KEY','OPENAI_API_KEY','GH_TOKEN']:os.environ.pop(key,None)
    asyncio.run(native.main())
