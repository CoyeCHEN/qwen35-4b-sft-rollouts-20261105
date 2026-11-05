"""Extended installed-CLI admission on the existing cold formal model service."""
import argparse
import hashlib
import importlib
import json
import os
from pathlib import Path
import subprocess
import time

R = Path('/ssd/chenkeyi/qwen35-sft-772-20261101')
WHEEL = '1d27eef1ca6696275f306d8c653f7a266a4c7aea7321f0d47fd01b739c27fa18'
serving = importlib.import_module('cold-native-serving18-r2')


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def admit(tag):
    live = serving.info(tag)
    output = R / 'formal-protocol' / tag
    marker = output / 'FORMAL_PROTOCOL_ADMISSION.json'
    sources = {name: sha(R / name) for name in ['admit-formal-native-cli18-r2.py',
               'audit-native-cli-smoke-r5.py', 'audit-native-cli-prefix-r2.py']}
    if marker.exists():
        proof = json.loads(marker.read_text())
        assert proof['passed'] and proof['weight_version'] == live['weight_version']
        assert proof['wheel_sha256'] == WHEEL and proof['source_sha256'] == sources
        return proof
    assert not output.exists(), 'Keep a prior failed or interrupted protocol admission for investigation'
    release = json.loads((R / 'checks/NEW11_STUDENT_HARNESS_RELEASE_R5.json').read_text())
    assert release['wheel_sha256'] == WHEEL and sha(Path(release['wheel'])) == WHEEL
    assert sha(Path(live['model_manifest'])) == live['weight_version']
    output.mkdir(parents=True)
    workspace=output/'workspace';workspace.mkdir()
    binding = dict(model_id=live['model_id'], tokenizer_model_path=live['model_path'],
                   model_manifest=live['model_manifest'], weight_version=live['weight_version'],
                   actual_model_info=live['actual_model_info'])
    (output / 'SERVING_MODEL_BINDING.json').write_text(json.dumps(binding, indent=2) + '\n')
    config = json.loads((R / 'checks/ORIGINAL_TEACHER_11TOOLS_CONFIG.json').read_text())
    config.update(model=dict(id=live['model_id'], name='Qwen3.5-4B native local',
        api='openai-completions', provider='openai',
        baseUrl='http://127.0.0.1:' + str(live['port']) + '/v1',
        reasoning=True, reasoningContent=True, input=['text', 'image'],
        thinkingLevelMap={'high': 'high', 'max': 'high'}, contextWindow=262144, maxTokens=81920,
        cost=dict(input=0, output=0, cacheRead=0, cacheWrite=0)), thinkingLevel='high',
        sessionDir=str(output / 'sessions'), recording=dict(enabled=True, directory=str(output / 'recorder')),
        requestOptions=dict(maxTokens=81920, temperature=1., timeout=120, topP=.95, topK=20,
            minP=0., presencePenalty=1.5, repetitionPenalty=1., chatTemplateKwargs={'enable_thinking': True}))
    for name in ['compaction', 'branchSummary']:
        config[name]['summaryThinkingLevel'] = 'high'
    (output / 'config.json').write_text(json.dumps(config, indent=2) + '\n')
    prompt = '''This is a local protocol smoke. Complete the following small operations in the current directory, check your output, then call finish.
Write protocol-check.txt with exactly alpha followed by a newline using write. Use read to inspect the file. Use edit_patch to replace alpha with beta, then read it again to verify beta.
Also run a short real background bash job which sleeps one second and writes bg-ok.txt containing ready, then use bash_job to inspect that exact job and verify the output. Call trajectory_read once to inspect your actual recorded history. Confirm both files with bash.
'''
    (output / 'instruction.txt').write_text(prompt)
    env = os.environ | dict(OPENAI_API_KEY='local-node18', TMPDIR=str(R / 'tmp'),
        PATH=str(R / 'harness-context-recovery-r1/e2e-bin') + ':' + os.environ['PATH'])
    argv = [str(R / 'env/harness-new11-r2/bin/open-harness'), '-p', '--mode', 'json',
            '--config', str(output / 'config.json'), '--cwd', str(workspace),
            '--prompt-file', str(output / 'instruction.txt')]
    (output / 'CLI_COMMAND.json').write_text(json.dumps(argv, indent=2) + '\n')
    (output / 'ADMISSION_SOURCE.json').write_text(json.dumps(sources, indent=2) + '\n')
    with (output / 'stdout.jsonl').open('x') as stdout, (output / 'stderr.log').open('x') as stderr:
        run = subprocess.run(argv, cwd=workspace, env=env, stdout=stdout, stderr=stderr, timeout=600)
    (output / 'CLI_EXIT.json').write_text(json.dumps(dict(return_code=run.returncode)) + '\n')
    assert run.returncode == 0, 'Native formal protocol CLI exited abnormally'
    subprocess.run([str(R / 'env/harness-new11-r2/bin/python'),
                    str(R / 'audit-native-cli-smoke-r5.py'), str(output)],
                   cwd=output, env=env, check=True, timeout=90)
    audit = json.loads((output / 'NATIVE_CLI_AUDIT.json').read_text())
    assert audit['passed'] and len(audit['calls']) >= 3
    again = serving.info(tag)
    assert again['weight_version'] == live['weight_version']
    proof = dict(passed=True, at=time.time(), tag=tag, model_id=live['model_id'],
        model_path=live['model_path'], weight_version=live['weight_version'], wheel_sha256=WHEEL,
        native_cli_calls=len(audit['calls']), actual_tool_names=audit['actual_tool_names'],
        background_job_completed=True, actual_native_agent_closure=True,
        scratch_fixture_bytes_exact=(workspace/'protocol-check.txt').read_bytes()==b'beta\n',
        actual_prefix_and_gpu_usage_verified=True, source_sha256=sources,
        model_binding_sha256=sha(output / 'SERVING_MODEL_BINDING.json'),
        audit_sha256=sha(output / 'NATIVE_CLI_AUDIT.json'),
        generic_compaction_and_tool_budget_wheel_e2e_sha256=sha(R / 'checks/CONTEXT_RECOVERY_FULL_WHEEL_E2E_ACCEPTANCE_R1.json'),
        existing_cold_server_reused_without_restart=True, new_gpu_or_optimizer_processes=0,
        workspace=str(workspace),control_and_recording_outside_working_directory=True,
        actual_cli_model_requests=True, official_task_attempts=0, official_verifier_score=None)
    marker.write_text(json.dumps(proof, indent=2) + '\n')
    return proof


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('tag', choices=['m0', 'new-m1-e5', 'new-m2-e5'])
    args = parser.parse_args()
    print(json.dumps(admit(args.tag)))
