"""Prepare the first preregistered same-stratum CF reserve; no teacher call."""
from pathlib import Path
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from urllib.request import ProxyHandler, Request, build_opener
from verify_public_oci import verify
from inspect_cold_oci_r1 import inspect_archive, publish
from prepare_cf_original_basic_ssd17_r6 import run, inspect_image, ENGINE, R

S = Path('/ssd/chenkeyi/qwen35-new-cf500-tmax500-20261029')
HELPER = 'quay.io/skopeo/stable@sha256:ad1d2e25cf0234bb50476e753a8fc9debd4f0582cdd2ab6fd7bad9bacdfe3b9b'


def main():
    planfile = Path(sys.argv[1]) if len(sys.argv) == 2 else R / 'manifests/CF_ENVIRONMENT_RESERVE_PLAN_R1.json'
    plan = json.loads(planfile.read_text()); row = plan['candidate']; ident = row['task_id']
    resultfile = R / 'checks/cf-reserve-environments-r1' / (ident + '.json')
    resultfile.parent.mkdir(exist_ok=True)
    if resultfile.exists():
        raise FileExistsError('Observe the exact original reserve pass before resumption')
    if plan['model_attempts_before_replacement'] or plan['active_manifest_changed'] or row['exclusion_reasons']:
        raise ValueError('Reserve registration/source decontamination differs')
    if run(['docker', 'info', '--format', '{{.ID}}']).stdout.strip() != ENGINE:
        raise ValueError('Native17 engine differs')
    name = 'rsi-cf-reserve17-r1'; helper_name = 'rsi-cf-reserve-image17-r1'
    result = dict(task_id=ident, pool='calibforge', source_revision=row['revision'],
        source_task_toml_sha256=row['task_toml_sha256'], source_instruction_sha256=row['instruction_sha256'],
        replaced_task_id=plan['replaced_task_id'], reserve_rank=row['reserve_rank'],
        original_resources=plan['original_resources'], source_plan_sha256=hashlib.sha256(planfile.read_bytes()).hexdigest(),
        backend_engine=ENGINE, active_manifest_changed=False, model_calls=0,
        native_cli_and_final_verifier='Pending; do not admit or count as teacher success')
    loaded = False; image = None; start = time.monotonic()
    try:
        if not row['docker_image'].startswith('aweaiteam/calibforge:'):
            raise ValueError('Unexpected original image repository')
        opener = build_opener(ProxyHandler({'http': 'http://127.0.0.1:7890', 'https': 'http://127.0.0.1:7890'}))
        with opener.open('https://auth.docker.io/token?service=registry.docker.io&scope=repository:aweaiteam/calibforge:pull', timeout=30) as response:
            token = json.load(response)['token']
        tag = row['docker_image'].split(':', 1)[1]
        request = Request('https://registry-1.docker.io/v2/aweaiteam/calibforge/manifests/' + tag,
            headers={'Authorization': 'Bearer ' + token, 'Accept': 'application/vnd.oci.image.manifest.v1+json, application/vnd.docker.distribution.manifest.v2+json'})
        with opener.open(request, timeout=40) as response:
            raw = response.read(); declared = response.headers['Docker-Content-Digest']
        if declared != 'sha256:' + hashlib.sha256(raw).hexdigest():
            raise ValueError('Official public manifest hash differs')
        manifest = json.loads(raw)
        if 'config' not in manifest or 'layers' not in manifest:
            raise ValueError('Original reserve image needs explicit multi-platform acceptance')
        source = dict(task_id=ident, image=row['docker_image'], status='OFFICIAL_REGISTRY_IDENTITY_FROZEN',
            top_manifest_digest=declared, manifest_sha256=declared.split(':')[1],
            pinned='aweaiteam/calibforge@' + declared, config_digest=manifest['config']['digest'],
            media_type=manifest['mediaType'], compressed_layer_bytes=sum(x['size'] for x in manifest['layers']))
        public = R / 'checks/cf-reserve-public-identities-r1'; public.mkdir(exist_ok=True)
        publish(public / (ident + '.json'), source)
        (public / (ident + '.manifest.json')).write_bytes(raw)
        directory = S / 'registry/tasks-cf-reserve-r1' / ident; directory.mkdir(parents=True, exist_ok=True)
        for child in ['tmp', 'home']:
            (directory / child).mkdir(exist_ok=True)
        archive = directory / 'image.oci.tar'
        create = run(['docker', 'create', '--name', helper_name, '--runtime', 'runc', '--network', 'host',
            '--user', str(os.getuid()) + ':' + str(os.getgid()), '--cpus', '1', '--memory', '1g',
            '--mount', 'type=bind,src=' + str(directory) + ',dst=/cache', '--env', 'HOME=/cache/home', '--env', 'TMPDIR=/cache/tmp',
            '--env', 'HTTP_PROXY=http://127.0.0.1:7890', '--env', 'HTTPS_PROXY=http://127.0.0.1:7890',
            HELPER, 'copy', '--preserve-digests', '--retry-times', '2', '--src-no-creds',
            'docker://docker.io/' + source['pinned'], 'oci-archive:/cache/image.oci.tar:' + ident])
        create.check_returncode()
        with (directory / 'copy.log').open('x') as stream:
            copied = subprocess.run(['docker', 'start', '--attach', helper_name], stdout=stream, stderr=subprocess.STDOUT, timeout=1800)
        copied.check_returncode()
        helper = run(['docker', 'inspect', helper_name]); helper.check_returncode(); helper = json.loads(helper.stdout)[0]
        if helper['State']['ExitCode'] or helper['HostConfig']['Privileged'] or helper['HostConfig'].get('DeviceRequests'):
            raise ValueError('Native public archive helper failed its resource/device contract')
        cache = verify(source, archive); publish(directory / 'cache.json', cache)
        publish(S / 'registry/tasks-local-skopeo-r1' / ident / 'cache.json', cache)
        expanded = inspect_archive(archive, declared, cache['archive_sha256'])
        publish(R / 'checks/cold-image-sizes-r1' / (ident + '.json'), expanded)
        required = 32 * 1024**3 + 2 * expanded['archive_bytes'] + expanded['expanded_layer_tar_bytes']
        if shutil.disk_usage('/').free < required:
            raise RuntimeError('Original reserve image exceeds bounded17 runtime cache headroom')
        image = declared; before = inspect_image(image)
        if before is None:
            with (directory / 'load.log').open('x') as stream:
                loaded_result = subprocess.run(['docker', 'image', 'load', '--input', str(archive)], stdout=stream, stderr=subprocess.STDOUT, timeout=900)
            loaded_result.check_returncode(); loaded = True
        info = inspect_image(image)
        if info is None or info['Id'] != declared:
            raise ValueError('Actual original reserve image identity differs')
        resource = plan['original_resources']
        if resource.get('gpus'):
            raise ValueError('Original reserve declares GPU; no CPU substitution allowed')
        create = run(['docker', 'create', '--name', name, '--runtime', 'runc', '--cpus', str(resource['cpus']),
            '--memory', str(resource['memory_mb'] * 1024**2), '--entrypoint', '/bin/bash', image, '-lc',
            'set -eu; pwd -P; id; test -w .; command -v bash; test ! -e /tests; test ! -e /solution; '
            'probe=.cf-reserve-preflight-$$; printf probe > "$probe"; rm -- "$probe"; '
            'cat /sys/fs/cgroup/memory.max /sys/fs/cgroup/cpu.max; getent hosts api.deepseek.com'])
        create.check_returncode()
        configured = run(['docker', 'inspect', name]); configured.check_returncode(); actual = json.loads(configured.stdout)[0]['HostConfig']
        if actual['Memory'] != resource['memory_mb'] * 1024**2 or actual['NanoCpus'] != round(resource['cpus'] * 10**9) or actual['Privileged'] or actual.get('DeviceRequests'):
            raise ValueError('Actual original reserve runtime resource contract differs')
        probe = run(['docker', 'start', '--attach', name], timeout=120)
        native = run(['docker', 'inspect', name]); native.check_returncode(); code = json.loads(native.stdout)[0]['State']['ExitCode']
        result.update(status='IMAGE_IDENTITY_AND_BASIC_SETUP_PASSED' if probe.returncode == code == 0 else 'BASIC_SETUP_FAILED',
            image_id=image, archive_sha256=cache['archive_sha256'], pinned_image=source['pinned'],
            actual_memory_bytes=actual['Memory'], actual_nano_cpus=actual['NanoCpus'],
            probe_returncode=code, probe_stdout=probe.stdout, probe_stderr=probe.stderr)
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        result.update(status='RESERVE_ENVIRONMENT_PREPARATION_FAILED', error_type=type(error).__name__, error=str(error)[:800])
    finally:
        result['cleanup_confirmed'] = True
        for container in [name, helper_name]:
            try:
                removed = run(['docker', 'rm', '-f', container], timeout=180)
                ok = removed.returncode == 0 or 'No such container' in removed.stderr
            except (OSError, subprocess.SubprocessError) as error:
                ok = False; result['cleanup_error'] = str(error)[:800]
            result['cleanup_confirmed'] &= ok
        if loaded and result['cleanup_confirmed']:
            refs = run(['docker', 'ps', '-a', '--filter', 'ancestor=' + image, '--format', '{{.ID}}']); refs.check_returncode()
            if not refs.stdout.strip():
                result['newly_loaded_image_release_returncode'] = run(['docker', 'image', 'rm', image], timeout=120).returncode
        result['seconds'] = time.monotonic() - start
        publish(resultfile, result)
    print(json.dumps(result))


if __name__ == '__main__':
    main()
