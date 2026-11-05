"""Existing engineering fixture via native Harbor, actual R5 CLI/model and Recorder.

This is outside the801 benchmark and all teacher attempts. It never promotes a
deployment or starts another campaign controller.
"""
import asyncio
import copy
import hashlib
import json
import os
from pathlib import Path
import shlex
import subprocess
import time
import urllib.request

from harbor.job import Job
from harbor.models.job.config import JobConfig
from foundation.rollouts.export import RolloutView

R = Path('/ssd/chenkeyi/qwen35-sft-772-20261101')
E = R / 'formal-native-eval-r1'
A = Path('/home/chenkeyi/.local/share/harbor-rsi/qwen35-new772-tb21-20261101')
WHEEL = '1d27eef1ca6696275f306d8c653f7a266a4c7aea7321f0d47fd01b739c27fa18'
MODEL = 'qwen35-new772-new-m1-epoch3-fixed'


def read(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def model_info():
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open('http://127.0.0.1:18303/model_info', timeout=10) as response:
        return json.loads(response.read())


async def main():
    deployment = read(R / 'configs/formal-controller18-deployment-candidate-r1.json')
    assert deployment['activated'] is False
    assert read(R / 'checks/FORMAL_CONTROLLER18_NATIVE_NOP_ACCEPTANCE_R2.json')['passed']
    os.environ['PATH'] = deployment['transport']['private_client_bin'] + ':' + os.environ['PATH']
    os.environ['TMPDIR'] = str(R / 'tmp')
    os.environ['OPENAI_API_KEY'] = 'node18-local'
    ssh = ['ssh', '-p', '18449', 'chenkeyi@127.0.0.1']
    fixture = E / 'diagnostics/native-interop-fixture-r2'
    source = str(A / 'diagnostics/native-interop-fixture-r2')
    remote_program = "import pathlib,hashlib,json;p=pathlib.Path(" + repr(source) + ");" + \
        "print(json.dumps({str(f.relative_to(p)):hashlib.sha256(f.read_bytes()).hexdigest()"
    remote_program += "for f in sorted(p.rglob(\"*\"))if f.is_file()}))"
    source_hashes = json.loads(subprocess.check_output(ssh + ['python3', '-c',
        shlex.quote(remote_program)], text=True, timeout=20))
    assert source_hashes
    if not fixture.exists():
        fixture.mkdir()
        subprocess.run(['/usr/bin/rsync', '-a', '-e',
            '/usr/bin/ssh -F ' + deployment['transport']['ssh_configuration'],
            'chenkeyi@127.0.0.1:' + source + '/', str(fixture) + '/'], check=True, timeout=90)
    assert source_hashes == {str(p.relative_to(fixture)): sha(p)
        for p in sorted(fixture.rglob('*')) if p.is_file()}
    before = model_info()
    assert before['weight_version'] == '2e02fec581cbb3c802cd1e0e80ac2c9568bead3a9002338f4d661ea6ac94053d'
    assert before['model_path'] == str(R / 'epoch-models/new-m1-epoch3')
    cfg = read(A / 'configs/formal-native-job-r2.json')
    agent = copy.deepcopy(cfg['agents'][1])
    agent['model_name'] = 'openai/' + MODEL
    agent['override_timeout_sec'] = 300
    agent['kwargs']['config']['model'].update(id=MODEL,
        name='Qwen3.5-4B NEW-M1 E3 engineering acceptance', baseUrl='http://172.17.0.1:18303/v1')
    assert agent['kwargs']['wheel_sha256'] == WHEEL
    assert sha(Path(agent['kwargs']['wheel_path'])) == WHEEL
    cfg.update(job_name='formal-controller18-r5-native-interop-r1',
        jobs_dir=str(E / 'diagnostics'), n_attempts=1, n_concurrent_trials=1,
        tasks=[dict(path=str(A / 'diagnostics/native-interop-fixture-r2'))], agents=[agent],
        retry=dict(max_retries=0))
    cfg['environment']['kwargs'].update(endpoint=deployment['task_engine']['native_endpoint'],
        staging_root=deployment['task_engine']['staging_root'], project_namespace='q35formal18joint')
    directory = E / 'diagnostics' / cfg['job_name']
    assert not directory.exists(), 'Preserve an existing actual attempt; do not redispatch'
    engine = subprocess.check_output(['docker', '--host', deployment['task_engine']['native_endpoint'],
        'info', '--format', '{{.ID}}'], text=True, timeout=20).strip()
    assert engine == deployment['task_engine']['id']
    started = time.time()
    job = await Job.create(JobConfig.model_validate(cfg))
    result = await job.run()
    assert len(result.trial_results) == 1
    files = list(directory.glob('*/result.json'))
    assert len(files) == 1
    path = files[0]
    raw = read(path)
    assert raw.get('exception_info') is None and not raw.get('infrastructure_errors'), raw
    assert raw['verifier_result']['rewards']['reward'] == 1
    assert raw['verifier_result']['return_code'] == 0
    artifact = read(path.parent / 'agent/artifact.json')
    assert artifact['wheel_sha256'] == WHEEL
    rollout = path.parent / 'agent/openharness-rollout'
    view = RolloutView.open(rollout)
    validation = view.validate()
    assert validation['complete'] and all(r['status'] == 'completed' for r in validation['runs'])
    events = [json.loads(line) for line in (rollout / 'events.jsonl').open()]
    starts = [e for e in events if e['type'] == 'call_start' and e['data']['source'] == 'agent']
    tools = [e for e in events if e['type'] == 'tool_start']
    assert len(starts) >= 3
    from foundation.rollouts.export import loadValue
    first = next(e for e in events if e['type'] == 'call_payload'
        and e['data']['call_id'] == starts[0]['data']['call_id'])
    payload = loadValue(first['data']['payload'], rollout / 'artifacts')
    request = payload.get('request', payload)
    names = {t['function']['name'] for t in request['tools']}
    assert names == {'read', 'bash', 'edit', 'write', 'grep', 'find', 'ls',
        'edit_patch', 'trajectory_read', 'bash_job', 'finish'}
    assert request['max_tokens'] == 81920 and request['chat_template_kwargs']['enable_thinking']
    assert model_info() == before, 'A running model must not be replaced for acceptance'
    assert source_hashes == {str(p.relative_to(fixture)): sha(p)
        for p in sorted(fixture.rglob('*')) if p.is_file()}
    assert path.stat().st_dev == R.stat().st_dev and path.resolve() == path
    proof = dict(passed=True, at=time.time(), started_at=started,
        kind='NATIVE_CONTROLLER18_REAL_R5_MODEL_CLI_VERIFIER_RECORDER_JOINT',
        job_id=str(result.id), trial_id=raw['id'], result_path=str(path), result_sha256=sha(path),
        engine_id=engine, task_engine='149', controller_and_logs_node='18',
        all_local_hot_results_physical_ssd=True, actual_model=before,
        actual_model_calls=len(starts), actual_tool_calls=len(tools), tool_names=sorted(names),
        wheel_sha256=WHEEL, reward=raw['verifier_result']['rewards'], recorder=validation,
        events_sha256=sha(rollout/'events.jsonl'), original_fixture_files_sha256=source_hashes,
        synthetic_fixture_excluded_from_formal801_and_teacher=True,
        deployment_promoted=False, official_task_verifier_or_reward_modified=False,
        training_or_existing_e3_jobs_restarted=False, source_sha256=sha(Path(__file__)))
    output = R / 'checks/FORMAL_CONTROLLER18_NATIVE_JOINT_ACCEPTANCE_R1.json'
    assert not output.exists()
    output.write_text(json.dumps(proof, indent=2) + '\n')
    print(json.dumps(proof), flush=True)


if __name__ == '__main__':
    asyncio.run(main())
