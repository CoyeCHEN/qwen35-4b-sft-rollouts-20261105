"""Small allowlisted evidence bundle; no raw teacher data, caches or environments."""
import datetime
import hashlib
import io
import json
from pathlib import Path
import shlex
import subprocess
import tarfile

R = Path('/home/chenkeyi/.local/share/harbor-rsi/qwen35-new-cf500-tmax500-20261029')
files = {}
names = ['CURRENT_HANDOFF.md', 'stream/collection-r4/deployment-r16/CAMPAIGN.json',
    'configs/campaign-deployment17-r16.json', 'checks/current-operational-metadata-r172.json',
    'checks/actual-active-agent-eight-and-backfill-r147-20261031T091918Z.json',
    'checks/actual-active-agent-eight-and-backfill-r147-20261031T095419Z.json',
    'checks/actual-active-agent-eight-and-backfill-r147-20261031T103530Z.json',
    'checks/actual-active-agent-eight-and-backfill-r174-20261031T104901Z.json',
    'checks/deployment17-rollout-acceptance-r158-20261031T102556Z.json',
    'checks/canonical-data-writer-acceptance-r165.json', 'checks/canonical-data-writer-handoff-r165.json',
    'checks/data-progress-observer-r166-live-hook.json', 'checks/actual-slot-wait-observer-r175-activation.json',
    'checks/terminal-scope-cleanup-r169.json', 'checks/runtime-clock-offset-r140.json',
    'stream/cleaned-original-scope-recheck17-r170/TERMINAL.json',
    'stream/cleaned-original-scope-recheck17-r170/environment-outcomes/data-science_20260414_211453_004.json',
    'logs/canonical-data-writer-handoff-r165c.log']
scripts = ['bootstrap_uv17_r157.py', 'install_controller_runtime17_r160.py',
    'accept_deployment17_rollout_r158.py', 'audit_canary_loader_r159.py',
    'revalidate_canonical_tokenizer17_r159.py', 'audit_canonical_primary17_r161.py',
    'freeze_primary_audit_inputs_r161.py', 'recheck_pre_agent_setup17_r162.py',
    'audit_stream_canonical17_r163.py', 'quarantine_unrepresentable_export_r164.py',
    'audit_stream_data_worker149_r6.py', 'handoff_data_writer149_r165.py',
    'handoff_data_writer149_r165b.py', 'handoff_data_writer149_r165c.py',
    'complete_data_writer_handoff149_r171.py', 'preserve_terminal_scope17_r168.py',
    'cleanup_preserved_terminal_scope17_r169.py', 'recheck_cleaned_original_scope17_r170.py',
    'observe_collection_data_progress_r166.py', 'capture_active_teacher_phases149_r174.py',
    'observe_collection_actual_slot_wait_r175.py', 'package_operational_metadata_r176.py']
names += ['scripts/' + name for name in scripts]
for name in names:
    path = R / name
    files['149/' + name] = path.read_bytes()
deployment = json.loads((R / 'configs/campaign-deployment17-r16.json').read_text())
S = '/ssd/chenkeyi/qwen35-new-cf500-tmax500-20261029'
remote = ['controller17-r1/bootstrap/RUNTIME_INSTALL_ACCEPTANCE_R160.json',
    'controller17-r1/bootstrap/UV_IDENTITY_R157.json', 'controller17-r1/ssh/LOOPBACK_ACCEPTANCE_R154.json',
    'student-tokenizer-r155/SOURCE_MANIFEST_R155.json',
    'data-tokenizer-revalidation-r159/ddc3d97b-cd36-44c5-b911-28451892baeb/checks/TOKENIZER_FULL_TRIAL_ACCEPTANCE_R159.json',
    'data-canonical-primary-r161/training/PROGRESS.json', 'data-canonical-primary-r161/serving/PROGRESS.json',
    'terminal-scope-preservation-r168/cbf183a0d82248229de2d3c7e5d09f50/PRESERVATION_COMPLETE_R168.json',
    'terminal-scope-preservation-r168/cbf183a0d82248229de2d3c7e5d09f50/OWNED_RESOURCE_CLEANUP_COMPLETE_R169.json']
code = "import json,sys;from pathlib import Path;names=json.load(sys.stdin);root=Path(sys.argv[1]);print(json.dumps({n:(root/n).read_text() for n in names}))"
reply = subprocess.run([*deployment['ssh'], deployment['host'], shlex.join(['python3', '-c', code, S])],
    input=json.dumps(remote), text=True, capture_output=True, check=True, timeout=30)
for name, value in json.loads(reply.stdout).items():
    files['17/' + name] = value.encode()
if any(len(blob) > 2 * 1024 * 1024 for blob in files.values()):
    raise ValueError('Unexpected metadata size; do not include raw datasets')
manifest = dict(created_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
    files={name:dict(bytes=len(blob), sha256=hashlib.sha256(blob).hexdigest()) for name, blob in files.items()},
    raw_trajectories_included=False, token_caches_included=False, environment_or_image_files_included=False,
    formal_dataset_release=False, training_started=False)
files['BUNDLE_MANIFEST.json'] = json.dumps(manifest, indent=2).encode()
target = R / 'checks/operational-metadata-r176.tar.gz'
with tarfile.open(target, 'x:gz') as tar:
    for name, blob in sorted(files.items()):
        item = tarfile.TarInfo(name);item.size = len(blob);item.mode = 0o600
        tar.addfile(item, io.BytesIO(blob))
identity = dict(path=str(target), bytes=target.stat().st_size,
    sha256=hashlib.sha256(target.read_bytes()).hexdigest(), members=len(files))
with (R / 'checks/operational-metadata-r176-identity.json').open('x') as stream:
    json.dump(identity, stream, indent=2)
print(json.dumps(identity))
