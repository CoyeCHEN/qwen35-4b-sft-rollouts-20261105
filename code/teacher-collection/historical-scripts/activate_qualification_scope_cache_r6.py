"""Switch a non-controller audit entry after its existing full scan completes."""
import datetime
import fcntl
import hashlib
import json
import os
from pathlib import Path
import time

R=Path('/home/chenkeyi/.local/share/harbor-rsi/qwen35-new-cf500-tmax500-20261029')
OLD_SCAN_PID=3887619


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    lock=(R/'checks/qualification-scope-cache-activation-r6.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    canonical=R/'scripts/audit_collection_results.py';new=R/'scripts/audit_collection_results_r6.py'
    proof=R/'checks/qualification-scope-cache-activation-r6.json'
    if proof.exists():raise FileExistsError('Observe the completed audit-source activation')
    original_sha=sha(canonical);new_sha=sha(new)
    assert not canonical.is_symlink()
    manifest=json.loads((R/'stream/collection-r4/deployment-r7b/CAMPAIGN.json').read_text())
    assert canonical.name not in manifest['helper_sha256']
    process=Path('/proc')/str(OLD_SCAN_PID)
    command=str(canonical).encode()
    if process.exists() and command not in (process/'cmdline').read_bytes().split(b'\0'):
        raise ValueError('Old audit PID identity changed before observation')
    observed_at=datetime.datetime.now(datetime.timezone.utc).isoformat();start=time.monotonic()
    old_start_ticks=(process/'stat').read_text().split()[21] if process.exists() else None
    while process.exists():
        if (process/'stat').read_text().split()[21]!=old_start_ticks:raise ValueError('Old scan PID was reused')
        if time.monotonic()-start>3600:raise TimeoutError('Keep old source active; no process is interrupted')
        time.sleep(1)
    # The same worker remains the only derived-index writer. No new auditor is
    # launched here; its next ordinary subprocess reads this new source.
    active=[]
    for p in Path('/proc').iterdir():
        if not p.name.isdigit():continue
        try:
            if command in (p/'cmdline').read_bytes().split(b'\0'):active.append(int(p.name))
        except OSError:pass
    if active:raise RuntimeError('Another full scan already started; keep the existing source until another idle point')
    assert sha(canonical)==original_sha and sha(new)==new_sha
    history=R/'scripts/audit_collection_results_before_scope_cache_r5.py'
    if history.exists():assert sha(history)==original_sha
    else:os.link(canonical,history)
    baseline={}
    for pool in ['CALIBFORGE','TMAX']:
        p=R/'indexes'/(pool+'_SUCCESS_INDEX.jsonl')
        baseline[pool]=dict(qualified_tasks=sum(1 for _ in p.open()),index_sha256=sha(p))
    temporary=canonical.with_name('.qualification-scope-cache-r6.pending')
    os.symlink(new.name,temporary);os.replace(temporary,canonical)
    value=dict(status='NEXT_ORDINARY_SCAN_USES_SCOPE_CACHE_NO_WORKER_RESTART',activated_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        old_scan_pid=OLD_SCAN_PID,old_start_ticks=old_start_ticks,old_scan_observed_at=observed_at,
        original_source_sha256=original_sha,original_source_preserved=str(history),new_source=str(new),new_source_sha256=new_sha,
        canonical_entry=str(canonical),sole_derived_writer_pid=502085,baseline=baseline,
        changes='Parse each immutable native sampling snapshot and each protocol scope once per full scan; cache SHA from exactly the parsed bytes. Qualification, target identity, reward and all checks remain unchanged.',
        source_and_evidence_hash_checks_retained=True,controllers_restarted=0,teacher_or_verifier_signals=0,
        data_worker_restarts=0,additional_derived_index_writers=0,model_calls=0)
    with proof.open('x') as stream:json.dump(value,stream,indent=2)
    print(json.dumps(value),flush=True)


if __name__=='__main__':main()
