"""One bounded native recovery for proven pre-model disk failures; never dispatched here."""
import argparse
import asyncio
import hashlib
import importlib
import json
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

R = Path('/ssd/chenkeyi/qwen35-sft-772-20261101')
E = R / 'formal-native-eval-r1'
B = R / 'environment-preflight30'
C = Path('/data/chenkeyi/qwen35-sft-772-20261101/control')
EXPECTED = {'new-m1-e3-diag': 15, 'new-m1-e5-diag': 23}
sys.path[:0] = [str(R), str(E / 'scripts')]
from environment_evidence_audit_r3 import inventory, read, sha, write

accepted = importlib.import_module('run-accepted-common30-native18-r4')
native = accepted.native
prep = accepted.prep
DISK_PROBE = r'''import hashlib,json,os,sys,tempfile,time
request=json.loads(sys.argv[1]);minimum=64*1024**3;root=request['staging_root'];out={'observed_at_engine149':time.time(),'minimum_available_bytes':minimum,'passed':False,'fsync_file_passed':False,'fsync_directory_passed':False,'readback_passed':False,'probe_file_removed':False};name=None;fd=None;errors=[]
def sample():
 rows=[]
 for path in [root,request['docker_root_dir']]:
  st=os.statvfs(path);rows.append({'path':path,'realpath':os.path.realpath(path),'device':os.stat(path).st_dev,'available_bytes':st.f_bavail*st.f_frsize,'available_inodes':st.f_favail})
 return rows
try:
 out['before']=sample()
 if any(r['available_bytes']<minimum or r['available_inodes']<=0 for r in out['before']):raise RuntimeError('RECOVERY_STORAGE_BELOW_64_GIB_OR_NO_INODES')
 fd,name=tempfile.mkstemp(prefix='.q35-disk-recovery-fsync-',dir=root);data=b'\x00'*65536;offset=0
 while offset<len(data):
  written=os.write(fd,data[offset:])
  if written<=0:raise RuntimeError('Short fsync probe write')
  offset+=written
 os.fsync(fd);out['fsync_file_passed']=True;os.lseek(fd,0,os.SEEK_SET);actual=os.read(fd,len(data)+1)
 out['probe_bytes']=len(actual);out['probe_sha256']=hashlib.sha256(actual).hexdigest();out['readback_passed']=actual==data
 if not out['readback_passed']:raise RuntimeError('Fsync probe readback mismatch')
 os.close(fd);fd=None;os.unlink(name);name=None;out['probe_file_removed']=True
 directory=os.open(root,os.O_RDONLY|os.O_DIRECTORY)
 try:os.fsync(directory);out['fsync_directory_passed']=True
 finally:os.close(directory)
 out['after']=sample()
 if any(r['available_bytes']<minimum or r['available_inodes']<=0 for r in out['after']):raise RuntimeError('RECOVERY_STORAGE_FELL_BELOW_64_GIB')
 out['passed']=True
except Exception as exc:errors.append(repr(exc))
finally:
 if fd is not None:
  try:os.close(fd)
  except Exception as exc:errors.append('probe_close:'+repr(exc))
 if name is not None:
  try:os.unlink(name);out['probe_file_removed']=True
  except Exception as exc:errors.append('probe_cleanup:'+repr(exc))
out['errors']=errors;out['passed']=out['passed']and not errors;out['model_generation_calls']=0
print(json.dumps(out));raise SystemExit(0 if out['passed']else 1)'''
compile(DISK_PROBE, '<recovery-storage-probe>', 'exec')


def model_evidence(trial):
    markers = list(trial.glob('ACTUAL_AGENT_START*.json'))
    files = [p for folder in ['agent', 'agent-logs'] for p in (trial / folder).rglob('*')
             if p.is_file() and p.stat().st_size and any(s in str(p.relative_to(trial)).lower()
             for s in ['recorder', 'trajectory', 'events.jsonl', 'session', 'payload',
                       'open-harness.stdout', 'open-harness.complete', 'effective-config.json'])]
    return markers + files


