"""One native zero-model recheck after an exact terminal-scope cleanup."""
import asyncio
import json
import os
from pathlib import Path

import recheck_pre_agent_setup17_r162 as native

R = native.n.R
IDENT = 'data-science_20260414_211453_004'
original_plan = native.plan


def plan():
    cleanup_path = R / 'checks/terminal-scope-cleanup-r169.json'
    cleanup = json.loads(cleanup_path.read_text())
    if not cleanup['owned_container_network_volume_cleanup_complete'] or any(cleanup['remaining_owned_resources'].values()):
        raise ValueError('Original retained scope cleanup has not completed')
    if cleanup['identity'] != 'cbf183a0d82248229de2d3c7e5d09f50' or cleanup['engine_id'] != native.n.NODE['engine_id']:
        raise ValueError('Cleanup belongs to another scope or Engine')
    if native.n.sha(R / 'scripts/recheck_pre_agent_setup17_r162.py') != 'b1c5239570bd37a017d6986dbbb20b4e9380fed7aae066226550f552cd3a2f4a':
        raise ValueError('Frozen native preparation helper changed')
    value = original_plan()
    tasks = [x for x in value['tasks'] if x['task_id'] == IDENT]
    if len(tasks) != 1:
        raise ValueError('Preserve changed admission; do not repeat this Task')
    value.update(tasks=tasks, source_sha256=native.n.sha(Path(__file__)),
        native_helper_sha256=native.n.sha(R / 'scripts/recheck_pre_agent_setup17_r162.py'),
        cleanup_proof=str(cleanup_path), cleanup_proof_sha256=native.n.sha(cleanup_path),
        existing_paid_attempts_preserved=tasks[0]['existing_attempt_budget_used'],
        original_failed_scope_result_unchanged=cleanup['original_result_sha256'],
        preparation_capacity='One additional native zero-model slot; with R162 at most two extra preparation slots, outside eight Teacher permits')
    return value


if __name__ == '__main__':
    native.S = R / 'stream/cleaned-original-scope-recheck17-r170'
    native.plan = plan
    os.environ['PATH'] = native.n.DEPLOYMENT['native_client_bin'] + ':' + str(R / 'client-bin-v2') + ':' + os.environ['PATH']
    os.environ['SSH_AUTH_SOCK'] = '/home/chenkeyi/.local/share/harbor-rsi/near-r3-20261015/auth.sock'
    for name in ['DEEPSEEK_API_KEY', 'OPENAI_API_KEY', 'GH_TOKEN']:
        os.environ.pop(name, None)
    asyncio.run(native.main())
