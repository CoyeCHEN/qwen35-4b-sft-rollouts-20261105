"""Preserve one ended native Trial's retained filesystem before any cleanup.

This command neither stops containers nor changes any original Result. No
model calls, Task edits, shared-daemon edits, or resource cleanup occur here.
"""
import datetime
import gzip
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

S = Path('/ssd/chenkeyi/qwen35-new-cf500-tmax500-20261029')
ROOT = S / 'terminal-scope-preservation-r168/cbf183a0d82248229de2d3c7e5d09f50'
os.umask(0o077)
ROOT.mkdir(parents=True, exist_ok=False, mode=0o700)
ENGINE = '59c8ba22-0aa4-4aed-bc43-4e1b5989fa22'
CID = '89fe38750768cef0f383a85eb5b6ef0503182ecfda77b9e1390d115bdc0a8166'
IDENTITY = 'cbf183a0d82248229de2d3c7e5d09f50'
CLI = ['docker', '--host', 'unix://' + str(S / 'engine17-r1/socket/docker.sock')]


def run(args, **kwargs):
    return subprocess.run(CLI + args, check=True, timeout=120, **kwargs)


def sha(path):
    with path.open('rb') as stream:
        value = hashlib.sha256()
        while data := stream.read(8 * 1024 * 1024):
            value.update(data)
    return value.hexdigest()


assert run(['info', '--format', '{{.ID}}'], capture_output=True, text=True).stdout.strip() == ENGINE
container, = json.loads(run(['inspect', CID], capture_output=True, text=True).stdout)
assert container['Config']['Labels']['io.harbor.remote-docker.identity'] == IDENTITY
assert container['Config']['Image'] == 'sha256:63290be53f98f0855e0bc25eadd7c4aad71a596d15c7627698b893f529b95801'
assert container['Config']['Labels']['com.docker.compose.project.config_files'].endswith('/data-science_20260414_211453_004__8bdoiot/remote-docker-' + IDENTITY + '.compose.json')
top = run(['top', CID, '-eo', 'pid,stat,comm'], capture_output=True, text=True).stdout
commands = [line.split(None, 2)[2] for line in top.splitlines()[1:] if len(line.split(None, 2)) == 3]
if not commands or not set(commands) <= {'sh', 'sleep'}:
    raise ValueError('Preserve all processes; scope is no longer an idle ended Agent environment')
metadata = dict(checked_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
    trial='data-science_20260414_211453_004__8bdoiot', task_id='data-science_20260414_211453_004',
    original_result_sha256='c92973ea7126aad364ff9f739765f99a1c4943bc3b8dffedfa7afd374edc7c00',
    original_native_finished_at='2026-10-31T08:17:00.677179Z',
    original_exception='DownloadVerifierDirError', original_result_not_reclassified=True,
    engine_id=ENGINE, container_id=CID, identity=IDENTITY, image=container['Config']['Image'],
    state=container['State'], mounts=container['Mounts'], current_process_commands=commands,
    archive_scope='Complete container filesystem plus every named volume; Docker export alone excludes named volume contents',
    model_calls=0, original_results_or_recorder_modified=False, cleanup_performed=False,
    source_sha256=sha(Path(__file__)))
(ROOT / 'PLAN.json').write_text(json.dumps(metadata, indent=2))
partial = ROOT / 'container-filesystem.tar.gz.partial'
with (ROOT / 'docker-export.stderr').open('xb') as stderr, partial.open('xb') as raw:
    process = subprocess.Popen(CLI + ['export', CID], stdout=subprocess.PIPE, stderr=stderr)
    with gzip.GzipFile(fileobj=raw, mode='wb', compresslevel=1, mtime=0) as archive:
        shutil.copyfileobj(process.stdout, archive, 1024 * 1024)
    if process.wait(timeout=120) != 0:
        raise ValueError('Container export failed; no cleanup is allowed')
    raw.flush()
target = ROOT / 'container-filesystem.tar.gz'
partial.replace(target)
volumes = []
for ordinal, mount in enumerate(container['Mounts']):
    if mount['Type'] != 'volume':
        continue
    volume, = json.loads(run(['volume', 'inspect', mount['Name']], capture_output=True, text=True).stdout)
    if volume['Labels'].get('io.harbor.remote-docker.identity') != IDENTITY:
        raise ValueError('A named volume is outside this exact native scope')
    destination = ROOT / ('named-volume-' + str(ordinal))
    destination.mkdir()
    with (ROOT / ('docker-cp-' + str(ordinal) + '.stderr')).open('xb') as log:
        subprocess.run(CLI + ['cp', CID + ':' + mount['Destination'] + '/.', str(destination)],
            check=True, stdout=log, stderr=subprocess.STDOUT, timeout=3600)
    files = [dict(path=str(path.relative_to(destination)), bytes=path.stat().st_size, sha256=sha(path))
             for path in sorted(destination.rglob('*')) if path.is_file() and not path.is_symlink()]
    symlinks = [dict(path=str(path.relative_to(destination)), target=str(path.readlink()))
                for path in sorted(destination.rglob('*')) if path.is_symlink()]
    volumes.append(dict(name=mount['Name'], mount_destination=mount['Destination'],
        archive_directory=str(destination), files=files, symlinks=symlinks))
after = run(['top', CID, '-eo', 'pid,stat,comm'], capture_output=True, text=True).stdout
after_commands = [line.split(None, 2)[2] for line in after.splitlines()[1:] if len(line.split(None, 2)) == 3]
if not set(after_commands) <= {'sh', 'sleep'}:
    raise ValueError('Scope activity changed; keep archives and forbid cleanup')
metadata.update(completed_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
    container_filesystem=dict(path=str(target), bytes=target.stat().st_size, sha256=sha(target)),
    named_volumes=volumes, all_named_volumes_copied=True, original_result_still_requires_original_failure_classification=True)
with (ROOT / 'PRESERVATION_COMPLETE_R168.json').open('x') as stream:
    json.dump(metadata, stream, indent=2)
print(json.dumps(dict(proof=str(ROOT / 'PRESERVATION_COMPLETE_R168.json'),
    filesystem_archive_bytes=target.stat().st_size, named_volumes=len(volumes), cleanup_performed=False)))