def validated_plan(admission):
    if admission['unique_controller_owner'] != read(C / 'NATIVE_ADVANCE_OWNER.json'):
        raise RuntimeError('Only the current sole controller may admit this recovery')
    if admission['source_sha256'] != sha(Path(__file__)):
        raise RuntimeError('Recovery source identity changed')
    plan_path = Path(admission['plan_path'])
    if sha(plan_path) != admission['plan_sha256']:
        raise RuntimeError('Frozen recovery plan changed')
    plan = read(plan_path)
    if not admission['disk_repair_verified'] or plan['maximum_new_model_attempts'] != len(plan['trials']):
        raise RuntimeError('Verified disk repair and bounded admission required')
    if sha(Path(admission['disk_repair_proof_path'])) != admission['disk_repair_proof_sha256']:
        raise RuntimeError('Disk repair proof changed')
    reg_path = Path(plan['original_registration_path'])
    if sha(reg_path) != plan['original_registration_sha256']:
        raise RuntimeError('Original accepted registration changed')
    reg = read(reg_path)
    if sha(R / 'run-accepted-common30-native18-r4.py') != reg['source_sha256']:
        raise RuntimeError('The original accepted worker identity changed')
    if sha(B / 'ENV_PREFLIGHT_30_MANIFEST.json') != reg['environment_manifest_sha256']:
        raise RuntimeError('Shared environment acceptance changed')
    if sha(Path(plan['source_audit_path'])) != plan['source_audit_sha256']:
        raise RuntimeError('Read-only source audit changed')
    if len(plan['trials']) != EXPECTED.get(reg['tag']) or len({x['task_id'] for x in plan['trials']}) != EXPECTED[reg['tag']]:
        raise RuntimeError('Recovery must contain exactly this model’s fixed proven zero-model task set')
    tasks = {row['task_id'] for row in plan['trials']}
    if tasks.intersection(reg['retained_started_tasks']) or plan['previous_actual_model_attempts'] != 0:
        raise RuntimeError('Previously started model tasks are excluded')
    if reg['tag'] == 'new-m1-e3-diag':
        proof_path = Path(plan['old_prejob_failure_proof_path'])
        if sha(proof_path) != plan['old_prejob_failure_proof_sha256']:
            raise RuntimeError('Original R2 pre-job failure proof changed')
        proof = read(proof_path)
        if not proof['assertions_passed'] or proof['old_job_directory_exists'] or proof['actual_native_job_uuid'] is not None:
            raise RuntimeError('Original M1E3 R2 is not proven to have no native Job')
        if Path(proof['old_job_directory']).exists():
            raise RuntimeError('Original R2 native Job now exists')
        for name in proof['old_actual_files_absent']:
            if (Path(proof['old_admission_identity']['path']).parent / name).exists():
                raise RuntimeError('Original R2 native mapping/progress appeared')
        for key in ['old_admission_identity', 'old_log_identity']:
            if sha(Path(proof[key]['path'])) != proof[key]['sha256']:
                raise RuntimeError('Original R2 admission or failure log changed')
        props = dict(line.split('=', 1) for line in subprocess.check_output([
                     'systemctl', '--user', 'show', proof['old_unit'], '-p', 'MainPID', '-p', 'ActiveState'],
                     text=True, timeout=8).splitlines())
        if props['MainPID'] != '0' or props['ActiveState'] != 'failed':
            raise RuntimeError('Original R2 unit is no longer the retained failed pre-job launch')
    for external in plan['external_attempt_ledgers']:
        path = Path(external['path'])
        if sha(path) != external['sha256']:
            raise RuntimeError('External historical attempt ledger changed')
        ledger = read(path)
        for row in ledger.get('rows', []):
            if row.get('model_id') == reg['model']['model_id'] and row.get('task_id') in tasks and row.get('actual_or_conservatively_started') is not False:
                raise RuntimeError('External actual or ambiguous prior model attempt exists')
        for row in ledger.get('trials', []):
            cfg = read(Path(row['source_directory']) / 'config.json')
            if cfg['agent']['kwargs']['config']['model']['id'] == reg['model']['model_id'] and row['task_id'] in tasks:
                raise RuntimeError('Detached actual prior model attempt exists')
    for row in plan['trials']:
        rp = Path(row['result_identity']['path'])
        cp = Path(row['config_identity']['path'])
        if sha(rp) != row['result_identity']['sha256'] or sha(cp) != row['config_identity']['sha256']:
            raise RuntimeError('Original Result/config changed: ' + row['task_id'])
        previous = read(rp)
        ex = previous.get('exception_info') or {}
        if ex.get('exception_type') != 'RemoteDockerError' or 'No space left on device' not in ex.get('exception_message', ''):
            raise RuntimeError('Not the admitted infrastructure failure')
        if previous.get('agent_execution') is not None or previous.get('agent_result') is not None or model_evidence(rp.parent):
            raise RuntimeError('Prior actual/ambiguous model attempt must be retained, not retried')
        if previous['id'] != row['native_trial_uuid'] or previous['config']['agent']['kwargs']['config']['model']['id'] != reg['model']['model_id']:
            raise RuntimeError('Original Trial/model identity changed')
        task = Path(read(cp)['task']['path'])
        expected = row['task_source']['files']
        if {str(p.relative_to(task)) for p in task.rglob('*') if p.is_file()} != {p['path'] for p in expected}:
            raise RuntimeError('Original Task file set changed')
        for f in expected:
            path = task / f['path']
            if sha(path) != f['sha256'] or path.stat().st_mode & 0o7777 != f['mode']:
                raise RuntimeError('Original Task bytes or permissions changed: ' + str(path))
        for other in (E / 'jobs').glob('*/' + '*/config.json'):
            if other == cp:
                continue
            cfg = read(other)
            model = cfg['agent'].get('kwargs', {}).get('config', {}).get('model', {})
            if Path(cfg['task']['path']).name != row['task_id'] or model.get('id') != reg['model']['model_id']:
                continue
            raw_path = other.parent / 'result.json'
            raw = read(raw_path) if raw_path.exists() else None
            if raw is None or raw.get('agent_execution') is not None or raw.get('agent_result') is not None or model_evidence(other.parent):
                raise RuntimeError('Other active/actual/ambiguous model-task Trial exists: ' + str(other.parent))
    return plan, reg


