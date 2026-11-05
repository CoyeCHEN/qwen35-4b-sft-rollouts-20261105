"""Exclude only proved environment-start failures from model-attempt counts.

All other legacy reservations remain conservative. No existing Trial is reset.
"""
import hashlib
import json
from pathlib import Path
import run_collection_stream_r4 as c

PROOF = c.R / 'checks/attempt-environment-only-reconciliation-r6.json'


def attempt_counts():
    counts = c.attempt_counts()
    proof = json.loads(PROOF.read_text())
    if proof['status'] != 'FOUR_TERMINAL_ENVIRONMENT_START_FAILURES_PROVED_BEFORE_AGENT_SETUP':
        raise ValueError('Attempt reconciliation has not been accepted')
    for row in proof['environment_only_trials']:
        file = Path(row['result_path'])
        if hashlib.sha256(file.read_bytes()).hexdigest() != row['result_sha256']:
            raise ValueError('Original environment-only Result changed')
        value = json.loads(file.read_text())
        if value.get('failure_phase') != 'environment_setup' or value.get('agent_setup') or value.get('agent_execution'):
            raise ValueError('Reconciled failure now contains Agent start evidence')
        if (file.parent / 'agent/openharness-rollout/events.jsonl').exists():
            raise ValueError('Unexpected Recorder in an environment-only failure')
        counts[row['task_id']] -= 1
    if min(counts.values(), default=0) < 0 or max(counts.values(), default=0) > 2 or sum(counts.values()) > 2000:
        raise ValueError('Reconciled native attempt cap differs')
    return +counts
