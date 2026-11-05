"""Compare complete current ledger totals and mutation/dedup edge cases."""
from collections import Counter
import datetime
import hashlib
import json
import os
from pathlib import Path
import tempfile
import time

import monitor_usage_cache_r27 as cache

R = cache.ROOT


def summarize(files, cached):
    calls = {}
    for file in files:
        if cached:
            for _,trial,call,present,number in cache.records(file):
                calls[(trial,call)] = (present,number)
        else:
            for line in file.open():
                value = json.loads(line)
                usage = value.get('provider_final_usage')
                calls[(value['trial_id'],value['call_id'])] = (
                    bool(usage), {k:v for k,v in (usage or {}).items() if type(v) in [int,float]})
    totals = Counter()
    for _,number in calls.values():
        totals.update(number)
    return dict(unique_calls=len(calls), calls_with_final_usage=sum(p for p,_ in calls.values()), totals=dict(totals))


def main():
    checks = []
    original_root = cache.CACHE_ROOT
    with tempfile.TemporaryDirectory(prefix='usage-r27-',dir=R / 'derived') as tmp:
        tmp = Path(tmp)
        cache.CACHE_ROOT = tmp / 'cache'
        a,b = tmp / 'a.jsonl',tmp / 'b.jsonl'
        row = dict(trial_id='trial-a', call_id='call-a', provider_final_usage=dict(
            tokens=4, cached=2, fraction=1.25, nested=dict(ignored=7), boolean=True))
        a.write_text(json.dumps(row) + '\n' + json.dumps(dict(trial_id='trial-a',call_id='call-b')) + '\n')
        b.write_text(json.dumps(dict(row,provider_final_usage=dict(tokens=7))) + '\n')
        assert summarize([a,b],False) == summarize([a,b],True) == summarize([a,b],True)
        checks += ['cold_and_warm_match_original', 'duplicate_call_last_wins_in_original_file_order',
            'missing_usage_not_counted_as_reported', 'nested_values_and_boolean_not_summed']
        state = a.stat()
        a.write_text(a.read_text().replace('"tokens": 4','"tokens": 9'))
        os.utime(a,ns=(state.st_atime_ns,state.st_mtime_ns))
        assert summarize([a],False) == summarize([a],True)
        checks.append('same_size_same_mtime_line_mutation_recomputed')
        a.write_text(a.read_text().splitlines()[0] + '\n')
        assert summarize([a,b],False) == summarize([a,b],True)
        checks.append('removed_call_does_not_persist_in_totals')
        pointer = json.loads((cache.CACHE_ROOT / a.name / 'head.json').read_text())
        proof = cache.CACHE_ROOT / a.name / pointer['proof']
        proof.write_bytes(proof.read_bytes() + b' ')
        try:
            cache.records(a)
        except ValueError:
            checks.append('corrupt_usage_view_rejected')
        else:
            raise AssertionError('Corrupt usage view was accepted')
    cache.CACHE_ROOT = original_root
    files = list((R / 'indexes').glob('*-CALL_COST_TOKEN_LEDGER.jsonl'))
    start = time.monotonic()
    original = summarize(files,False)
    original_seconds = time.monotonic() - start
    start = time.monotonic()
    candidate = summarize(files,True)
    cold_seconds = time.monotonic() - start
    start = time.monotonic()
    warm = summarize(files,True)
    warm_seconds = time.monotonic() - start
    assert original == candidate == warm
    checks.append('all_actual_ledgers_original_cold_warm_totals_equal')
    proof = dict(passed=True, checked_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),checks=checks,
        source_sha256=hashlib.sha256(Path(cache.__file__).read_bytes()).hexdigest(),
        ledger_files=[dict(path=str(p),sha256=hashlib.sha256(p.read_bytes()).hexdigest(),bytes=p.stat().st_size) for p in files],
        exact_original_totals=original, original_seconds=original_seconds, cold_seconds=cold_seconds,
        warm_seconds=warm_seconds, raw_ledgers_modified=0, model_calls=0)
    with (R / 'checks/monitor-usage-cache-r27-acceptance.json').open('x') as stream:
        json.dump(proof,stream,indent=2)
    print(json.dumps(proof))


if __name__ == '__main__':
    main()
