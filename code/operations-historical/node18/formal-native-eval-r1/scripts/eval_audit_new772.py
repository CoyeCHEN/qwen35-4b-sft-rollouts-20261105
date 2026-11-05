"""Read-only Qwen Trial/Verifier/Recorder audit, separate from Harbor scheduling."""
from collections import Counter, defaultdict
import hashlib
import json
import math
from pathlib import Path
import re
import statistics

from foundation.rollouts.export import RolloutView, loadValue
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]
TOOLS = {'read', 'bash', 'edit', 'write', 'grep', 'find', 'ls', 'bash_job', 'trajectory_read', 'edit_patch', 'finish'}


def infrastructure_model_error(message):
    """Classify explicit transport/backend failures, not generated bad tool arguments."""
    text = message.lower()
    return (bool(re.search(r'\b(?:http\s*|status(?: code)?[ :=]*)(?:5\d\d|401|403|429)\b', text))
            or any(value in text for value in ('connection refused', 'connection reset', 'connecterror',
                'readtimeout', 'connecttimeout', 'server disconnected', 'all connection attempts failed')))


def sha(path):
    with Path(path).open('rb') as source:
        return hashlib.file_digest(source, 'sha256').hexdigest()


def inspect_trial(directory):
    directory = Path(directory)
    result = json.loads((directory / 'result.json').read_text())
    verifier = result.get('verifier_result') or {}
    rewards = verifier.get('rewards')
    reward = (rewards or {}).get('reward')
    # A real numeric official reward and successful verifier are both required.
    valid = (isinstance(reward, (int, float)) and not isinstance(reward, bool)
             and math.isfinite(reward) and reward in (0, 1)
             and not result.get('infrastructure_errors') and verifier.get('return_code') == 0)
    row = dict(task_id=result['task_name'], trial_id=str(result['id']), trial_name=result['trial_name'],
               harbor_task_id=result['task_id'], task_checksum=result.get('task_checksum'),
               started_at=result.get('started_at'), finished_at=result.get('finished_at'),
               result_path=str(directory / 'result.json'), result_sha256=sha(directory / 'result.json'),
               reward=rewards, raw_official_score_valid=bool(valid), valid_score=bool(valid), task_success=bool(valid and reward == 1),
               exception_type=(result.get('exception_info') or {}).get('exception_type'),
               failure_phase=result.get('failure_phase'), infrastructure_errors=result.get('infrastructure_errors', []),
               trajectory_complete=False, normal_close=False, protocol_issues=[],
               model_calls=0, tool_calls=0, tool_argument_invalid=0, tool_arguments_valid=0,
               thinking_blocks=0, input_tokens=0, output_tokens=0, model_call_statuses={}, tool_statuses={},
               task_group=None, classification='TB21_EXTERNAL_CF_TMAX_SFT_RESEARCH_LONG3H')
    try:
        root = directory / 'agent/openharness-rollout'
        view = RolloutView.open(root)
        integrity = view.validate()
        calls, tools, runs, contexts = view.rows()
        resolve = lambda v: loadValue(v, root / 'artifacts')
        row.update(session_id=view.manifest['session_id'], recorder_validation=integrity,
                   events_sha256=sha(root / 'events.jsonl'), model_calls=len(calls), tool_calls=len(tools),
                   run_statuses=[r['status'] for r in runs],
                   model_call_statuses=dict(Counter(c.get('status') for c in calls)),
                   model_stop_reasons={}, model_http_error_statuses={}, fatal_model_transport_error=False,
                   tool_statuses=dict(Counter(t.get('status') for t in tools)), image_input_calls=0,
                   compaction_events=0, background_events=0, historical_thinking_messages=0)
        config = json.loads((directory / 'config.json').read_text())
        model_id = config['agent']['kwargs']['config']['model']['id']
        schema_map = {}
        stops, http_errors, agent_responses = Counter(), Counter(), []
        for call in calls:
            response = resolve(call.get('response', {})) or {}
            stops[response.get('stopReason', 'missing')] += 1
            error_message = response.get('errorMessage', '')
            http_errors.update(re.findall(r'\b(?:HTTP\s*|status(?: code)?[ :=]*)([45]\d\d)\b', error_message, flags=re.I))
            if call.get('source') == 'agent':
                agent_responses.append(response)
            usage = response.get('usage') or {}
            row['input_tokens'] += usage.get('input', 0)
            row['output_tokens'] += usage.get('output', 0)
            row['thinking_blocks'] += sum(p.get('type') == 'thinking' and bool(p.get('thinking')) for p in response.get('content', []))
            if 'payload' not in call:
                if call.get('status') not in ('error', 'aborted', 'interrupted'):
                    row['protocol_issues'].append('missing_payload:' + call['call_id'])
                continue
            payload = resolve(call['payload'])
            if call.get('source') != 'agent':
                continue  # Compaction requests are recorded but are not agent decisions.
            expected = dict(model=model_id, max_tokens=81920, temperature=1.0, top_p=.95, top_k=20, min_p=0., presence_penalty=1.5, repetition_penalty=1., chat_template_kwargs={'enable_thinking': True}, stream=True)
            for key, value in expected.items():
                if payload.get(key) != value:
                    row['protocol_issues'].append('payload_' + key + ':' + call['call_id'])
            names = {x['function']['name'] for x in payload.get('tools', [])}
            if names != TOOLS:
                row['protocol_issues'].append('tool_contract:' + call['call_id'])
            for entry in payload.get('tools', []):
                schema_map[entry['function']['name']] = entry['function']['parameters']
            pending = set()
            for message in payload['messages']:
                if message['role'] == 'assistant':
                    if message.get('reasoning_content'):
                        row['historical_thinking_messages'] += 1
                    pending.update(t['id'] for t in message.get('tool_calls', []))
                elif message['role'] == 'tool':
                    ident = message.get('tool_call_id')
                    if ident not in pending:
                        row['protocol_issues'].append('unpaired_tool_result:' + str(ident))
                    pending.discard(ident)
            if pending:
                row['protocol_issues'].append('missing_tool_results:' + call['call_id'])
            row['image_input_calls'] += any(isinstance(m.get('content'), list) and any(c.get('type') == 'image_url' for c in m['content']) for m in payload['messages'])
            for part in response.get('content', []):
                if part.get('type') != 'toolCall':
                    continue
                schema = schema_map.get(part.get('name'))
                args = part.get('arguments')
                try:
                    if isinstance(args, str):
                        args = json.loads(args)
                    if schema is None:
                        raise ValueError('Undeclared tool')
                    Draft202012Validator(schema).validate(args)
                    row['tool_arguments_valid'] += 1
                except Exception:
                    row['tool_argument_invalid'] += 1
        row['model_stop_reasons'] = dict(stops)
        row['model_http_error_statuses'] = dict(http_errors)
        if agent_responses:
            last = agent_responses[-1]
            row['fatal_model_transport_error'] = bool(last.get('stopReason') == 'error' and infrastructure_model_error(last.get('errorMessage', '')))
            if row['fatal_model_transport_error']:
                # Keep the untouched official reward separately; do not label an
                # unrecovered API/transport failure a normal model zero.
                row['valid_score'] = False
                row['task_success'] = False
                row['diagnostic_exclusion_reason'] = 'UNRECOVERED_MODEL_TRANSPORT_OR_BACKEND_FAILURE'
        for context in contexts:
            event = resolve(context['data'].get('event', {})) or {}
            kind = event.get('type', '')
            row['compaction_events'] += 'compaction' in kind
            row['background_events'] += kind.startswith('background_job_')
        sessions = []
        for path in (directory / 'agent/openharness-sessions').rglob('*.jsonl'):
            ended = False
            with path.open() as stream:
                for line in stream:
                    ended |= json.loads(line).get('type') == 'run_end'
            sessions.append(dict(path=str(path), sha256=sha(path), run_end=ended))
        marker = directory / 'agent/open-harness.complete.json'
        exit_code = json.loads(marker.read_text())['exit_code'] if marker.exists() else None
        row['cli_exit_code'] = exit_code
        row['session_files'] = sessions
        row['normal_close'] = bool(exit_code == 0 and runs and all(r['status'] == 'completed' for r in runs) and any(s['run_end'] for s in sessions))
        row['trajectory_complete'] = bool(integrity['complete'] and row['normal_close'] and not row['protocol_issues'])
    except Exception as error:
        row['audit_error'] = type(error).__name__ + ': ' + str(error)
    return row


