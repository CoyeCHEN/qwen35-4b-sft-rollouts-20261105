"""Update the existing timer's observer after its unchanged resource acceptance."""
import datetime
import hashlib
import json
from pathlib import Path
import subprocess

R = Path('/home/chenkeyi/.local/share/harbor-rsi/qwen35-new-cf500-tmax500-20261029')
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
canonical = R / 'scripts/observe_collection.py'
candidate = R / 'scripts/observe_collection_remaining_verifier_r321.py'
proof_path = R / 'checks/monitor-remaining-verifier-r326-resource/result.json'
proof = json.loads(proof_path.read_text())
if not proof['passed'] or proof['source_sha256'] != sha(candidate):
    raise ValueError('Accepted observer changed')
previous = '5a7a5e5bf1f509df4aea86e8ee986133a544beb2dd124f12e602e7cdbb402001'
if sha(canonical) != previous:
    raise ValueError('Observer identity changed; do not overwrite another window')
state = subprocess.run(['systemctl', '--user', 'is-active', 'qwen35-tb21-monitor.service'], capture_output=True, text=True).stdout.strip()
if state in ['active', 'activating', 'deactivating']:
    raise ValueError('Existing timer hook must finish before observer replacement')
helper=R/'scripts/collection_current_setup_blocks_r293.py'
renderer=R/'scripts/collection_reports_r325.py'
temporary = canonical.with_suffix('.r327.pending')
temporary.write_bytes(candidate.read_bytes())
temporary.replace(canonical)
out = dict(checked_at=datetime.datetime.now(datetime.timezone.utc).isoformat(), active_sha256=sha(canonical), previous_sha256=previous, resource_proof=str(proof_path),helper_sha256=sha(helper),renderer_sha256=sha(renderer), resource_proof_sha256=sha(proof_path), unchanged_cpu_quota='10%', unchanged_memory_limit_bytes=256*1024**2, unchanged_hook_timeout_seconds=90, actual_next_timer_execution_pending=True, shared_timer_or_service_changes=0, teacher_or_verifier_actions=0)
with (R / 'checks/monitor-public-cli-r327-ACTIVE.json').open('x') as stream:
    json.dump(out, stream, indent=2)
print(json.dumps(out))
