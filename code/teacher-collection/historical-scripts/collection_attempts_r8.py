"""Conservative admission counts with only four proved pre-Agent exceptions.

Raw configuration reservations are counted before the accepted evidence is
applied. This permits two actual attempts even when a proved environment-only
reservation makes the historical configuration count three. No trial is reset.
"""
from collections import Counter
import hashlib
import json
from pathlib import Path

from run_collection_stream_r4 import R


def configuration_reservations():
    counts=Counter()
    for file in (R/'jobs').glob('*/config.json'):
        value=json.loads(file.read_text())
        if value.get('install_only') or not any(x.get('name')=='open-harness' for x in value.get('agents',[])):continue
        if value.get('n_attempts',1)!=1 or value.get('retry',{}).get('max_retries',0)!=0:
            raise ValueError('Unexpected legacy repetition; no budget reinterpretation')
        counts.update(Path(x['path']).name for x in value['tasks'])
    for file in R.glob('stream/*/dispatches/*/dispatch.json'):
        value=json.loads(file.read_text())
        if value['kind']=='teacher':counts[value['task_id']]+=1
    return counts


def attempt_counts():
    counts=configuration_reservations()
    proof=json.loads((R/'checks/attempt-environment-only-reconciliation-r6.json').read_text())
    if proof['status']!='FOUR_TERMINAL_ENVIRONMENT_START_FAILURES_PROVED_BEFORE_AGENT_SETUP':
        raise ValueError('Pre-Agent reconciliation evidence is not accepted')
    rows=proof['environment_only_trials']
    if len(rows)!=4 or len({x['task_id'] for x in rows})!=4:
        raise ValueError('The authorized proof scope changed')
    for row in rows:
        file=Path(row['result_path'])
        if hashlib.sha256(file.read_bytes()).hexdigest()!=row['result_sha256']:
            raise ValueError('Original environment-only Result changed')
        value=json.loads(file.read_text())
        if value.get('failure_phase')!='environment_setup' or value.get('agent_setup') or value.get('agent_execution'):
            raise ValueError('An excluded reservation now contains Agent-start evidence')
        if (file.parent/'agent/openharness-rollout/events.jsonl').exists():
            raise ValueError('An environment-only exception contains a Recorder')
        counts[row['task_id']]-=1
    if min(counts.values(),default=0)<0 or max(counts.values(),default=0)>2 or len(+counts)>1000 or sum(counts.values())>2000:
        raise ValueError('Actual or conservatively reserved attempt cap exceeded')
    return +counts