def raw_success(row):
    return row.get('raw_official_score_valid', False) and (row.get('reward') or {}).get('reward') == 1


def summary(rows, expected):
    return dict(expected=expected, terminal=len(rows), unique_tasks=len({r['task_id'] for r in rows}),
                valid_scores=sum(r['valid_score'] for r in rows), successes=sum(r['task_success'] for r in rows),
                normal_close=sum(r['normal_close'] for r in rows),
                trajectory_complete=sum(r['trajectory_complete'] for r in rows),
                agent_timeouts=sum(r['exception_type'] == 'AgentTimeoutError' for r in rows),
                infrastructure_failures=sum(bool(r['infrastructure_errors']) for r in rows),
                unrecovered_model_transport_errors=sum(r.get('fatal_model_transport_error', False) for r in rows),
                raw_official_scores=sum(r.get('raw_official_score_valid', False) for r in rows),
                raw_official_reward_successes=sum(raw_success(r) for r in rows),
                protocol_failures=sum(bool(r['protocol_issues']) for r in rows),
                audit_errors=sum('audit_error' in r for r in rows),
                tool_arguments_valid=sum(r['tool_arguments_valid'] for r in rows),
                tool_argument_invalid=sum(r['tool_argument_invalid'] for r in rows),
                exception_types=dict(Counter(r['exception_type'] for r in rows)),
                raw_success_rate=sum(raw_success(r) for r in rows) / expected,
                diagnostic_success_lower_bound=sum(r['task_success'] for r in rows) / expected,
                valid_score_coverage=sum(r['valid_score'] for r in rows) / expected,
                diagnostic_valid_success_rate=(sum(r['task_success'] for r in rows) / sum(r['valid_score'] for r in rows)) if any(r['valid_score'] for r in rows) else None)


