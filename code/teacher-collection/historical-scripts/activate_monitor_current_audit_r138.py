"""Bind the accepted health observer to current R15 reports and audited caches."""
import datetime
import hashlib
import json
from pathlib import Path

R=Path('/home/chenkeyi/.local/share/harbor-rsi/qwen35-new-cf500-tmax500-20261029')
sha=lambda path:hashlib.sha256(path.read_bytes()).hexdigest()
old=R/'scripts/observe_collection_health_io_r134.py'
new=R/'scripts/observe_collection_current_audit_r138.py'
reporter=R/'scripts/collection_reports_r138.py'
expected=old.read_text().replace('partial-primary-target-audit-r12/PARTIAL_DATA_TARGET_AUDIT_R12.json','partial-primary-target-audit-r136/PARTIAL_DATA_TARGET_AUDIT_R136.json').replace('from collection_reports_r123 import render','from collection_reports_r138 import render')
if new.read_text()!=expected:raise ValueError('Observer change exceeds report bindings')
expected=(R/'scripts/collection_reports_r123.py').read_text().replace("'r13','r14']","'r13','r14','r15']").replace('partial-primary-target-audit-r12','partial-primary-target-audit-r136').replace('_R12.json','_R136.json')
if reporter.read_text()!=expected:raise ValueError('Report change exceeds R15 and current partial audit')
audit=R/'checks/partial-primary-target-audit-r136/PARTIAL_DATA_TARGET_AUDIT_R136.json'
value=json.loads(audit.read_text())
if value['full_campaign_complete'] or value['formal_corpus_release'] or value['training_started']:raise ValueError('Partial audit was mislabeled as a release')
if sum(x['qualified_independent_tasks'] for x in value['pools'].values())!=452:raise ValueError('Accepted partial scope changed')
canonical=R/'scripts/observe_collection.py'
if sha(canonical)!='b53b2b8d19b1bae1b74f5f6c2d025bd00cf9bc364c9509021ee5dfb2bf7ce78e':raise ValueError('Prior accepted observer changed')
backup=R/'scripts/observe_collection_before_current_audit_r138.py'
with backup.open('xb') as stream:stream.write(canonical.read_bytes())
temporary=canonical.with_suffix('.r138-pending');temporary.write_bytes(new.read_bytes());temporary.replace(canonical)
proof=dict(checked_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),passed=True,
    observer_sha256=sha(canonical),reporter_sha256=sha(reporter),previous_observer_sha256=sha(backup),
    partial_audit_sha256=sha(audit),partial_independent_tasks=452,
    accepted_changes=['Recognize R15 in report text','Report existing R136 complete token/cache audit instead of historical R12'],
    timer_or_service_changes=0,teacher_dispatches=0,teacher_or_verifier_signals=0,source_sha256=sha(Path(__file__)))
with (R/'checks/monitor-current-audit-r138-activation.json').open('x') as stream:json.dump(proof,stream,indent=2)
print(json.dumps(proof))
