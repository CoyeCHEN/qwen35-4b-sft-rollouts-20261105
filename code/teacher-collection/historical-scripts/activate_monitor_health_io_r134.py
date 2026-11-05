"""Accept bounded health I/O changes without changing the timer or data audit."""
import datetime
import hashlib
import importlib.util
import json
from pathlib import Path

R=Path('/home/chenkeyi/.local/share/harbor-rsi/qwen35-new-cf500-tmax500-20261029')
sha=lambda path:hashlib.sha256(path.read_bytes()).hexdigest()
old=R/'scripts/observe_collection_live_slots_r129.py'
new=R/'scripts/observe_collection_health_io_r134.py'
canonical=R/'scripts/observe_collection.py'
expected=old.read_text().replace(
    '    finite_failures=finite_environment_failures(ROOT)\n    environment=[]\n',
    """    finite_failures=finite_environment_failures(ROOT)
    # The health report uses a directory-entry snapshot, as does Ready above.
    # Avoid repeating one nonexistent-file stat per Task and historical root.
    failure_files_by_task={}
    for root in runtime_roots:
        for path in (root/'environment-failures').glob('*.json'):
            failure_files_by_task.setdefault(path.stem,[]).append(path)
    environment=[]
""").replace(
    "        failure_paths=[root/'environment-failures'/(ident+'.json') for root in runtime_roots]",
    "        failure_paths=failure_files_by_task.get(ident,[]).copy()").replace(
    """        call_ledgers=[dict(path=str(path),bytes=path.stat().st_size,
            sha256=hashlib.sha256(path.read_bytes()).hexdigest()) for path in ledger_paths],""",
    """        call_ledgers=[dict(path=str(path),bytes=path.stat().st_size,
            modified_at_ns=path.stat().st_mtime_ns,integrity_sha256_deferred_to_full_data_audit=True) for path in ledger_paths],""")
if new.read_text()!=expected:raise ValueError('Unexpected observer semantics change')
resource=R/'checks/monitor-health-io-r134-resource/result.json'
test=json.loads(resource.read_text())
if not test['passed'] or test['source_sha256']!=sha(new) or test['wall_seconds']>=75:
    raise ValueError('Insufficient margin under the existing monitor resource limits')
authority=json.loads((R/'checks/CURRENT_DISPATCH_AUTHORITY_R15.json').read_text())
manifest=json.loads(Path(authority['manifest']).read_text())
roots=list(dict.fromkeys(Path(path) for path in manifest['readiness_roots']))
spec=importlib.util.spec_from_file_location('observer_candidate',new)
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
finite=module.finite_environment_failures(R)
lookup={}
for root in roots:
    for path in (root/'environment-failures').glob('*.json'):
        lookup.setdefault(path.stem,[]).append(path)
identifiers=set(finite)|set(lookup)
for name in ['CALIBFORGE_500_TASKS.jsonl','TMAX_RUNTIME_CANDIDATES_V2.jsonl']:
    identifiers.update(json.loads(line)['task_id'] for line in (R/'manifests'/name).open())
for ident in identifiers:
    original=[root/'environment-failures'/(ident+'.json') for root in roots]
    candidate=lookup.get(ident,[]).copy()
    if ident in finite:
        original.append(finite[ident][0]);candidate.append(finite[ident][0])
    def choose(paths):
        return max((path for path in paths if path.exists()),
            key=lambda path:(path.stat().st_mtime_ns,str(path)),
            default=roots[-1]/'environment-failures'/(ident+'.json'))
    if choose(original)!=choose(candidate):raise ValueError('Failure evidence precedence differs')
proof=R/'checks/monitor-health-io-r134-activation.json'
if proof.exists():raise FileExistsError('Observe existing activation')
if sha(canonical)!='7ed4b5fc4c24dbdd988c8a2fc4d3147de3089b30379765630d90670614b9099d':
    raise ValueError('Previous observer changed')
backup=R/'scripts/observe_collection_before_health_io_r134.py'
with backup.open('xb') as f:f.write(canonical.read_bytes())
temporary=canonical.with_suffix('.r134-pending');temporary.write_bytes(new.read_bytes());temporary.replace(canonical)
value=dict(checked_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),passed=True,
    observer_sha256=sha(canonical),previous_observer_sha256=sha(backup),
    failure_evidence_precedence_equal_for_task_ids=len(identifiers),
    resource_proof=str(resource),resource_proof_sha256=sha(resource),
    call_ledger_content_untouched=True,full_call_ledger_sha_verification='Preserved in data audit; no repeated large ledger read by health hook',
    timer_or_shared_service_changes=0,teacher_dispatches=0,teacher_or_verifier_signals=0,
    source_sha256=sha(Path(__file__)))
with proof.open('x') as f:json.dump(value,f,indent=2)
print(json.dumps(value))
