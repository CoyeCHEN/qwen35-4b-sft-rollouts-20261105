"""Existing unique controller: audit legacy work; hold superseded new admissions."""
import hashlib
import importlib
import json
from pathlib import Path

legacy = importlib.import_module('winner267-phase18-r16')
R, C, E = legacy.R, legacy.C, legacy.E
POLICY = R / 'checks/USER_RELIABILITY_REPAIR_CAMPAIGN_R1.json'


def advance(owner, state, launch_cpu):
    assert legacy.read(C / 'NATIVE_ADVANCE_OWNER.json') == owner
    policy = legacy.read(POLICY)
    assert policy['new_formal_n3_admission'] is False
    assert policy['new_same_protocol_comparison_admission'] is False
    assert policy['preserve_healthy_legacy_trials'] is True
    assert policy['no_retraining_and_no_teacher_collection'] is True

    # Keep the existing single CPU audit and native queues. Never call the old
    # winner selection, serving release, model launch, or old-study progression.
    incremental = legacy.cached_matrix()
    audit = legacy.ensure_cpu_audit(owner, incremental, launch_cpu)
    state['common150_cpu_audit'] = audit
    completed_path = E / 'checks/DIAGNOSTIC150_MATRIX_R6.json'
    completed_bytes = completed_path.read_bytes()
    completed = json.loads(completed_bytes)
    assert completed['source_sha256'] == 'f0ecc863e13004bf245527e21e177fee5113d2b943a0f3bd760726dbd691e3b7'
    state['common150_scoring_snapshot'] = {
        key: completed[key] for key in
        ['checked_at', 'source_sha256', 'complete', 'logical_terminal', 'expected', 'models']
    }
    state['common150_scoring_snapshot'].update(
        snapshot_is_last_completed_audit=True,
        matrix_path=str(completed_path),
        matrix_sha256=hashlib.sha256(completed_bytes).hexdigest(),
        incremental_rows_are_not_reported_as_completed_scores=True,
    )
    cfg = legacy.read(R / 'configs/diagnostic150-five-model-r1.json')
    state['legacy_common150_completion_gate'] = legacy.completion_gate(cfg)
    state['new_common30_model_admission'] = False
    state['selected267'] = dict(
        status='USER_SUPERSEDED_OLD_AUTO_WINNER267_ADMISSION_HELD',
        new_formal_n3_admission=False,
        requires_repaired_protocol_canary_and_new_m0_common30=True,
        old_result_reward_recorder_protocols_remain_separate=True,
    )
    state['reliability_repair'] = dict(
        status='P0_P5_OFFLINE_REPLAY_AND_FIXES_BEFORE_NEW_MODEL_ADMISSION',
        campaign_policy_path=str(POLICY),
        campaign_policy_sha256=legacy.sha(POLICY),
        healthy_legacy_trials_preserved=True,
        current_checkpoint_identities_from_manifest=True,
        official_task_verifier_reward_unchanged=True,
        current_old_801_and_old_winner267_auto_dispatch_disabled=True,
        no_new_old_research_gpu_dispatch=True,
    )
    state['status'] = 'RELIABILITY_REPAIR_WITH_HEALTHY_LEGACY_TRIALS_PRESERVED'


if __name__ == '__main__':
    raise SystemExit('Only the existing unique controller may call advance')
