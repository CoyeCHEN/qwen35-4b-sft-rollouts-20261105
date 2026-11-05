"""One terminal r002 identity only: preserve staging, then use native provider.stop."""
import asyncio
import hashlib
import inspect
import json
import os
from pathlib import Path, PurePosixPath
import shlex
import time

from harbor.environments.factory import EnvironmentFactory
from harbor.models.task.task import Task
from harbor.models.trial.config import TrialConfig
from harbor.models.trial.paths import TrialPaths
import harbor_remote_docker.environment as provider

R = Path('/ssd/chenkeyi/qwen35-sft-772-20261101')
B = R / 'synthetic32/cleanup-fixcode-r002-terminal-r1'
C = Path('/data/chenkeyi/qwen35-sft-772-20261101/control')
TASKS = {'fix-code-vulnerability--r002--openharness'}


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def read(path):
    return json.loads(path.read_text())


def save(path, value):
    assert not path.exists(), path
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.partial')
    with temporary.open('x') as stream:
        json.dump(value, stream, indent=2)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())
    temporary.rename(path)


def protected(directory):
    # This snapshot includes the entire original Recorder, not only its manifest.
    return {str(p): sha(p) for p in directory.rglob('*') if p.is_file()}


ARCHIVE = r'''
from pathlib import Path
import hashlib,json,os,sys,tarfile
w=Path(sys.argv[1]);identity=sys.argv[2];expected=json.loads(sys.argv[3]);dest=Path(sys.argv[4])
assert w.resolve()==w and w.is_dir() and w.joinpath('.identity').read_text()==identity
actual={str(p.relative_to(w)):p for p in w.rglob('*')}
assert set(actual)=={x['path'] for x in expected}
for item in expected:
 p=actual[item['path']];assert not p.is_symlink()
 if item['directory']:assert p.is_dir()
 else:
  assert p.is_file() and p.stat().st_size==item['bytes']
  assert hashlib.sha256(p.read_bytes()).hexdigest()==item['sha256']
assert not dest.exists();dest.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
temporary=dest.with_suffix('.partial');assert not temporary.exists()
with temporary.open('xb') as f:
 os.chmod(temporary,0o600)
 with tarfile.open(fileobj=f,mode='w') as t:
  for item in expected:t.add(actual[item['path']],arcname=item['path'],recursive=False)
 f.flush();os.fsync(f.fileno())
assert temporary.stat().st_size<=67108864
with tarfile.open(temporary)as t:
 assert set(t.getnames())==set(actual)
 for item in expected:
  if not item['directory']:
   assert hashlib.sha256(t.extractfile(item['path']).read()).hexdigest()==item['sha256']
os.replace(temporary,dest)
fd=os.open(dest.parent,os.O_RDONLY);os.fsync(fd);os.close(fd)
print(json.dumps(dict(archive=str(dest),sha256=hashlib.sha256(dest.read_bytes()).hexdigest(),bytes=dest.stat().st_size,verified_members=expected,source_identity=identity)))
'''


async def unused_resources(env, item):
    resources = await env._resources()
    assert not resources['container'], 'A container reappeared; stop for identity review'
    assert set(resources['network']) <= set(item['resources']['network'])
    assert set(resources['volume']) <= set(item['resources']['volume'])
    for volume in resources['volume']:
        refs = await env._run(env._docker('ps', '-aq', '--filter', 'volume=' + volume))
        assert not refs.stdout.strip(), 'Volume has a container reader'
    for network in resources['network']:
        detail = json.loads((await env._run(env._docker('network', 'inspect', network))).stdout)
        assert len(detail) == 1 and not detail[0].get('Containers')
    return resources


