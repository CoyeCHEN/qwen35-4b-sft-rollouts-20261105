"""Read-only actual Trial evidence versus conservative configuration reservations.

Never clears uncertain reservations or changes the admission budget ledger.
"""
from collections import Counter, defaultdict
import datetime
import hashlib
import json
from pathlib import Path
import run_collection_stream_r4 as c

R = c.R
trials = {}
reservations = []
for file in sorted((R / 'jobs').glob('*/config.json')):
    config = json.loads(file.read_text())
    if config.get('install_only') or not any(a.get('name') == 'open-harness' for a in config.get('agents', [])):
        continue
    by_task = defaultdict(list)
    for candidate in file.parent.glob('*/config.json'):
        trial = json.loads(candidate.read_text())
        if trial.get('agent', {}).get('name') == 'open-harness' and not trial.get('install_only'):
            by_task[Path(trial['task']['path']).name].append(candidate.parent)
    for row in config['tasks']:
        ident = Path(row['path']).name
        if not by_task[ident]:
            reservations.append(dict(task_id=ident, scope=file.parent.name, config=str(file),
                config_sha256=hashlib.sha256(file.read_bytes()).hexdigest(),
                classification='CONFIG_DECLARED_NO_DISCOVERABLE_NATIVE_TRIAL_UNCERTAINTY_RETAINED', reserved_attempts=1))
        for trial in by_task[ident]:
            trials[str(trial)] = dict(task_id=ident, scope=file.parent.name, trial=trial)
protocol = {}
for file in (R / 'checks').glob('*-live-protocol.json'):
    try:
        rows = json.loads(file.read_text()).get('trials', [])
        for row in rows:
            protocol[row['trial_directory']] = row
    except (OSError, ValueError, AttributeError):
        continue
for file in R.glob('stream/*/dispatches/*/dispatch.json'):
    row = json.loads(file.read_text())
    if row['kind'] != 'teacher':
        continue
    trial = file.parents[2] / 'trials' / row['trial_name']
    trials[str(trial)] = dict(task_id=row['task_id'], scope='stream-' + file.parents[2].name,
        trial=trial, native_agent_start_admitted=True, admitted_at=row.get('dispatched_at'))
rows = []
for key, item in sorted(trials.items()):
    trial = item.pop('trial')
    result = trial / 'result.json'
    native = json.loads(result.read_text()) if result.exists() else {}
    observed = protocol.get(key, {})
    calls = observed.get('calls', {})
    journal = trial / 'agent/openharness-rollout/events.jsonl'
    started = item.get('native_agent_start_admitted') or bool((native.get('agent_execution') or {}).get('started_at'))
    rows.append(dict(item, trial_directory=key, trial_id=native.get('id'), terminal_result=result.exists(),
        native_agent_execution_started=bool(started), recorder_present=journal.exists(),
        observed_agent_provider_calls=sum(x.get('source') == 'agent' and 'payload' in x for x in calls.values()),
        provider_call_evidence_pending=not observed, raw_reward=(native.get('verifier_result') or {}).get('rewards'),
        classification='NATIVE_AGENT_STARTED' if started else 'NATIVE_SETUP_ONLY_OR_START_EVIDENCE_PENDING',
        internal_provider_retries_are_independent_task_attempts=False))
configured = c.attempt_counts()
actual = Counter(row['task_id'] for row in rows if row['native_agent_execution_started'])
if max(actual.values(), default=0) > 2 or sum(actual.values()) > 2000:
    raise ValueError('Actual native AgentStart attempt cap exceeded')
out = dict(checked_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
    status='ACTUAL_NATIVE_ATTEMPTS_AND_UNCERTAIN_CONFIGURATION_RESERVATIONS_RECONCILED_READ_ONLY',
    configured_reservation_total=sum(configured.values()), configured_independent_task_ids=len(configured),
    native_trial_count=len(rows), native_agent_started_trial_count=sum(actual.values()),
    native_agent_started_independent_task_ids=len(actual), uncertain_configuration_only_reservations=reservations,
    trials=rows, task_counts_actual=dict(actual), task_counts_conservative=dict(configured),
    admission_counts_changed=False, uncertain_reservations_cleared=0, model_calls_by_auditor=0)
stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
path=R/'checks'/('attempt-ledger-evidence-r6-'+stamp+'.json')
with path.open('x') as stream:
    json.dump(out, stream, indent=2)
print(json.dumps(dict(proof=str(path), configured=out['configured_reservation_total'], actual_started=sum(actual.values()),
    actual_unique=len(actual), uncertain_config_only=len(reservations), admission_counts_changed=False)))
