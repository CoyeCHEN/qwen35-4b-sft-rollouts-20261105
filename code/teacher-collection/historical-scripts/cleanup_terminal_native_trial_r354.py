"""Recover cleanup through the existing RemoteDocker lifecycle, exact terminal zero-model scope only."""
import json
from pathlib import Path, PurePosixPath
import shlex
import tomllib

from harbor.environments.factory import EnvironmentFactory
from harbor.models.task.config import TaskConfig
from harbor.models.trial.config import TrialConfig
from harbor.models.trial.paths import TrialPaths
import collection_readiness_r20 as n


async def cleanup(trial, destination):
    trial = Path(trial)
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=False)
    result = json.loads((trial / 'result.json').read_text())
    config = TrialConfig.model_validate_json((trial / 'config.json').read_text())
    if not result.get('finished_at') or (result.get('agent_execution') and config.agent.name != 'nop'):
        raise ValueError('Cleanup recovery requires a terminal pre-Agent or explicit zero-model NOP Trial')
    if (trial / 'agent/openharness-rollout/events.jsonl').exists():
        raise ValueError('Preserve unexpected Teacher Recorder evidence')
    for line in (n.R / 'stream/collection-r4/teacher-lifecycle.jsonl').open():
        event = json.loads(line)
        if event['event'] == 'TEACHER_ADMITTED' and event['trial_name'] == trial.name:
            raise ValueError('Never adopt an admitted Teacher for setup cleanup')
    if config.environment.kwargs['endpoint'] != n.DEPLOYMENT['environment']['kwargs']['endpoint'] or config.environment.kwargs['remote_socket_path'] != n.NODE['socket']:
        raise ValueError('Terminal Trial is outside the accepted private17 Engine')
    evidence, = trial.glob('remote-docker-*.jsonl')
    events = [json.loads(line) for line in evidence.read_text().splitlines()]
    old = events[0]
    identity = old['identity']
    expected = config.environment.kwargs['project_namespace'] + '-' + identity
    if old['project'] != expected or any(item['identity'] != identity or item['project'] != expected or item['workspace'] != old['workspace'] for item in events):
        raise ValueError('Original native identity is inconsistent')
    connected = [item for item in events if item['action'] == 'connected']
    if not connected or any(item['daemon_id'] != n.NODE['engine_id'] for item in connected):
        raise ValueError('Original connected Engine identity differs')
    if old['workspace'] != n.DEPLOYMENT['environment']['kwargs']['staging_root'] + '/' + expected:
        raise ValueError('Original native workspace is outside the accepted SSD root')
    task = Path(config.task.path)
    resources = TaskConfig.model_validate(tomllib.loads((task / 'task.toml').read_text())).environment
    env = EnvironmentFactory.create_environment_from_config(config=config.environment, environment_dir=task / 'environment',
        environment_name=trial.name, session_id=old['session_id'],
        trial_paths=TrialPaths(trial_dir=destination / 'native-cleanup'), task_env_config=resources)
    # Restore only the exact original ownership identity; start/exec are never invoked.
    env.identity = identity
    env.project = expected
    env.workspace = PurePosixPath(old['workspace'])
    env.evidence = destination / 'remote-docker-cleanup.jsonl'
    await env._connect()
    before = await env._resources()
    for cid in before['container']:
        top = await env._run(env._docker('top', cid, '-eo', 'pid,stat,args'))
        for line in (top.stdout or '').splitlines():
            if '--prompt-file' in line and 'open-harness' in line:
                raise ValueError('Preserve unexpected live Teacher CLI')
    exists = await env._shell('test -d ' + shlex.quote(old['workspace']), check=False)
    if exists.return_code not in (0, 1):
        raise ValueError('Original workspace existence is unknown')
    env._workspace_created = exists.return_code == 0
    await env.stop(delete=True)
    after = await env._resources()
    if any(after.values()):
        raise ValueError('Scoped native cleanup did not complete')
    out = dict(passed=True, trial=str(trial), result_sha256=n.sha(trial / 'result.json'),
        original_evidence_sha256=n.sha(evidence), identity=identity, engine_id=n.NODE['engine_id'],
        before=before, after=after, native_cleanup_evidence=str(env.evidence),
        model_calls=0, teacher_or_verifier_signals=0, original_result_or_recorder_changes=0,
        source_sha256=n.sha(Path(__file__)))
    n.freeze(destination / 'ACCEPTANCE.json', out)
    return out
