"""Verify the completed native install-only Job; never execute an agent or verifier."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time
import tomllib

from harbor.models.task.config import TaskConfig
from harbor.models.trial.config import VerifierConfig

R = Path('/home/chenkeyi/.local/share/harbor-rsi/qwen35-new772-tb21-20261101')
WHEEL = '1d27eef1ca6696275f306d8c653f7a266a4c7aea7321f0d47fd01b739c27fa18'


def read(p):
    return json.loads(p.read_text())


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    output = R / 'checks/NEW11_ALL89_INSTALL_ACCEPTANCE_R1.json'
    assert not output.exists(), 'Keep the completed acceptance immutable'
    marker = R / 'checks/NEW11_INSTALL_PREFLIGHT_ALL_TERMINAL_R1.json'
    complete = read(marker)
    status_path = R / 'checks/NEW11_INSTALL_PREFLIGHT_STATUS_R1.json'
    status = read(status_path)
    assert complete['passed'] and complete['terminal'] == complete['ready'] == 89
    assert complete['status_sha256'] == sha(status_path)
    identities = read(R / 'manifests/OFFICIAL_89_TASK_IDENTITIES.json')['tasks']
    identities = {x['task_id']: x for x in identities}
    assert len(identities) == len(status['rows']) == 89
    job = R / 'jobs/qwen35-new772-new11-install-preflight'
    uuids, tasks, rows = set(), set(), []
    for recorded in status['rows']:
        task_id = recorded['task_id']
        identity = identities[task_id]
        directory = job / recorded['trial_name']
        result_path, config_path = directory / 'result.json', directory / 'config.json'
        result, config = read(result_path), read(config_path)
        assert recorded['result_sha256'] == sha(result_path)
        assert result['trial_name'] == directory.name
        assert result['id'] not in uuids and task_id not in tasks
        uuids.add(result['id']); tasks.add(task_id)
        assert config['install_only'] and result['config']['install_only']
        assert result['agent_execution'] is None and result['agent_result'] is None
        assert result['verifier'] is None and result['verifier_result'] is None
        assert result['exception_info'] is None and not result['infrastructure_errors']
        assert result['environment_setup']['finished_at'] and result['agent_setup']['finished_at']
        assert not (directory / 'agent/openharness-rollout/events.jsonl').exists()
        artifact = directory / 'agent/artifact.json'
        assert read(artifact)['wheel_sha256'] == config['agent']['kwargs']['wheel_sha256'] == WHEEL
        assert sha(artifact) == recorded['install_artifact_sha256']
        source = Path(identity['path'])
        assert str(source) == config['task']['path']
        assert sha(source / 'instruction.md') == identity['instruction_sha256']
        assert sha(source / 'task.toml') == identity['task_toml_sha256']
        task = TaskConfig.model_validate(tomllib.loads((source / 'task.toml').read_text()))
        assert config['agent']['override_timeout_sec'] == max(10800, task.agent.timeout_sec)
        verifier = VerifierConfig.model_validate(config['verifier'])
        assert verifier.override_timeout_sec is None and verifier.max_timeout_sec is None
        assert all(config['environment'].get(k) is None for k in
                   ['override_cpus', 'override_memory_mb', 'override_storage_mb', 'override_gpus'])
        composed = list(directory.glob('remote-docker-*.compose.json'))
        assert len(composed) == 1
        main_service = read(composed[0])['services']['main']
        assert main_service['cpus'] == task.environment.cpus
        assert int(main_service['mem_limit']) == task.environment.memory_mb * 1024 ** 2
        assert main_service['image'] == task.environment.docker_image
        rg = [v for v in main_service['volumes'] if v['target'] == '/usr/local/bin/rg']
        assert len(rg) == 1 and rg[0]['type'] == 'bind' and rg[0]['read_only']
        rows.append(dict(task_id=task_id, trial_id=result['id'], trial_name=directory.name,
                         result_sha256=sha(result_path), config_sha256=sha(config_path),
                         compose_sha256=sha(composed[0]), artifact_sha256=sha(artifact),
                         official_cpus=task.environment.cpus,
                         official_memory_mb=task.environment.memory_mb,
                         original_task_image=task.environment.docker_image,
                         actual_agent_model_attempts=0, official_verifier_scores=0))
    os.environ['SSH_AUTH_SOCK'] = str(R.parent / 'near-r3-20261015/auth.sock')
    engine = subprocess.check_output(['docker', '--host', 'ssh://chenkeyi@127.0.0.1:5102',
                                      'info', '--format', '{{.ID}}'], text=True, timeout=30).strip()
    assert engine == 'c6e16cdf-e878-4cc5-84c8-78a56c54b5c5'
    proof = dict(passed=True, at=time.time(), distinct_tasks=len(tasks), distinct_native_trials=len(uuids),
                 official_engine_id=engine, wheel_sha256=WHEEL,
                 native_install_only=True, actual_agent_model_attempts=0, official_verifier_scores=0,
                 no_new_trials_dispatched=True, official_resources_unchanged=True,
                 original_task_public_files_sha_verified=True, readonly_public_rg_bind_verified=True,
                 verifier_execution_claimed=False, model_success_claimed=False,
                 native_completion_marker_sha256=sha(marker), native_status_sha256=sha(status_path),
                 source_sha256=sha(Path(__file__)), rows=rows)
    output.write_text(json.dumps(proof, indent=2) + '\n')
    print(json.dumps({k: v for k, v in proof.items() if k != 'rows'}))


if __name__ == '__main__':
    main()
