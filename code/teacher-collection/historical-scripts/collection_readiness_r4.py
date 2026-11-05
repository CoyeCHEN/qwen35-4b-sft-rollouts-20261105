"""Task preparation for cold archives; native Harbor still owns every lifecycle.

No provider, agent-loop or scoring implementation. Official files remain intact.
"""
from pathlib import Path
import hashlib
import json
import re
import shutil
import subprocess
import tomllib
import toml
from harbor.models.task.config import TaskConfig
from native_image_archive149_r1 import R, SSH, HOST, PY17, E17, image_info, load_verified_archive
from tmax_runtime_adapter import runtime_compose_override


def read(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def blocking_review(ident):
    for directory in ['cf-environment-boundary-reviews-r8', 'native-environment-review-corrections-r11', 'task-source-boundary-reviews-r7']:
        path = R / 'checks' / directory / (ident + '.json')
        if path.exists() and read(path)['status'] in ['ENV_BLOCKED', 'ENV_FAILED']:
            return path
    return None


def basic_receipt(row):
    if blocking_review(row['task_id']):
        return None
    names = (['cf-reserve-environments-r1', 'cf-environments-ssd17-recheck-r7', 'cf-environments-oci-r5', 'cf-environments-ssd17-r6']
        if row['pool'] == 'calibforge' else ['tmax-environments-preregistered-reserve-r3',
        'tmax-environments-public-input-review-r6', 'tmax-environments-collision-recheck-r5',
        'tmax-environments-runtime-r4', 'tmax-environments-ssd17-r7'])
    for name in names:
        path = R / 'checks' / name / (row['task_id'] + '.json')
        if not path.exists():
            continue
        value = read(path)
        if value['status'] == 'IMAGE_BASIC_PASSED_CAPACITY_HOLD':
            historical = Path(value['original_evidence'])
            if sha(historical) != value['original_evidence_sha256']:
                raise ValueError('Original capacity-held preparation bytes changed')
            path, value = historical, read(historical)
        if value['status'] in ['IMAGE_IDENTITY_AND_BASIC_SETUP_PASSED', 'IMAGE_AND_ORIGINAL_INITIAL_STATE_PASSED_FINAL_VERIFIER_PENDING']:
            if not value.get('cleanup_confirmed', value.get('preparation_container_cleanup_confirmed', False)):
                raise ValueError('Original preparation cleanup is unconfirmed')
            return path, value
    return None


def prepared(row, basic):
    receipt, evidence = basic
    original = Path(row['source_path'] if row['pool'] == 'calibforge' else row['task_path'])
    if sha(original / 'instruction.md') != row['instruction_sha256']:
        raise ValueError('Frozen original instruction changed')
    raw = tomllib.loads((original / 'task.toml').read_text())
    if row['pool'] == 'calibforge':
        if sha(original / 'task.toml') != row['task_toml_sha256']:
            raise ValueError('Original CF task configuration changed')
        files = row['private_file_identities']
    else:
        source = R / 'sources/tmax/original-tasks' / row['task_id']
        if sha(source / 'task.json') != row['task_json_sha256']:
            raise ValueError('Original TMax release changed')
        files = [dict(path=str(p.relative_to(original)), sha256=sha(p)) for p in sorted((original / 'tests').rglob('*')) if p.is_file()]
        if 'ssd17-r7' in str(receipt):
            plan = read(R / 'manifests/TMAX_REMAINING_INITIAL_SSD17_R7.json')
            source_row = next(x for x in plan['tasks'] if x['task_id'] == row['task_id'])
            if sha(original / 'task.toml') != source_row['native_config_sha256'] or sha(source / 'test_initial_state.py') != evidence['initial_test_sha256']:
                raise ValueError('Original native context/initial-test identity changed')
    path = R / 'prepared-tasks' / (row['pool'] + '-cold-stream-r4') / row['task_id']
    expected = json.loads(json.dumps(raw)); expected['environment']['docker_image'] = evidence['image_id']
    startup = None
    if row['pool'] == 'tmax':
        expected['environment']['workdir'] = '/home/user'
        expected['environment'].setdefault('env', {})['HOME'] = '/home/user'
        startup = runtime_compose_override(R / 'sources/tmax/original-tasks' / row['task_id'])
        recorded = evidence.get('native_startup_override', evidence.get('native_compose_startup_override'))
        if recorded is not None and recorded != startup:
            raise ValueError('Original TMax runtime startup differs')
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True); shutil.copytree(original, path)
        (path / 'task.toml').write_text(toml.dumps(expected))
        if startup:
            import yaml
            (path / 'environment/docker-compose.yaml').write_text(yaml.safe_dump(startup, sort_keys=False))
    if tomllib.loads((path / 'task.toml').read_text()) != expected:
        raise ValueError('Immutable external task image-pin copy changed')
    if startup:
        import yaml
        if yaml.safe_load((path / 'environment/docker-compose.yaml').read_text()) != startup:
            raise ValueError('Immutable native startup copy changed')
    for item in files:
        if sha(original / item['path']) != item['sha256'] or sha(path / item['path']) != item['sha256']:
            raise ValueError('Official verifier/private bytes changed')
    native = TaskConfig.model_validate(expected); source_config = TaskConfig.model_validate(raw)
    for key in ['cpus', 'memory_mb', 'storage_mb', 'gpus']:
        if getattr(native.environment, key) != getattr(source_config.environment, key):
            raise ValueError('Original Task resource changed')
    if native.verifier != source_config.verifier:
        raise ValueError('Original verifier deadline/configuration changed')
    admitted = dict(row)
    admitted.update(prepared_task_path=str(path), prepared_task_toml_sha256=sha(path / 'task.toml'),
        image_id=evidence['image_id'], preparation_receipt=str(receipt), preparation_receipt_sha256=sha(receipt),
        agent_timeout_override_sec=max(source_config.agent.timeout_sec, 10800),
        original_verifier_timeout_sec=native.verifier.timeout_sec, verifier_files=files)
    return admitted


