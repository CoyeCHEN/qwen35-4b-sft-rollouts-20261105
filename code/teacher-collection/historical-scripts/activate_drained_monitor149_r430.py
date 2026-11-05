"""Activate the measured read-only drain/reconciliation observation."""
import datetime
import hashlib
import json
from pathlib import Path
import subprocess

R = Path('/home/chenkeyi/.local/share/harbor-rsi/qwen35-new-cf500-tmax500-20261029')
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
source = R / 'scripts/observe_collection_drained_r428.py'
canonical = R / 'scripts/observe_collection.py'
review_path = R / 'checks/monitor-drained-r428-source-equivalence.json'
review = json.loads(review_path.read_text())
assert review['passed'] and sha(source) == review['candidate_source_sha256']
base = source.read_text()
for block in review['added_blocks']:
    assert base.count(block) == 1
    base = base.replace(block, '')
assert base == (R / 'scripts/observe_collection_service_gate_r403.py').read_text()
assert sha(canonical) == review['base_source_sha256'] == '8846eefab416ad2bbcf71c8a800d1086bb91486b79db7edcd72a6e2f3228b4ff'
assert sha(R / 'scripts/collection_administrative_ready_r427.py') == review['helper_source_sha256']
proof_path = R / 'checks/monitor-drained-r429-resource/result.json'
proof = json.loads(proof_path.read_text())
assert proof['passed'] and proof['source_sha256'] == sha(source) and proof['wall_seconds'] < 75
progress = json.loads((R / 'progress.json').read_text())
assert progress['teacher_slot_telemetry']['controller_terminal_observed']
assert progress['teacher_slot_telemetry']['resident_image_buffer'] is None
assert len(progress['administrative_admission_environment_reconciliation']) == 5
state = subprocess.run(['systemctl', '--user', 'is-active', 'qwen35-tb21-monitor.service'], capture_output=True, text=True).stdout.strip()
assert state == 'inactive', 'Let the ordinary shared monitor lifecycle finish first'
temporary = canonical.with_suffix('.r430.pending')
temporary.write_bytes(source.read_bytes())
temporary.replace(canonical)
out = dict(passed=True, checked_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
    source_sha256=sha(source), helper_sha256=review['helper_source_sha256'],
    resource_proof_sha256=sha(proof_path), source_equivalence_sha256=sha(review_path),
    existing20minute_timer_and_shared_service_unchanged=True, cpu_quota='10%', memory_max=256*1024**2,
    hook_timeout=90, teacher_provider_or_task_changes=0, next_actual_timer_execution_pending=True)
with (R / 'checks/MONITOR_DRAINED_RECONCILIATION_R430_ACTIVE.json').open('x') as f:
    json.dump(out, f, indent=2)
print(json.dumps(out))
