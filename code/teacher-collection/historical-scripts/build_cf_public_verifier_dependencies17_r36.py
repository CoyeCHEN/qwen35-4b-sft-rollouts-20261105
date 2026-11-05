"""Build two explicit public-Verifier-dependency candidates on owned17 SSD.

Original images, Tasks, tests and reward scripts remain immutable. These
candidates cannot publish Ready or dispatch teachers; native acceptance and
a source-checked Campaign promotion are required separately.
"""
import datetime
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import tarfile
import time
import urllib.request

from inspect_cold_oci_r1 import inspect_archive, publish


R = Path('/home/chenkeyi/workspace/RSI/runtime-evidence/qwen35-new-cf500-tmax500-20261029')
S = Path('/ssd/chenkeyi/qwen35-new-cf500-tmax500-20261029/cf-verifier-public-dependency-r36')


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def main():
    lock = (S / 'build-worker.lock').open('a')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    scope_path = S / 'SOURCE_SCOPE.json'
    scope = json.loads(scope_path.read_text())
    campaign_path = R / 'configs/campaign-build17-r17.json'
    campaign = json.loads(campaign_path.read_text())
    acceptance_path = Path(campaign['native_build_service_acceptance'])
    acceptance = json.loads(acceptance_path.read_text())
    if not acceptance['passed'] or sha(acceptance_path) != campaign['native_build_service_acceptance_sha256']:
        raise ValueError('Accepted private native builder changed')
    if scope['engine_id'] != campaign['runtime_engine_id'] or scope['engine_id'] != acceptance['builder_engine_id']:
        raise ValueError('Candidate/runtime/private-builder Engine differs')
    if sha(acceptance['deployment']['native_buildctl']) != acceptance['deployment']['native_buildctl_sha256']:
        raise ValueError('Accepted buildctl changed')
    os.environ['DOCKER_CONFIG'] = acceptance['deployment']['docker_client_config']
    os.environ.pop('DOCKER_HOST', None)
    engine = subprocess.run(['docker', '--context', acceptance['deployment']['docker_context'],
        'info', '--format', '{{.ID}}'], check=True, text=True, capture_output=True).stdout.strip()
    if engine != scope['engine_id']:
        raise ValueError('Actual private Engine differs')
    if shutil.disk_usage(S).free < 128 * 1024**3:
        raise RuntimeError('Insufficient bounded SSD headroom')
    policy = dict(source_scope_sha256=sha(scope_path), builder_source_sha256=sha(Path(__file__)),
        engine_id=engine, native_builder_acceptance_sha256=sha(acceptance_path),
        build_deployment_sha256=sha(campaign_path), candidate_tasks=scope['tasks'],
        model_calls=0, teacher_dispatches=0, native_build_concurrency=1,
        accepted_by_current_controller=False, original_task_or_test_changes=0,
        identity_policy='Explicit derived candidates; never claim byte identity with the original published images')
    publish(S / 'BUILD_PLAN.json', policy)
    results = []

    def state(task_id, stage):
        value = dict(pid=os.getpid(), checked_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
            current_task_id=task_id, stage=stage, planned=len(scope['tasks']), terminal=len(results),
            results=results, model_calls=0, teacher_dispatches=0, build_concurrency=1,
            accepted_by_current_controller=False, engine_id=engine)
        tmp = S / 'state.pending'
        tmp.write_text(json.dumps(value, indent=2))
        tmp.replace(S / 'state.json')

    for item in scope['tasks']:
        ident = item['task_id']
        dest = S / ident
        context = dest / 'context'
        context.mkdir(parents=True, exist_ok=False)
        record = dict(task_id=ident, source= item, builder_source_sha256=sha(Path(__file__)),
            source_scope_sha256=sha(scope_path), engine_id=engine, model_calls=0,
            accepted_by_current_controller=False, official_task_or_test_changes=0)
        started = time.monotonic()
        try:
            state(ident, 'FREEZING_PUBLIC_DEPENDENCY_CONTEXT')
            cache = Path(item['original_cache_receipt'])
            if sha(cache) != item['original_cache_receipt_sha256']:
                raise ValueError('Original published-image receipt changed')
            original = json.loads(cache.read_text())
            if original['pinned'] != item['original_pinned_image'] or original['image_id'] != item['original_image_id']:
                raise ValueError('Original published image binding differs')
            dockerfile = 'FROM ' + item['original_pinned_image'] + '\n'
            if item['public_setup'] == 'numpy_in_existing_verifier_venv':
                wheel_lock = S / 'numpy-wheel-lock.json'
                wheel = json.loads(wheel_lock.read_text())
                filename = wheel['filename']
                if Path(filename).name != filename or not filename.endswith('.whl'):
                    raise ValueError('Unexpected public wheel filename')
                target = context / filename
                state(ident, 'DOWNLOADING_HASH_LOCKED_PUBLIC_NUMPY_WHEEL')
                opener = urllib.request.build_opener(urllib.request.ProxyHandler({'https':'http://127.0.0.1:7890'}))
                with opener.open(wheel['url'], timeout=120) as response, target.open('xb') as stream:
                    shutil.copyfileobj(response, stream)
                if sha(target) != wheel['wheel_sha256']:
                    raise ValueError('Official public NumPy wheel hash differs')
                dockerfile += 'COPY ' + filename + ' /tmp/cf-public-verifier-dependency/' + filename + '\n'
                dockerfile += 'RUN /usr/local/bin/python3 -m pip --python /opt/verifier/bin/python install --no-index --no-deps /tmp/cf-public-verifier-dependency/' + filename
                dockerfile += ' && /opt/verifier/bin/python -c "import numpy; assert numpy.__version__ == ' + repr(wheel['version']) + '"\n'
                record.update(numpy_wheel_lock_sha256=sha(wheel_lock), numpy_version=wheel['version'], numpy_wheel_sha256=wheel['wheel_sha256'])
            elif item['public_setup'] == 'install_public_ca_certificates':
                inventory = S / 'original-ca-package-inventory.json'
                if sha(inventory) != item['original_ca_inventory_sha256']:
                    raise ValueError('Original CA inventory differs')
                dockerfile += 'ARG HTTP_PROXY\nARG HTTPS_PROXY\n'
                dockerfile += 'RUN http_proxy="$HTTP_PROXY" https_proxy="$HTTPS_PROXY" apt-get update'
                dockerfile += ' && http_proxy="$HTTP_PROXY" https_proxy="$HTTPS_PROXY" apt-get install -y --no-install-recommends ca-certificates'
                dockerfile += ' && test -s /etc/ssl/certs/ca-certificates.crt\n'
            else:
                raise ValueError('Unexpected finite public setup operation')
            (context / 'Dockerfile').write_text(dockerfile)
            members = [dict(path=str(p.relative_to(context)), sha256=sha(p), mode=stat.S_IMODE(p.stat().st_mode))
                for p in sorted(context.iterdir()) if p.is_file()]
            publish(dest / 'context.json', dict(files=members,
                context_sha256=hashlib.sha256(json.dumps(members, sort_keys=True).encode()).hexdigest(),
                original_image_id=item['original_image_id'], contains_official_tests_or_oracle=False))
            archive = dest / 'image.oci.tar'
            metadata = dest / 'buildctl-metadata.json'
            command = [acceptance['deployment']['native_buildctl'], '--addr', acceptance['buildctl_address'],
                'build', '--frontend', 'dockerfile.v0', '--local', 'context=' + str(context),
                '--local', 'dockerfile=' + str(context), '--opt', 'platform=linux/amd64',
                '--opt', 'label:rsi.campaign=' + R.name,
                '--opt', 'label:rsi.public-verifier-dependency-setup=r36',
                '--opt', 'build-arg:HTTP_PROXY=' + acceptance['deployment']['public_dependency_proxy']['bridge'],
                '--opt', 'build-arg:HTTPS_PROXY=' + acceptance['deployment']['public_dependency_proxy']['bridge'],
                '--output', 'type=oci,name=rsi-cf-public-verifier-r36:' + ident + ',dest=' + str(archive),
                '--metadata-file', str(metadata)]
            record['build_command'] = command
            state(ident, 'BUILDING_PUBLIC_VERIFIER_DEPENDENCY_CANDIDATE_ON_PRIVATE17')
            with (dest / 'build.log').open('x') as log:
                subprocess.run(command, check=True, stdout=log, stderr=subprocess.STDOUT,
                    timeout=item['original_build_timeout_sec'])
            with tarfile.open(archive, 'r') as tar:
                index = json.loads(tar.extractfile('index.json').read())
                if len(index['manifests']) != 1:
                    raise ValueError('Unexpected native OCI export structure')
                image = index['manifests'][0]['digest']
            proof = inspect_archive(str(archive), image, sha(archive))
            publish(dest / 'image-audit.json', proof)
            record.update(status='CANDIDATE_PUBLIC_VERIFIER_DEPENDENCIES_BUILT_NATIVE_ACCEPTANCE_PENDING',
                image_id=image, archive=str(archive), archive_sha256=proof['archive_sha256'],
                image_audit_sha256=sha(dest / 'image-audit.json'),
                all_manifest_config_layer_and_diffid_hashes_verified=proof['all_original_manifest_config_layer_and_diffid_hashes_verified'])
        except Exception as error:
            record.update(status='CANDIDATE_BUILD_FAILED', error_type=type(error).__name__, reason=str(error)[-1800:])
        record['seconds'] = time.monotonic() - started
        publish(dest / 'build.json', record)
        results.append(dict(task_id=ident, status=record['status'], receipt=str(dest / 'build.json')))
        state(ident, 'CANDIDATE_BUILD_TERMINAL')
        print(json.dumps(results[-1]), flush=True)
    state(None, 'FINITE_PUBLIC_VERIFIER_DEPENDENCY_CANDIDATE_BUILDS_TERMINAL')
    publish(S / 'TERMINAL.json', json.loads((S / 'state.json').read_text()))


if __name__ == '__main__':
    for key in ['DEEPSEEK_API_KEY', 'OPENAI_API_KEY', 'GH_TOKEN']:
        os.environ.pop(key, None)
    os.environ['HTTP_PROXY'] = os.environ['HTTPS_PROXY'] = 'http://127.0.0.1:7890'
    main()
