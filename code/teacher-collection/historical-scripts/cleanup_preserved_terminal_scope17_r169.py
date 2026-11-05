"""Complete exact owned-resource cleanup after full terminal-scope preservation.

Use the same container/network/volume removal boundary as RemoteDocker.stop.
No image removal, shared daemon change, Task rerun, or result reinterpretation.
"""
import datetime
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

S = Path('/ssd/chenkeyi/qwen35-new-cf500-tmax500-20261029')
IDENTITY = 'cbf183a0d82248229de2d3c7e5d09f50'
CID = '89fe38750768cef0f383a85eb5b6ef0503182ecfda77b9e1390d115bdc0a8166'
ROOT = S / 'terminal-scope-preservation-r168' / IDENTITY
CLI = ['docker', '--host', 'unix://' + str(S / 'engine17-r1/socket/docker.sock')]
os.umask(0o077)


def run(args, **kwargs):
    return subprocess.run(CLI + args, check=True, timeout=120, **kwargs)


def sha(path):
    value = hashlib.sha256()
    with path.open('rb') as stream:
        while chunk := stream.read(8 * 1024 * 1024):
            value.update(chunk)
    return value.hexdigest()


target = ROOT / 'OWNED_RESOURCE_CLEANUP_COMPLETE_R169.json'
if target.exists():
    raise FileExistsError('Observe completed exact-scope cleanup; no replay')
proof_path = ROOT / 'PRESERVATION_COMPLETE_R168.json'
proof = json.loads(proof_path.read_text())
assert proof['identity'] == IDENTITY and proof['all_named_volumes_copied']
assert proof['original_result_sha256'] == 'c92973ea7126aad364ff9f739765f99a1c4943bc3b8dffedfa7afd374edc7c00'
archive = proof['container_filesystem']
assert sha(Path(archive['path'])) == archive['sha256']
for volume in proof['named_volumes']:
    directory = Path(volume['archive_directory'])
    for entry in volume['files']:
        assert sha(directory / entry['path']) == entry['sha256']
    for entry in volume['symlinks']:
        assert str((directory / entry['path']).readlink()) == entry['target']
assert run(['info', '--format', '{{.ID}}'], capture_output=True, text=True).stdout.strip() == proof['engine_id']
container, = json.loads(run(['inspect', CID], capture_output=True, text=True).stdout)
assert container['Config']['Labels']['io.harbor.remote-docker.identity'] == IDENTITY
assert container['Image'] == json.loads(run(['image', 'inspect', proof['image']], capture_output=True, text=True).stdout)[0]['Id']
top = run(['top', CID, '-eo', 'pid,stat,comm'], capture_output=True, text=True).stdout
commands = [line.split(None, 2)[2] for line in top.splitlines()[1:] if len(line.split(None, 2)) == 3]
if not commands or not set(commands) <= {'sh', 'sleep'}:
    raise ValueError('Active work exists; no cleanup allowed')
marker_reply = run(['exec', CID, 'cat', '/logs/agent/open-harness.complete.json'], capture_output=True)
marker = json.loads(marker_reply.stdout)
assert marker['exit_code'] == 0
binds = []
for ordinal, mount in enumerate(container['Mounts']):
    if mount['Type'] != 'bind':
        continue
    source = Path(mount['Source'])
    expected = S / 'staging-private-engine17-r1' / ('cftmaxprivate17r720261031-' + IDENTITY)
    if not source.resolve().is_relative_to(expected):
        raise ValueError('Bind source is outside the exact native staging scope')
    destination = ROOT / ('bind-preserved-r169-' + str(ordinal))
    if source.is_file():
        shutil.copy2(source, destination)
        assert sha(source) == sha(destination)
        files = [dict(path=destination.name, sha256=sha(destination), bytes=destination.stat().st_size)]
    else:
        raise ValueError('Unexpected directory bind needs a separate preservation review')
    binds.append(dict(original_source=str(source), mount_destination=mount['Destination'], copied_files=files))
resources = {}
for kind in ['container', 'network', 'volume']:
    args = [kind, 'ls', '-q', '--filter', 'label=io.harbor.remote-docker.identity=' + IDENTITY]
    if kind == 'container':
        args.insert(2, '-a')
    resources[kind] = run(args, capture_output=True, text=True).stdout.split()
assert len(resources['container']) == 1 and CID.startswith(resources['container'][0])
plan = dict(checked_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
    identity=IDENTITY, engine_id=proof['engine_id'], preservation_sha256=sha(proof_path),
    original_result_sha256=proof['original_result_sha256'], verified_archive_sha256=archive['sha256'],
    named_volume_files_rehashed=True, bind_inputs_preserved=binds, exact_resources=resources,
    native_cli_complete_marker_sha256=hashlib.sha256(marker_reply.stdout).hexdigest(),
    current_process_commands=commands, raw_result_unchanged=True, model_calls=0,
    original_task_or_official_verifier_changes=0, source_sha256=sha(Path(__file__)))
with (ROOT / 'OWNED_RESOURCE_CLEANUP_PLAN_R169.json').open('x') as stream:
    json.dump(plan, stream, indent=2)
for kind, identifiers in resources.items():
    for identifier in identifiers:
        run([kind, 'rm', *(['--force'] if kind == 'container' else []), identifier], capture_output=True)
remaining = {}
for kind in ['container', 'network', 'volume']:
    args = [kind, 'ls', '-q', '--filter', 'label=io.harbor.remote-docker.identity=' + IDENTITY]
    if kind == 'container':
        args.insert(2, '-a')
    remaining[kind] = run(args, capture_output=True, text=True).stdout.split()
assert not any(remaining.values())
plan.update(completed_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
    remaining_owned_resources=remaining, owned_container_network_volume_cleanup_complete=True,
    staging_unchanged_and_retained_for_forensics=True, image_removals=0, qualified_success_claim=False)
with target.open('x') as stream:
    json.dump(plan, stream, indent=2)
print(json.dumps(dict(proof=str(target), cleanup_complete=True, original_result_or_reward_rewritten=False)))
