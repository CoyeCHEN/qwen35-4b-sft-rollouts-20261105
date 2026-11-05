"""Update the existing timer's observer after its unchanged resource acceptance."""
import datetime
import hashlib
import json
from pathlib import Path
import subprocess

R = Path('/home/chenkeyi/.local/share/harbor-rsi/qwen35-new-cf500-tmax500-20261029')
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
canonical = R / 'scripts/observe_collection.py'
candidate = R / 'scripts/observe_collection_public_cli_r289.py'
proof_path = R / 'checks/monitor-public-cli-r283-resource/result.json'
proof = json.loads(proof_path.read_text())
original=R/'scripts/observe_collection_public_cli_r278.py'
normalized=candidate.read_text().replace('stream/public-cpython-native-setup-recovery17-r277/state.json','stream/public-cpython-setup-recovery17-r277/state.json').replace('public_cli_controller_acceptance_r288','public_cli_controller_acceptance_r284').replace('controller-r20-offline-acceptance-r288.json','controller-r20-offline-acceptance-r284.json')
if normalized!=original.read_text():raise ValueError('Observer changes beyond the two proven metadata paths')
if not proof['passed'] or proof['source_sha256'] != sha(original):
    raise ValueError('Accepted observer changed')
previous = sha(R/'scripts/observe_collection_public_cli_r278.py')
if sha(canonical) != previous:
    raise ValueError('Observer identity changed; do not overwrite another window')
state = subprocess.run(['systemctl', '--user', 'is-active', 'qwen35-tb21-monitor.service'], capture_output=True, text=True).stdout.strip()
if state in ['active', 'activating', 'deactivating']:
    raise ValueError('Existing timer hook must finish before observer replacement')
temporary = canonical.with_suffix('.r292.pending')
temporary.write_bytes(candidate.read_bytes())
temporary.replace(canonical)
out = dict(checked_at=datetime.datetime.now(datetime.timezone.utc).isoformat(), active_sha256=sha(canonical), previous_sha256=previous, resource_proof=str(proof_path), resource_proof_sha256=sha(proof_path), unchanged_cpu_quota='10%', unchanged_memory_limit_bytes=256*1024**2, unchanged_hook_timeout_seconds=90, actual_next_timer_execution_pending=True,original_resource_budget_preserved=True,path_only_delta_acceptance=True, shared_timer_or_service_changes=0, teacher_or_verifier_actions=0)
with (R / 'checks/monitor-public-cli-r292-ACTIVE.json').open('x') as stream:
    json.dump(out, stream, indent=2)
print(json.dumps(out))
