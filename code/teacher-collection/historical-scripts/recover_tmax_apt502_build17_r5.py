"""One explicit original-context retry for the preserved APT502 build failure."""
import datetime
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import tarfile
import time
from inspect_cold_oci_r1 import inspect_archive, sha_file

R = Path('/home/chenkeyi/workspace/RSI/runtime-evidence/qwen35-new-cf500-tmax500-20261029')
S = Path('/ssd/chenkeyi/qwen35-new-cf500-tmax500-20261029')
IDENT = 'task_009921_1b294fdc'


def freeze(path, value):
    with path.open('x') as stream:
        stream.write(json.dumps(value, indent=2))


def main():
    old = S / 'buildkit-rootless-r2/archives' / IDENT / 'client-proxy-r3'
    failed = json.loads((old / 'build.json').read_text())
    log = (old / 'build.log').read_text()
    if failed['status'] != 'NATIVE_SSD_BUILD_FAILED' or '502  Bad Gateway' not in log or 'pip3: not found' not in log:
        raise ValueError('This finite recovery only covers the observed original APT502 failure')
    context = S / 'buildkit-rootless-r2/contexts' / IDENT
    actual = [dict(path=str(p.relative_to(context)), mode=stat.S_IMODE(p.stat().st_mode), sha256=sha_file(p))
              for p in sorted(context.rglob('*')) if p.is_file()]
    if actual != failed['source_context']['build_context_files']:
        raise ValueError('Original context bytes/modes changed')
    dest = old.parent / 'network-recovery-r5'
    dest.mkdir(exist_ok=False)
    command = failed['command'].copy()
    command[command.index('--output') + 1] = 'type=oci,name=rsi-ssd-tmax-r2:' + IDENT + ',dest=' + str(dest / 'image.oci.tar')
    command[command.index('--metadata-file') + 1] = str(dest / 'buildctl-metadata.json')
    command.append('--no-cache')
    plan = dict(task_id=IDENT, source_context=failed['source_context'], command=command,
        original_failure=str(old / 'build.json'), original_failure_sha256=sha_file(old / 'build.json'),
        original_failure_log=str(old / 'build.log'), original_failure_log_sha256=sha_file(old / 'build.log'),
        retry_limit=1, model_calls=0, original_files_modified=0,
        reason='APT502 left a successfully cached post-install layer without Python. Re-execute this task build only; no shared cache deletion or daemon changes.',
        source_sha256=sha_file(Path(__file__)))
    freeze(dest / 'PLAN.json', plan)
    record = dict(plan, checked_at=datetime.datetime.now(datetime.timezone.utc).isoformat())
    start = time.monotonic()
    try:
        with (dest / 'build.log').open('x') as stream:
            subprocess.run(command, stdout=stream, stderr=subprocess.STDOUT, check=True, timeout=3600)
        archive = dest / 'image.oci.tar'
        with tarfile.open(archive) as tar:
            index = json.loads(tar.extractfile('index.json').read())
            descriptor, = index['manifests']
            image = descriptor['digest']
        digest = sha_file(archive)
        proof = inspect_archive(str(archive), image, digest)
        freeze(dest / 'image-audit.json', proof)
        record.update(status='ORIGINAL_NATIVE_OCI_ARCHIVE_BUILT_INITIAL_AND_VERIFIER_TESTS_PENDING',
            archive=str(archive), archive_sha256=digest, archive_bytes=archive.stat().st_size,
            native_manifest_digest=image, all_manifest_config_layer_hashes_verified=True,
            full_manifest_config_layer_diffid_proof=str(dest / 'image-audit.json'),
            full_manifest_config_layer_diffid_proof_sha256=sha_file(dest / 'image-audit.json'))
    except Exception as error:
        record.update(status='NATIVE_SSD_NETWORK_RECOVERY_FAILED', error_type=type(error).__name__, error=str(error)[:1200])
    record['seconds'] = time.monotonic() - start
    freeze(dest / 'build.json', record)
    print(json.dumps(record), flush=True)


if __name__ == '__main__':
    for key in ['DEEPSEEK_API_KEY', 'GH_TOKEN', 'OPENAI_API_KEY']:
        os.environ.pop(key, None)
    os.environ['HTTP_PROXY'] = os.environ['HTTPS_PROXY'] = 'http://127.0.0.1:7890'
    main()
