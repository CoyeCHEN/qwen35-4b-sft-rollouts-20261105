"""Honor only the identity-pinned, previously approved R86 NOP limitation."""
import datetime
import hashlib
import json
from pathlib import Path

from collection_current_setup_blocks_r293 import current_setup_blocks as original_blocks

IDENT = 'task_008794_911eb529'
REVIEW_SHA = '2a6f91d12fb69ff92d58a34c682906b8cd44e9a4e02251a158c5d4dc891255b8'
PREVIOUS_SHA = '0a5bb6d31c968e3519389fc5e704dfde0a6fc18d0de7b50828800aef1c651181'
CONFIG_SHAS = {'fbfdc5ab8e080ff4ee84ee16fe902716c148bb6c81a06729bac79951de887708',
    '1ae0d944a8240ba8e268e6af458c35a666bd3c0a1d693919cb6a299e11d6d596'}
ENGINE = '59c8ba22-0aa4-4aed-bc43-4e1b5989fa22'
sha = lambda path: hashlib.sha256(Path(path).read_bytes()).hexdigest()
read = lambda path: json.loads(Path(path).read_text())


def current_setup_blocks(root, ready):
    special = ready.get(IDENT)
    reviewed = special and special.get('preflight_exception') == 'ORIGINAL_VERIFIER_THREAD_CLEANUP_ON_UNSOLVED_GOAL'
    ordinary = {key:value for key,value in ready.items() if key != IDENT or not reviewed}
    blocks = original_blocks(root, ordinary)
    if not reviewed:
        return blocks
    if special.get('raw_outcome_sha256') == PREVIOUS_SHA:
        # Historical R86 proof cannot supersede a later CLI setup failure.
        return blocks
    proof = Path(root)/'checks/known-verifier-cleanup-revalidation-r452.json'
    if special.get('raw_outcome') != str(proof) or special.get('raw_outcome_sha256') != REVIEW_SHA or sha(proof) != REVIEW_SHA:
        raise ValueError('Unreviewed official NOP limitation receipt')
    review = read(proof)
    if (review['task_id'] != IDENT or review['engine_id'] != ENGINE
            or review['previous_review_sha256'] != PREVIOUS_SHA
            or not review['existing_research_exception_scope_unchanged']
            or review['original_nop_verifier_completed'] is not False
            or review['original_nop_reward'] is not None
            or review['original_verifier_timeout_sec'] != 120):
        raise ValueError('Existing exact verifier exception scope changed')
    if (special.get('status') != 'ENV_READY' or special.get('nop_reward') is not None
            or special.get('original_nop_verifier_completed') is not False
            or special.get('teacher_success_not_implied') is not True):
        raise ValueError('Do not misreport the preserved NOP timeout as completion or success')
    if any(sha(path) != digest for path,digest in review['source_files'].items()):
        raise ValueError('Known verifier review original evidence changed')
    task = special['admitted_task']
    root_task = Path(task['prepared_task_path'])
    if (task['task_id'] != IDENT or task['image_id'] != 'sha256:447b7aa389436bd9350a5d691f3d22e8dfd9c02be7943fa3a0fcfabb6ebb2ef0'
            or review['source_files'].get(str(root_task/'task.toml')) != task['prepared_task_toml_sha256']
            or review['source_files'].get(str(root_task/'instruction.md')) != task['instruction_sha256']
            or any(review['source_files'].get(str(root_task/item['path'])) != item['sha256'] for item in task['verifier_files'])):
        raise ValueError('Known verifier limitation belongs to a different original Task/image/test')
    if special['engine_id'] != ENGINE or special['deployment_config_sha256'] not in CONFIG_SHAS:
        raise ValueError('Known verifier review moved to an unaccepted runtime')
    placement = Path(special['placement'])
    binding = read(placement)
    if (sha(placement) != special['placement_sha256'] or binding['task_id'] != IDENT
            or binding['node'] != '17' or binding['engine_id'] != ENGINE
            or binding['deployment_config_sha256'] != special['deployment_config_sha256']
            or sha(binding['deployment_config']) != binding['deployment_config_sha256']):
        raise ValueError('Known verifier review placement changed')
    for kind in ['install','nop']:
        if special['native_'+kind+'_trial'] != review['native_'+kind+'_trial']:
            raise ValueError('Known verifier review native Trial changed')
        path = Path(special['native_'+kind+'_trial'])/'result.json'
        result = read(path)
        if sha(path) != special[kind+'_result_sha256'] or not result.get('finished_at') or result.get('infrastructure_errors'):
            raise ValueError('Known verifier review native Result changed')
        if kind == 'install' and result.get('exception_info'):
            raise ValueError('Recovered original CLI installation failed')
        if kind == 'nop' and ((result.get('exception_info') or {}).get('exception_type') != 'VerifierTimeoutError'
                or (result.get('exception_info') or {}).get('exception_message') != 'Verifier execution timed out after 120.0 seconds'
                or result.get('verifier_result') is not None):
            raise ValueError('Do not fabricate completed NOP verification or Reward')
    blocked = blocks.get(IDENT)
    if blocked and blocked['native_result_sha256'] == review['source_native_setup_failure_sha256']:
        install = read(Path(review['native_install_trial'])/'result.json')
        if datetime.datetime.fromisoformat(install['finished_at'].replace('Z','+00:00')) <= datetime.datetime.fromisoformat(blocked['finished_at'].replace('Z','+00:00')):
            raise ValueError('New CLI acceptance predates the actual setup failure')
        blocks.pop(IDENT)
    return blocks
