"""Publish the current native service gate in the same accepted20min monitor."""
import datetime
import hashlib
import json
from pathlib import Path
import subprocess

R=Path('/home/chenkeyi/.local/share/harbor-rsi/qwen35-new-cf500-tmax500-20261029')
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
source=R/'scripts/observe_collection_service_gate_r403.py'
canonical=R/'scripts/observe_collection.py'
equivalence=R/'checks/monitor-service-gate-r403-source-equivalence.json'
review=json.loads(equivalence.read_text())
assert review['passed'] and sha(source)==review['candidate_source_sha256']
assert source.read_text().replace(review['extra_block'],'')==(R/'scripts/observe_collection_native_json_r386.py').read_text()
assert sha(canonical)==review['base_source_sha256']=='f0e415011aa59fe0df15bd3b788a9c4fc3a2d6c5f3716e3625a21465ce230c57'
proof_path=R/'checks/monitor-service-gate-r404-resource/result.json'
proof=json.loads(proof_path.read_text())
assert proof['passed'] and proof['source_sha256']==sha(source) and proof['wall_seconds']<75
state=subprocess.run(['systemctl','--user','is-active','qwen35-tb21-monitor.service'],capture_output=True,text=True).stdout.strip()
assert state=='inactive','Let the ordinary shared monitor lifecycle finish first'
p=canonical.with_suffix('.r405.pending');p.write_bytes(source.read_bytes());p.replace(canonical)
value=dict(passed=True,checked_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),source_sha256=sha(source),
 resource_proof_sha256=sha(proof_path),source_equivalence_sha256=sha(equivalence),
 existing20minute_timer_and_shared_service_unchanged=True,cpu_quota='10%',memory_max=256*1024**2,hook_timeout=90,
 teacher_provider_or_task_changes=0,next_actual_timer_execution_pending=True)
with (R/'checks/MONITOR_SERVICE_GATE_R405_ACTIVE.json').open('x') as f:json.dump(value,f,indent=2)
print(json.dumps(value))
