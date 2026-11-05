"""Offline installed-wheel proof. This does not replace either real canary."""
import asyncio
import argparse
import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile

from foundation.ai.deepseek import buildPayload
from rsi_modules.controller.sdk import createAgentSession
from rsi_modules.memory.context.budget import SessionToolResultBudget

ROOT = Path(__file__).resolve().parents[1]


def sha(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--summary-r1', action='store_true')
    args = parser.parse_args()
    prefix = 'summary-r1-' if args.summary_r1 else ''
    config_file = ROOT / ('configs/teacher-native-11tools-summary-r1.json' if args.summary_r1
                          else 'configs/teacher-native-11tools.json')
    config = json.loads(config_file.read_text())
    with tempfile.TemporaryDirectory(prefix='cf-tmax-native-contract-') as directory:
        config.update(cwd=directory, sessionDir=directory + '/sessions',
            recording=dict(enabled=True, directory=directory + '/recorder'))
        async with await createAgentSession(**config) as session:
            schemas = [{k: tool[k] for k in ['name', 'description', 'parameters']} for tool in session.state.tools]
            payload = buildPayload(session.state.model, dict(systemPrompt=session.state.systemPrompt,
                messages=[dict(role='user', content='Offline protocol schema probe.')], tools=schemas),
                dict(config['requestOptions'], reasoning='max'))
            names = [t['function']['name'] for t in payload['tools']]
            expected = json.loads((ROOT / 'manifests/TEACHER_CONTRACT_CANDIDATE.json').read_text())['final_tool_names']
            if names != expected or len(set(names)) != 11:
                raise ValueError('Final runtime tool registration differs from the frozen 11-tool contract')
            if payload['thinking'] != {'type': 'enabled'} or payload['reasoning_effort'] != 'max':
                raise ValueError('Thinking contract differs')
            tools = {tool['name']: tool for tool in session.state.tools}
            patched = await tools['edit_patch']['execute']('patch-probe', dict(changes=[
                dict(path='probe.txt', operation='add', content='original\n'),
                dict(path='empty.txt', operation='add', content='')]))
            if patched.get('isError') or Path(directory, 'probe.txt').read_text() != 'original\n':
                raise ValueError('Native structured edit_patch failed')
            launched = await tools['bash']['execute']('job-probe', dict(command='sleep .1; printf job-ok', background=True, timeout=5))
            job_id = launched['details']['job_id']
            waited = await tools['bash_job']['execute']('wait-probe', dict(action='wait', job_id=job_id, wait_seconds=2))
            if 'job-ok' not in json.dumps(waited):
                raise ValueError('Native bash_job did not retain completed output')
            launched2 = await tools['bash']['execute']('cancel-probe', dict(command='sleep 30', background=True, timeout=40))
            cancelled = await tools['bash_job']['execute']('cancel-probe', dict(action='cancel', job_id=launched2['details']['job_id']))
            if 'cancel' not in json.dumps(cancelled):
                raise ValueError('Native bash_job cancellation failed')
            settings = copy.deepcopy(session._config['toolResultBudget'])
            budget = SessionToolResultBudget(settings, baseDir=directory + '/budget-results')
            # Exercise the unchanged production threshold, including error pairing.
            original = [dict(role='toolResult', toolCallId='big-observation', toolName='bash',
                content=[dict(type='text', text='full original output\n' * 20000)], isError=True, timestamp=0)]
            preserved = copy.deepcopy(original)
            visible = budget.project(original)
            saved = list(Path(directory, 'budget-results').glob('*.txt'))
            if original != preserved or len(saved) != 1 or saved[0].read_text() != original[0]['content'][0]['text']:
                raise ValueError('Budget projection lost or altered raw evidence')
            if not visible[0]['isError'] or visible[0]['toolCallId'] != 'big-observation':
                raise ValueError('Budget projection damaged error/call pairing')
            if 'shortened by budget' not in visible[0]['content'][0]['text']:
                raise ValueError('Production budget threshold did not actually offload output')
            (ROOT / 'checks' / (prefix+'OFFLINE_PROVIDER_PAYLOAD.json')).write_text(json.dumps(payload, indent=2))
            (ROOT / 'checks' / (prefix+'TOOL_SCHEMAS.json')).write_text(json.dumps(schemas, indent=2))
            (ROOT / 'checks' / (prefix+'SYSTEM_PROMPT.txt')).write_text(session.state.systemPrompt)
            result = dict(passed=True, scope='OFFLINE installed wheel only; actual service and both benchmark canaries pending',
                installed_module=str(sys.modules['rsi_modules.controller.sdk'].__file__),
                tool_names=names, tool_schema_sha256=sha(schemas),
                system_prompt_sha256=hashlib.sha256(session.state.systemPrompt.encode()).hexdigest(),
                thinking=payload['thinking'], reasoning_effort=payload['reasoning_effort'],
                max_tokens=payload['max_tokens'], stream=payload['stream'], temperature=payload['temperature'],
                effective_tool_result_budget=settings, raw_chars=len(original[0]['content'][0]['text']),
                visible_chars=len(visible[0]['content'][0]['text']), full_raw_preserved=True,
                tool_call_and_error_semantics_preserved=True, legal_offloaded_output_readable=True,
                structured_edit_patch='PASS', background_start_wait_output_cancel='PASS',
                teacher_config_sha256=hashlib.sha256(config_file.read_bytes()).hexdigest(),
                effective_compaction=session._config['compaction'],
                effective_branch_summary=session._config['branchSummary'],
                real_model_calls=0, real_benchmark_attempts=0)
            if args.summary_r1:
                prior=json.loads((ROOT/'checks/offline-teacher-contract.json').read_text())
                for key in ['tool_names','tool_schema_sha256','system_prompt_sha256','effective_tool_result_budget']:
                    if result[key]!=prior[key]:raise ValueError('Unexpected non-summary contract change: '+key)
                for key in ['effective_compaction','effective_branch_summary']:
                    if result[key]['summaryThinkingLevel']!='max' or result[key]['summaryMaxTokens']!=65536:
                        raise ValueError('Explicit summary contract did not take effect')
            (ROOT / 'checks' / (prefix+'offline-teacher-contract.json')).write_text(json.dumps(result, indent=2))
            print(json.dumps(result))


if __name__ == '__main__':
    asyncio.run(main())