def audit_job(job_dir, destination, expected):
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    rows = [inspect_trial(p.parent) for p in sorted(Path(job_dir).glob('*/result.json'))]
    (destination / 'trials.jsonl').write_text(''.join(json.dumps(r) + '\n' for r in rows))
    result = summary(rows, expected)
    (destination / 'summary.json').write_text(json.dumps(result, indent=2) + '\n')
    return result


def aggregate():
    rows_by_model = {}
    groups = json.loads((ROOT / 'manifests/m2-task-groups.json').read_text())
    for model in ('m1', 'm2'):
        rows = []
        for phase in ('r1', 'r2-r5'):
            p = ROOT / 'evidence' / (model + '-' + phase + '-audit') / 'trials.jsonl'
            if p.exists():
                for line in p.open():
                    row = json.loads(line)
                    row['phase'] = phase
                    row['task_group'] = 'M2_TRAIN' if row['task_id'] in groups['train'] else 'M2_VALIDATION' if row['task_id'] in groups['validation'] else 'M2_NOT_SEEN'
                    rows.append(row)
        rows_by_model[model] = rows
        if len({r['trial_id'] for r in rows}) != len(rows):
            raise ValueError('Duplicate confirmed Trial UUID; original results preserved')
    result = dict(classification='TB21_EXTERNAL_CF_TMAX_SFT_RESEARCH_LONG3H', models={})
    for model, rows in rows_by_model.items():
        per_task = defaultdict(list)
        for row in rows:
            per_task[row['task_id']].append(row)
        per_task_stats = {task: dict(attempts=len(rs), valid=sum(r['valid_score'] for r in rs),
            successes=sum(r['task_success'] for r in rs), raw_success_rate=sum(raw_success(r) for r in rs) / 5,
            raw_official_successes=sum(raw_success(r) for r in rs),
            pass_at_5=any(raw_success(r) for r in rs) if len(rs) == 5 else None,
            individual_rewards=[r['reward'] for r in rs], trial_ids=[r['trial_id'] for r in rs],
            group=rs[0]['task_group']) for task, rs in per_task.items()}
        complete_five = len(per_task) == 89 and all(len(rs) == 5 for rs in per_task.values())
        rates = [v['raw_success_rate'] for v in per_task_stats.values()]
        repeated_rates = None
        if complete_five:
            repeated = [[] for _ in range(5)]
            for rs in per_task.values():
                first = [r for r in rs if r['phase'] == 'r1']
                later = [r for r in rs if r['phase'] == 'r2-r5']
                if len(first) != 1 or len(later) != 4 or any(not r['started_at'] for r in later):
                    raise ValueError('Native Trial start identities do not establish five independent attempts')
                ordered = first + sorted(later, key=lambda r: (r['started_at'], r['trial_id']))
                for index, row in enumerate(ordered):
                    repeated[index].append(row)
            repeated_rates = [summary(rs, 89) for rs in repeated]
        result['models'][model] = dict(first_round=summary([r for r in rows if r['phase'] == 'r1'], 89),
            all_trials=summary(rows, 445), complete_five=complete_five,
            pass_at_5=sum(any(raw_success(r) for r in rs) for rs in per_task.values()) / 89 if complete_five else None,
            mean_single_attempt_success=sum(raw_success(r) for r in rows) / 445 if complete_five else None,
            independent_repeat_rates=repeated_rates,
            independent_repeat_success_rate_std=statistics.pstdev(r['raw_success_rate'] for r in repeated_rates) if repeated_rates else None,
            across_task_single_attempt_rate_std=statistics.pstdev(rates) if complete_five else None,
            variation_scope='Actual first-pass Trial plus later per-task independent Trials ordered by native started_at; never selected by completion order or reward. Also reports per-task fractions.',
            per_task=per_task_stats,
            groups={g: summary([r for r in rows if r['task_group'] == g], n * 5) for g, n in [('M2_TRAIN', 59), ('M2_VALIDATION', 3), ('M2_NOT_SEEN', 27)]})
    result['paired_tasks'] = {t: {m: result['models'][m]['per_task'].get(t) for m in ('m1', 'm2')}
                              for t in set().union(*(set(x['per_task']) for x in result['models'].values()))}
    (ROOT / 'evidence/comparison.json').write_text(json.dumps(result, indent=2) + '\n')
    return result