async def clean(plan, item):
    directory = Path(item['original_result_path']).parent
    assert sha(directory / 'result.json') == item['original_result_sha256']
    raw = read(directory / 'result.json')
    assert raw['id'] == item['native_trial_id'] and raw['finished_at']
    assert raw['verifier_result']['return_code'] == 0 and raw['verifier_result']['rewards']['reward'] == 0
    assert any(e['phase'] == 'cleanup' and e['exception_info']['exception_type'] == 'TimeoutError'
               for e in raw['infrastructure_errors'])
    original_log = Path(item['original_provider_log']['path'])
    assert sha(original_log) == item['original_provider_log']['sha256']
    record = json.loads(original_log.open().readline())
    assert (record['identity'], record['project'], record['workspace']) == (
        item['identity'], item['project'], item['workspace']['workspace'])
    before_files = protected(directory)
    identity = item['identity']
    result = dict(task_id=item['task_id'], native_trial_id=raw['id'], identity=identity,
                  original_file_sha256=before_files, model_or_Verifier_calls=0)
    try:
        async with asyncio.timeout(300):
            cfg = TrialConfig.model_validate(raw['config'])
            task = Task(cfg.task.path)
            paths = TrialPaths(B / 'native-evidence' / identity)
            paths.mkdir()
            env = EnvironmentFactory.create_environment_from_config(
                cfg.environment, environment_dir=task.paths.environment_dir,
                environment_name=task.short_name, session_id='terminal-aux-cleanup-' + identity,
                trial_paths=paths, task_env_config=task.config.environment)
            env.identity, env.project = identity, item['project']
            env.workspace = PurePosixPath(record['workspace'])
            env.root = env.workspace.parent
            env.evidence = paths.trial_dir / 'provider-cleanup-only.jsonl'
            env._prepared = True
            await env._connect()
            info = json.loads((await env._run(env._docker('info', '--format', '{{json .}}'))).stdout)
            assert info['ID'] == plan['engine_id']
            resources = await unused_resources(env, item)
            archive = ('/home/chenkeyi/.local/share/harbor-rsi/qwen35-new772-tb21-20261101/'
                       'checks/synthetic32-fixcode-r002-terminal-preservation-r1/' + identity + '.tar')
            command = shlex.join(['python3', '-c', ARCHIVE, str(env.workspace), identity,
                                  json.dumps(item['workspace']['files']), archive])
            preserved = json.loads((await env._shell(command)).stdout)
            save(B / 'preservation' / (identity + '.json'), preserved)
            result.update(resources_before=resources, preserved_staging_archive=preserved)
            result['resources_reverified_after_preservation'] = await unused_resources(env, item)
            # Only this new auxiliary handle is rehydrated; no running process is patched.
            env._workspace_created = True
            assert env.cleanup_timeout == 120
            await env.stop(delete=True)
            after = await env._resources()
            assert not any(after.values())
            result.update(passed=True, resources_after=after, native_cleanup_timeout_sec=120)
    except Exception as error:
        result.update(passed=False, cleanup_unconfirmed=True, error=repr(error))
    after_files = protected(directory)
    assert after_files == before_files, 'Original Trial evidence changed'
    result['all_original_trial_file_sha_preserved'] = True
    save(B / 'receipts' / (identity + '.json'), result)
    print(json.dumps(dict(task=item['task_id'], passed=result.get('passed'), error=result.get('error'))), flush=True)
    return result


async def main():
    admission = read(B / 'ADMISSION_R1.json')
    assert admission['unique_controller_owner'] == read(C / 'NATIVE_ADVANCE_OWNER.json')
    assert sha(Path(__file__)) == admission['source_sha256']
    assert sha(B / 'PLAN_R1.json') == admission['plan_sha256']
    plan = read(B / 'PLAN_R1.json')
    assert len(plan['rows']) == 1 and {r['task_id'] for r in plan['rows']} == TASKS
    assert sha(Path(inspect.getfile(provider))) == plan['provider_source_sha256']
    assert not (B / 'COMPLETE_R1.json').exists()
    os.environ['PATH'] = str(R / 'formal-controller18-client-bin-r1') + ':' + os.environ['PATH']
    os.environ['TMPDIR'] = str(R / 'tmp')
    rows = [await clean(plan, item) for item in plan['rows']]
    value = dict(at=time.time(), passed=all(r.get('passed') for r in rows), rows=rows,
                 original_scores_and_UNKNOWN_unchanged=True, original_Result_Recorder_Provider_unchanged=True,
                 model_or_Verifier_calls=0, source_sha256=sha(Path(__file__)))
    save(B / 'COMPLETE_R1.json', value)
    if not value['passed']:
        raise RuntimeError('One scoped native cleanup not confirmed')


if __name__ == '__main__':
    asyncio.run(main())
