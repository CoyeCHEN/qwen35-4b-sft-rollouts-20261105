"""Read-only native campaign accounting snapshot, not a dispatch controller.

Stream existing Recorder events on the execution host. Preserve unknown billing
and in-flight states; SDK-calculated cost is not a provider invoice.
"""
from collections import Counter
import datetime
import hashlib
import json
from pathlib import Path

ROOT = Path('/home/chenkeyi/.local/share/harbor-rsi/qwen35-new-cf500-tmax500-20261029')


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                    separators=(',', ':')).encode()).hexdigest()


def main():
    now = datetime.datetime.now(datetime.timezone.utc)
    identity = now.strftime('%Y%m%dT%H%M%SZ')
    destination = ROOT / 'stage2' / ('request-accounting-' + identity)
    destination.mkdir(exist_ok=False)
    attempt_counts = Counter()
    totals = Counter()
    requests_path = destination / 'requests.jsonl'
    attempts_path = destination / 'attempts.jsonl'
    with requests_path.open('x') as requests, attempts_path.open('x') as attempts:
        for path in sorted((ROOT / 'jobs').glob('*/config.json')):
            config = json.loads(path.read_text())
            if config.get('install_only') or not any(
                a.get('name') == 'open-harness' for a in config.get('agents', [])
            ):
                continue
            assert config.get('n_attempts', 1) == 1
            assert config.get('retry', {}).get('max_retries', 0) == 0
            native_trials = {}
            for trial in path.parent.iterdir():
                trial_config = trial / 'config.json'
                if not trial.is_dir() or not trial_config.exists():
                    continue
                settings = json.loads(trial_config.read_text())
                task_path = settings.get('task', {}).get('path')
                if task_path:
                    native_trials.setdefault(task_path, []).append(trial)
            for task in config['tasks']:
                task_path = task['path']
                task_id = Path(task_path).name
                attempt_counts[task_id] += 1
                record = dict(job_id=path.parent.name, task_id=task_id,
                    task_path=task_path, observed_attempt_id=digest([path.parent.name, task_path]),
                    job_config_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                    observed_at=now.isoformat(), debited_reserved_attempts=1,
                    result_status='SUBMITTED_RESULT_NOT_OBSERVED', recorder_files=[],
                    native_dispatch_not_proof_of_http_request=True)
                matched = native_trials.get(task_path, [])
                if len(matched) > 1:
                    raise ValueError('Multiple native trials for a one-attempt task')
                if matched:
                    trial = matched[0]
                    record['trial_directory'] = str(trial)
                    result_path = trial / 'result.json'
                    if result_path.exists():
                        result = json.loads(result_path.read_text())
                        verifier = result.get('verifier_result') or {}
                        record.update(result_status='RESULT_PRESENT', trial_id=result.get('id'),
                            started_at=result.get('started_at'), finished_at=result.get('finished_at'),
                            result_sha256=hashlib.sha256(result_path.read_bytes()).hexdigest(),
                            raw_reward=(verifier.get('rewards') or {}).get('reward'),
                            verifier_return_code=verifier.get('return_code'),
                            exception_type=(result.get('exception_info') or {}).get('exception_type'))
                        totals['terminal_results'] += 1
                    for events in sorted((trial / 'agent' / 'openharness-rollout').glob('events.jsonl')):
                        calls = {}
                        hasher = hashlib.sha256()
                        event_counts = Counter()
                        malformed = []
                        with events.open('rb') as stream:
                            for number, raw in enumerate(stream, 1):
                                hasher.update(raw)
                                try:
                                    event = json.loads(raw)
                                except ValueError:
                                    malformed.append(number)
                                    continue
                                kind = event.get('type')
                                event_counts[kind] += 1
                                if kind not in ('call_start', 'call_payload', 'call_end'):
                                    continue
                                data = event.get('data') or {}
                                call_id = data['call_id']
                                call = calls.setdefault(call_id, dict(call_id=call_id,
                                    task_id=task_id, job_id=path.parent.name,
                                    recorder=str(events), payload_events=[], usage=None))
                                if kind == 'call_start':
                                    model = data.get('model')
                                    if isinstance(model, dict):
                                        model = {key: model.get(key) for key in ('id', 'name', 'api', 'provider')}
                                    call.update(start_event_line=number, source=data.get('source'),
                                        recorder_attempt=data.get('attempt'), retry_of=data.get('retry_of'),
                                        model=model, started_at=event.get('timestamp'))
                                elif kind == 'call_payload':
                                    payload = data.get('payload') or {}
                                    call['payload_events'].append(dict(line=number,
                                        payload_sha256=digest(payload), model=payload.get('model'),
                                        tool_schema_sha256=digest(payload.get('tools'))))
                                else:
                                    response = data.get('response') or {}
                                    call.update(end_event_line=number, status=data.get('status'),
                                        finished_at=event.get('timestamp'), usage=response.get('usage'),
                                        provider_response_id=response.get('responseId'),
                                        error_present=bool(data.get('error')))
                        for call in calls.values():
                            usage = call.get('usage') or {}
                            totals['recorder_calls'] += 1
                            totals['observed_payload_events'] += len(call['payload_events'])
                            totals['retry_linked_calls'] += bool(call.get('retry_of'))
                            totals['calls_with_usage'] += bool(usage)
                            totals['calls_without_usage'] += not bool(usage)
                            for field in ('input', 'output', 'reasoning', 'cacheRead', 'cacheWrite'):
                                value = usage.get(field)
                                if isinstance(value, (int, float)):
                                    totals['usage_' + field] += value
                            cost = (usage.get('cost') or {}).get('total')
                            if isinstance(cost, (int, float)):
                                totals['sdk_estimated_cost'] += cost
                            requests.write(json.dumps(call, ensure_ascii=False) + '\n')
                        record['recorder_files'].append(dict(path=str(events),
                            observed_content_sha256=hasher.hexdigest(), events=dict(event_counts),
                            malformed_lines=malformed, run_end_observed=event_counts['run_end'] > 0))
                attempts.write(json.dumps(record, ensure_ascii=False) + '\n')
    summary = dict(observed_at=now.isoformat(), totals=dict(totals),
        submitted_attempts=sum(attempt_counts.values()), independent_tasks=len(attempt_counts),
        max_submitted_attempts_per_task=max(attempt_counts.values(), default=0),
        numeric_caps_satisfied=sum(attempt_counts.values()) <= 2000 and len(attempt_counts) <= 1000
            and max(attempt_counts.values(), default=0) <= 2,
        setup_failures_count_as_attempts=True, configured_dispatches_reserved_conservatively=True,
        request_ledger=str(requests_path), attempt_ledger=str(attempts_path),
        unknown_provider_invoice=True, sdk_cost_is_estimate_not_confirmed_charge=True,
        all_http_transport_retries_captured='UNVERIFIED_WHEN_NATIVE_TOKEN_OBSERVATION_DISABLED',
        monetary_hard_cap_value='NOT_RECOVERED_FROM_REVIEWED_MANIFESTS',
        new_jobs_submitted=0, approval_written=False,
        scope='All observed native teacher jobs in this campaign; no source data modified')
    (destination / 'SUMMARY.json').write_text(json.dumps(summary, indent=2))
    (ROOT / 'checks' / 'native-request-accounting-latest.json').write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary), flush=True)


if __name__ == '__main__':
    main()