def ensure_resident(row):
    current = image_info(row['image_id'])
    if current is not None:
        return dict(status='EXACT_IMAGE_ALREADY_RESIDENT', image_id=current['Id'])
    import shlex
    request = json.dumps(dict(task_id=row['task_id'], image_id=row['image_id'], pool=row['pool']))
    reply = subprocess.run(SSH + [HOST, shlex.join([PY17, E17 + '/scripts/resolve_cold_image17_r1.py'])],
        input=request, capture_output=True, text=True, check=True, timeout=1800)
    return load_verified_archive(row['task_id'], row['image_id'], row['pool'], json.loads(reply.stdout))


def release_cold_cache(row):
    """Release only this Task's idle image after verifying its exact cold copy."""
    import shlex
    image=row['image_id']; current=image_info(image)
    if current is None:
        return dict(status='IMAGE_ALREADY_ABSENT',image_id=image)
    allowed={row.get('docker_image'), row['task_id'], row['task_id']+':latest'}
    allowed.discard(None)
    if row['pool']=='tmax':
        if (current['Config'].get('Labels') or {}).get('rsi.campaign')!=R.name:
            raise ValueError('Unowned TMax image cannot be released')
        allowed.add('rsi-stage2-tmax-20261029:'+row['task_id'])
        allowed.add('rsi-ssd-tmax-r2:'+row['task_id'])
    if not set(current.get('RepoTags') or [])<=allowed:
        return dict(status='CACHE_RETAINED_OTHER_TASK_TAGS',image_id=image)
    def refs():
        return subprocess.run(['docker','ps','-aq','--filter','ancestor='+image],capture_output=True,text=True,check=True,timeout=30).stdout.strip()
    if refs():
        return dict(status='CACHE_RETAINED_CONTAINER_REFERENCE',image_id=image)
    code='''import sys,json
sys.path.insert(0,sys.argv[1])
from resolve_cold_image17_r1 import resolve
from inspect_cold_oci_r1 import sha_file
p=resolve(sys.argv[2],sys.argv[3],sys.argv[4])
if sha_file(p['archive'])!=p['archive_sha256']:raise ValueError('Cold archive changed')
print(json.dumps(p))'''
    reply=subprocess.run(SSH+[HOST,shlex.join([PY17,'-c',code,E17+'/scripts',row['task_id'],image,row['pool']])],capture_output=True,text=True,timeout=1800)
    if reply.returncode:
        return dict(status='CACHE_RETAINED_COLD_COPY_NOT_VERIFIED',image_id=image)
    proof=json.loads(reply.stdout)
    if not proof['all_original_manifest_config_layer_and_diffid_hashes_verified']:
        raise ValueError('Cold archive original content identity is incomplete')
    if refs():
        return dict(status='CACHE_RETAINED_NEW_CONTAINER_REFERENCE',image_id=image)
    for tag in current.get('RepoTags') or []:
        # OCI imports may retain a bare alias. Docker CLI normalizes a bare
        # argument to :latest, so leave that alias for removal by exact ID.
        if ':' in tag:
            subprocess.run(['docker','image','rm',tag],capture_output=True,text=True,check=True,timeout=180)
    if image_info(image) is not None:
        subprocess.run(['docker','image','rm',image],capture_output=True,text=True,check=True,timeout=180)
    if image_info(image) is not None:
        raise ValueError('Native image removal did not complete')
    return dict(status='EXACT_COLD_BACKED_IDLE_IMAGE_RELEASED',image_id=image,
        archive=proof['archive'],archive_sha256=proof['archive_sha256'],force_or_global_prune_actions=0)


def verify_nop(result, trial, row):
    if result.exception_info or result.infrastructure_errors:
        raise ValueError('Native NOP verifier/lifecycle infrastructure failure')
    raw = read(trial / 'result.json')
    reward = (raw.get('verifier_result') or {}).get('rewards', {}).get('reward')
    if not (raw.get('verifier') or {}).get('finished_at') or reward not in (0, 1):
        raise ValueError('Official original verifier did not complete')
    text = '\n'.join(p.read_text(errors='replace') for p in (trial / 'verifier').glob('test-*.txt'))
    instruction = (Path(row['prepared_task_path']) / 'instruction.md').read_text()
    missing = set(re.findall(r"ModuleNotFoundError: No module named ['\"]([^'\"]+)['\"]", text))
    review = R / 'checks/native-environment-reviews-r10' / (row['task_id'] + '.json')
    reviewed_outputs = set()
    if review.exists() and not blocking_review(row['task_id']):
        known = read(review)
        if sha(Path(known['prior_outcome'])) != known['prior_outcome_sha256']:
            raise ValueError('Trusted NOP output-module review changed')
        reviewed_outputs = set(known['missing_modules'])
    expected_output_modules = all(name in reviewed_outputs or re.search(r'(?<![a-zA-Z0-9_])' + re.escape(name.split('.')[0]) + r'\.py\b', instruction) for name in missing)
    if missing and not expected_output_modules:
        raise ValueError('Verifier dependency/import origin requires trusted review; no teacher dispatch')
    fatal = ['command not found', 'No module named pytest']
    if any(value in text for value in fatal):
        raise ValueError('Original verifier executable/dependency failed to start')
    if any(value in text for value in ['ERROR collecting', 'ImportError while importing']) and not (missing and expected_output_modules):
        raise ValueError('Original verifier collection failed without a missing public output module')
    return reward
