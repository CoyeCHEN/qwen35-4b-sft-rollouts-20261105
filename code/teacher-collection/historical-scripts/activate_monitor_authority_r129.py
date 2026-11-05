"""Atomically update only the existing observer's authority and sampler bindings."""
import ast
import datetime
import hashlib
import json
from pathlib import Path

R=Path('/home/chenkeyi/.local/share/harbor-rsi/qwen35-new-cf500-tmax500-20261029')
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
canonical=R/'scripts/observe_collection.py'
candidate=R/'scripts/observe_collection_live_slots_r129.py'
old=R/'scripts/observe_collection_live_slots_r123.py'
expected=old.read_text().replace("['R14','R13'","['R15','R14','R13'").replace('capture_teacher_slots149_r124.py','capture_teacher_slots149_r130.py')
if candidate.read_text()!=expected:raise ValueError('Observer change exceeds authority and sampler bindings')
sampler=R/'scripts/capture_teacher_slots149_r130.py'
expected_sampler=(R/'scripts/capture_teacher_slots149_r124.py').read_text().replace("['R14','R13'","['R15','R14','R13'").replace('actual-teacher-eight-and-backfill-r124-','actual-teacher-eight-and-backfill-r130-')
if sampler.read_text()!=expected_sampler:raise ValueError('Sampler change exceeds authority and evidence names')
for p in [candidate,sampler]:ast.parse(p.read_text())
proof=R/'checks/monitor-authority-r129-activation.json'
if proof.exists():
    value=json.loads(proof.read_text())
    if sha(canonical)!=value['observer_sha256']:raise ValueError('Activated observer changed')
else:
    if sha(canonical)!='0c40a21a56bba09efc0113366814e44227d2c4a5cc75a7b3f5f52bdc9652e428':raise ValueError('Unexpected previous observer')
    backup=R/'scripts/observe_collection_before_authority_r129.py'
    if backup.exists():raise FileExistsError(backup)
    backup.write_bytes(canonical.read_bytes())
    temp=canonical.with_suffix('.r129-pending');temp.write_bytes(candidate.read_bytes());temp.replace(canonical)
    value=dict(checked_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),passed=True,
        observer_sha256=sha(canonical),previous_observer_sha256=sha(backup),sampler_sha256=sha(sampler),
        accepted_changes=['Recognize R15 as the newest dispatch authority','Use equivalent R130 slot sampler recognizing R15'],
        timer_or_service_changes=0,teacher_dispatches=0,teacher_or_verifier_signals=0,source_sha256=sha(Path(__file__)))
    with proof.open('x') as f:json.dump(value,f,indent=2)
print(json.dumps(value))
