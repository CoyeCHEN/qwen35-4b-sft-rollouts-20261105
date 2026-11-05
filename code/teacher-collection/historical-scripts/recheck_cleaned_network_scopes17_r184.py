"""One finite native zero-model pass for four preserved, cleaned terminal scopes."""
import asyncio
import json
import os
from pathlib import Path

import recheck_pre_agent_setup17_r162 as native

R = native.n.R
original_plan = native.plan


def plan():
    proof_path = R / 'checks/terminal-network-cleanup-r184.json'
    proof = json.loads(proof_path.read_text())
    if not proof['original_results_rehashed_unchanged']:
        raise ValueError('Original Result preservation not verified')
    accepted = {item['task_id'] for item in proof['terminal']['results']
                if item['status'] == 'PRESERVED_AND_OWNED_RESOURCES_CLEANED'}
    if len(accepted) != 4:
        raise ValueError('Unexpected finite cleanup scope')
    for entry in proof['proofs'].values():
        if entry['engine_id'] != native.n.NODE['engine_id'] or any(entry['remaining_owned_resources'].values()):
            raise ValueError('Cleanup identity or remaining resources do not match')
    value = original_plan()
    value['tasks'] = [item for item in value['tasks'] if item['task_id'] in accepted]
    if {item['task_id'] for item in value['tasks']} != accepted:
        raise ValueError('Task admission changed; inspect before replay')
    value.update(source_sha256=native.n.sha(Path(__file__)), cleanup_proof=str(proof_path),
                 cleanup_proof_sha256=native.n.sha(proof_path),
                 original_attempt_counts_preserved=True, preparation_capacity='One finite zero-model native slot')
    return value


if __name__ == '__main__':
    if native.n.sha(R / 'scripts/recheck_pre_agent_setup17_r162.py') != 'b1c5239570bd37a017d6986dbbb20b4e9380fed7aae066226550f552cd3a2f4a':
        raise ValueError('Native helper identity changed')
    native.S = R / 'stream/cleaned-network-scopes-recheck17-r184'
    native.plan = plan
    os.environ['PATH'] = native.n.DEPLOYMENT['native_client_bin'] + ':' + str(R / 'client-bin-v2') + ':' + os.environ['PATH']
    os.environ['SSH_AUTH_SOCK'] = '/home/chenkeyi/.local/share/harbor-rsi/near-r3-20261015/auth.sock'
    for name in ['DEEPSEEK_API_KEY', 'OPENAI_API_KEY', 'GH_TOKEN']:
        os.environ.pop(name, None)
    asyncio.run(native.main())