def configuration(plan, reg):
    cfg = accepted.JobConfig.model_validate_json(native.selected_config(read(E / 'manifests/FORMAL_801_TRIAL_PLAN.json')).read_text())
    names = {x['task_id'] for x in plan['trials']}
    cfg.tasks = [t for t in cfg.tasks if t.path.name in names]
    cfg.agents = [accepted.TrialConfig.model_validate(reg['template_config']).agent]
    cfg.job_name = plan['recovery_job_name']
    cfg.jobs_dir = E / 'jobs'
    cfg.n_concurrent_trials = plan['concurrency']
    cfg.n_attempts = 1
    cfg.retry.max_retries = 0
    if len(cfg.tasks) != EXPECTED[reg['tag']] or cfg.n_concurrent_trials != 2 or plan['ports'] != reg['ports']:
        raise RuntimeError('Recovery differs from the bounded original model placement')
    return cfg


async def main(admission_path, validate_only):
    admission = read(admission_path)
    gate_bin = Path(admission['docker_admission_bin'])
    if sha(gate_bin / 'docker') != admission['docker_wrapper_sha256'] or sha(Path(admission['docker_admission_policy_path'])) != admission['docker_admission_policy_sha256']:
        raise RuntimeError('Explicit recovery-only Docker admission identity changed')
    os.environ['PATH'] = str(gate_bin) + ':' + native.D['transport']['private_client_bin'] + ':' + os.environ['PATH']
    os.environ['OPENAI_API_KEY'] = 'node18-local'
    os.environ['TMPDIR'] = str(R / 'tmp')
    plan, reg = validated_plan(admission)
    cfg = configuration(plan, reg)
    out = Path(admission['output_directory'])
    if (cfg.jobs_dir / cfg.job_name).exists():
        raise RuntimeError('Never recreate a native recovery Job')
    snapshots = []
    for attempt in [1, 2]:
        snap = inventory(native.D['task_engine']['native_endpoint'])
        path = out / ('PRE_JOB_ENGINE_INVENTORY_R3_ATTEMPT' + str(attempt) + '.json')
        write(path, snap)
        snapshots.append({'path': str(path), 'sha256': sha(path)})
        if all(q['ok'] for q in snap['queries'].values()):
            break
        if attempt == 1:
            await asyncio.sleep(1)
    if not all(q['ok'] for q in snap['queries'].values()):
        wait = {'at': time.time(), 'status': 'WAITING_ENGINE_QUERY', 'native_job_created': False,
                'actual_native_job_id': None, 'new_model_attempts': 0, 'queries_attempted': len(snapshots),
                'inventory_evidence': snapshots, 'failures': {k: q for k, q in snap['queries'].items() if not q['ok']}}
        write(out / 'PRE_JOB_WAIT_R3.json', wait)
        print(json.dumps(wait))
        return
    if snap['queries']['engine']['data']['ID'] != plan['engine_id']:
        raise RuntimeError('Wrong Engine identity; preserved full inventory: ' + snapshots[-1]['path'])
    old_ids = {i for row in plan['trials'] for i in row['provider_identities']}
    for kind in ['container', 'network', 'volume']:
        if any(row['identity'] in old_ids for row in snap['queries'][kind]['data']):
            raise RuntimeError('Old scoped resources remain; parent must complete native cleanup')
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    for port in plan['ports']:
        with opener.open('http://127.0.0.1:' + str(port) + '/model_info', timeout=3) as response:
            info = json.load(response)
        if info['weight_version'] != reg['model']['weight_version'] or info['model_path'] != reg['model']['model_path']:
            raise RuntimeError('Wrong model service identity')

    async def disk_gate(phase):
        import shlex
        request = {'staging_root': native.D['task_engine']['staging_root'],
                   'docker_root_dir': snap['queries']['engine']['data']['DockerRootDir']}
        command = ['python3', '-c', DISK_PROBE, json.dumps(request)]
        process = await asyncio.create_subprocess_exec('ssh', '-p', '18449', 'chenkeyi@127.0.0.1',
                  shlex.join(command), stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=45)
        except TimeoutError:
            # Only our no-model SSH probe is stopped; no Native Trial/service is signalled.
            if process.returncode is None:
                process.kill()
            await process.wait()
            write(out / 'disk-gates' / (str(time.time_ns()) + '.json'), {
                  'at_node18': time.time(), 'phase': phase, 'passed': False, 'status': 'UNKNOWN',
                  'error': 'SSH fsync probe timed out; remote temporary-file cleanup is unconfirmed',
                  'remote_probe_file_prefix': '.q35-disk-recovery-fsync-', 'new_model_calls': 0})
            raise RuntimeError('RECOVERY_STORAGE_GATE_UNKNOWN: fsync probe timeout') from None
        receipt = {'at_node18': time.time(), 'phase': phase, 'ssh_return_code': process.returncode,
                   'probe_source_sha256': hashlib.sha256(DISK_PROBE.encode()).hexdigest(),
                   'stderr': stderr.decode(errors='replace')[-2000:],
                   'stdout': stdout.decode(errors='replace')}
        write(out / 'disk-gates' / (str(time.time_ns()) + '.json'), receipt)
        if process.returncode:
            raise RuntimeError('RECOVERY_STORAGE_GATE_FAILED: ' + receipt['stdout'][-3000:] + receipt['stderr'])
        proof = json.loads(stdout)
        if not all(proof[k] for k in ['passed', 'fsync_file_passed', 'fsync_directory_passed', 'readback_passed', 'probe_file_removed']):
            raise RuntimeError('RECOVERY_STORAGE_GATE_INCOMPLETE')
        if proof['minimum_available_bytes'] != 64 * 1024**3 or any(row['available_bytes'] < 64 * 1024**3 for kind in ['before', 'after'] for row in proof[kind]):
            raise RuntimeError('RECOVERY_STORAGE_GATE_BELOW_64_GIB')

    await disk_gate('immediately-before-native-job')
    if validate_only:
        print(json.dumps({'validated': True, 'new_trials_dispatched': 0, 'tasks': len(plan['trials']), 'concurrency': 2,
                          'source_results_preserved': True, 'model_generation_calls': 0}))
        return
    job = await accepted.Job.create(cfg)
    registered = [x for x in reg['trials'] if x['task_id'] in {r['task_id'] for r in plan['trials']}]
    items = accepted.ordered_items(job._trial_configs, registered)
    for item in items:
        item['trial_name'] = item['task_id'] + '__accepted30-disk-recovery-' + reg['tag'] + '-r3'
    native.apply_trial_overrides(job._trial_configs, {'trials': items}, read(B / 'environment-profiles-recheck-r2.json'), namespace='q35accepted30diskr1')
    for index, trial in enumerate(job._trial_configs):
        prep.append_ipam(trial, reg['tag'], trial.task.path.name, 1)
        trial.agent.kwargs['config']['model']['baseUrl'] = 'http://172.17.0.1:' + str(plan['ports'][index % len(plan['ports'])]) + '/v1'
    job._remaining_trial_configs = job._trial_configs
    write(out / 'ACTUAL_NATIVE_TRIALS_R3.json', {'at': time.time(), 'native_job_id': str(job.id),
          'job_name': cfg.job_name, 'expected': len(plan['trials']), 'tag': reg['tag'], 'plan_path': admission['plan_path'],
          'plan_sha256': admission['plan_sha256'], 'trials': [t.model_dump(mode='json') for t in job._trial_configs],
          'recovery_of_trials': [{'task_id': r['task_id'], 'original_native_trial_uuid': r['native_trial_uuid'],
                                 'original_result_identity': r['result_identity'],
                                 'original_config_identity': r['config_identity'],
                                 'previous_actual_model_attempts': 0} for r in plan['trials']]})
    manifest = read(B / 'ENV_PREFLIGHT_30_MANIFEST.json')

    async def started(event):
        if event.event.value != 'agent-start' or event.result.agent_setup is None or event.result.agent_setup.finished_at is None or event.result.agent_execution is not None or event.result.agent_result is not None:
            raise RuntimeError('Recovery identity gate must precede native Agent.run')
        d = Path(event.config.trials_dir) / event.trial_name
        logs = list(d.glob('remote-docker-*.jsonl'))
        if len(logs) != 1:
            raise RuntimeError('Missing unique native environment identity')
        identity = logs[0].stem.removeprefix('remote-docker-')
        args = ['docker', '--host', native.D['task_engine']['native_endpoint']]
        ids = subprocess.check_output(args + ['ps', '-q', '--filter', 'label=io.harbor.remote-docker.identity=' + identity], text=True, timeout=15).split()
        if len(ids) != 1:
            raise RuntimeError('Missing unique runtime container')
        actual = json.loads(subprocess.check_output(args + ['inspect', ids[0]], text=True, timeout=15))[0]
        prepared = next(t for t in manifest['tasks'] if t['task_id'] == event.config.task.path.name)['attempts'][-1]['actual_runtime']
        if actual['Image'] != prepared['actual_image_id']:
            raise RuntimeError('Accepted official image identity changed')
        write(d / 'ACCEPTED_ENVIRONMENT_IMAGE_DISK_R3.json', {'at': time.time(), 'identity': identity,
              'image_id': actual['Image'], 'prepared_image_id': prepared['actual_image_id']})
        if event.config.task.path.name == 'torch-tensor-parallelism':
            binding = reg['public_verifier_cache_binding']
            if sha(B / 'PUBLIC_VERIFIER_CACHE_BINDING_R1.json') != reg['public_verifier_cache_binding_sha256'] or sha(Path(binding['runtime_spec_path'])) != binding['runtime_spec_sha256']:
                raise RuntimeError('Accepted public dependency cache binding changed')
            import shlex
            record = read_jsonl(logs[0])[0]
            command = ['python3', binding['remote_materializer_path'], '--identity', identity,
                       '--workspace', record['workspace'], '--receipt-sha256', binding['archive_receipt_sha256']]
            process = await asyncio.create_subprocess_exec('ssh', '-p', '18449', 'chenkeyi@127.0.0.1', shlex.join(command), stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=600)
            if process.returncode:
                raise RuntimeError(stderr.decode(errors='replace')[-3000:])
            proof = json.loads(stdout)
            if proof['source_sha256'] != binding['materializer_sha256'] or proof['archive_sha256'] != binding['archive_sha256'] or not proof['actual_private_cache']['passed'] or proof['model_generation_calls'] != 0:
                raise RuntimeError('Public cache materialization failed')
            write(d / 'PUBLIC_DEPENDENCY_CACHE_PREPARATION_R1.json', proof)
        write(d / 'ACTUAL_AGENT_START_DISK_R3.json', {'at': time.time(), 'native_trial_uuid': str(event.trial_id),
              'task_id': event.config.task.path.name, 'model': reg['model']['model_id'],
              'recovery_of': next(r['native_trial_uuid'] for r in plan['trials'] if r['task_id'] == event.config.task.path.name)})

    def progress():
        rows = []
        for p in job.job_dir.glob('*/result.json'):
            raw = read(p)
            rows.append({'task_id': Path(raw['config']['task']['path']).name, 'trial_id': raw['id'],
                         'result_path': str(p), 'result_sha256': sha(p),
                         'raw_reward': (raw.get('verifier_result') or {}).get('rewards'),
                         'exception_type': (raw.get('exception_info') or {}).get('exception_type'),
                         'agent_execution': raw.get('agent_execution')})
        write(out / 'PROGRESS_R3.json', {'at': time.time(), 'expected': len(plan['trials']), 'terminal': len(rows),
              'native_job_id': str(job.id), 'job_name': cfg.job_name,
              'actual_agent_starts': len(list(job.job_dir.glob('*/ACTUAL_AGENT_START_DISK_R3.json'))),
              'rows': rows, 'original_results_unchanged': True, 'recovery_is_not_first_pass': True})

    async def ended(event):
        progress()

    async def starting(event):
        await disk_gate('before-environment:' + event.trial_name)

    job.on_trial_started(starting)
    job.on_agent_started(started)
    job.on_trial_ended(ended)
    progress()
    result = await job.run()
    progress()
    files = list(job.job_dir.glob('*/result.json'))
    if len(result.trial_results) != len(plan['trials']) or len(files) != len(plan['trials']):
        raise RuntimeError('Recovery is not fully terminal')
    write(out / 'ALL_TERMINAL_R3.json', {'at': time.time(), 'expected': len(plan['trials']), 'terminal': len(plan['trials']),
          'native_job_id': str(job.id), 'job_name': cfg.job_name, 'plan_path': admission['plan_path'], 'plan_sha256': admission['plan_sha256'],
          'source_results_preserved': True, 'recovery_is_not_first_pass': True,
          'results': [{'path': str(p), 'sha256': sha(p)} for p in files]})


def read_jsonl(path):
    return [json.loads(line) for line in path.read_text().splitlines()]


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('admission', type=Path)
    parser.add_argument('--validate-only', action='store_true')
    args = parser.parse_args()
    asyncio.run(main(args.admission, args.validate_only))
