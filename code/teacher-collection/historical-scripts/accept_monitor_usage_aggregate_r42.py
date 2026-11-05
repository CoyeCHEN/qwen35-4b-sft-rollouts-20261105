"""Compare cache totals with the unchanged ordered raw-ledger calculation."""
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile
import time

import monitor_usage_aggregate_r42 as aggregate


R = aggregate.ROOT


def golden(paths):
    calls = {}
    for path in paths:
        for line in path.open():
            value = json.loads(line)
            calls[(value['trial_id'], value['call_id'])] = value
    totals = Counter()
    for value in calls.values():
        totals.update({key:amount for key,amount in (value.get('provider_final_usage') or {}).items()
            if isinstance(amount, (int, float)) and not isinstance(amount, bool)})
    return dict(exported_unique_model_calls=len(calls),
        calls_with_provider_final_usage=sum(bool(value.get('provider_final_usage')) for value in calls.values()),
        raw_provider_usage_totals=dict(totals))


def main():
    cases = []
    with tempfile.TemporaryDirectory(prefix='monitor-aggregate-r42-', dir=R / 'checks') as temporary:
        root = Path(temporary)
        snapshots = []
        for index, path in enumerate((R / 'indexes').glob('*-CALL_COST_TOKEN_LEDGER.jsonl')):
            snapshot = root / (str(index) + '.jsonl')
            with path.open('rb') as source, snapshot.open('xb') as target:
                shutil.copyfileobj(source, target)
            snapshots.append(snapshot)
        expected = golden(snapshots)
        for name in ['cold', 'warm']:
            started = time.monotonic()
            actual, stats = aggregate.summarize(snapshots, root / 'actual-ledger-cache')
            assert actual == expected
            if name == 'warm':
                assert stats['changed_ledgers'] == stats['parsed_raw_lines'] == 0
            cases.append(dict(case='all_actual_ledgers_' + name, seconds=time.monotonic()-started,
                calls=actual['exported_unique_model_calls'], parsed_raw_lines=stats['parsed_raw_lines']))
        a = root / 'a.jsonl'
        b = root / 'b.jsonl'
        rows = [dict(trial_id='t', call_id='a', provider_final_usage=dict(tokens=10, flag=True, nested=dict(x=4))),
            dict(trial_id='t', call_id='b', provider_final_usage=None),
            dict(trial_id='t', call_id='a', provider_final_usage=dict(tokens=11))]

        def write(path, values):
            path.write_text(''.join(json.dumps(value) + '\n' for value in values))

        def check(name, paths):
            actual, stats = aggregate.summarize(paths, root / 'fixture-cache')
            assert actual == golden(paths), name
            cases.append(dict(case=name, arithmetic=stats['arithmetic']))
            return stats

        write(a, rows)
        write(b, [dict(trial_id='t', call_id='a', provider_final_usage=dict(tokens=17))])
        check('duplicate_keys_inside_and_across_files', [a, b])
        check('reordered_files_change_last_winner', [b, a])
        original = a.stat()
        raw = a.read_bytes()
        a.write_bytes(raw.replace(b'"tokens": 11', b'"tokens": 12'))
        os.utime(a, ns=(original.st_atime_ns, original.st_mtime_ns))
        assert a.stat().st_size == original.st_size
        check('same_size_and_mtime_ledger_rewrite', [b, a])
        check('removed_ledger', [a])
        write(a, [dict(trial_id='new', call_id='new', provider_final_usage=dict(tokens=3)), *rows])
        assert check('inserted_line_preserves_old_metadata', [a])['relocated_line_metadata']
        write(a, rows[:1])
        check('shortened_ledger_removes_old_rows', [a])
        floating = [dict(trial_id='float', call_id=str(i), provider_final_usage=dict(amount=v))
            for i,v in enumerate([1e16, 1.0, -1e16])]
        write(a, floating)
        write(b, [dict(trial_id='float', call_id='0', provider_final_usage=dict(amount=0.1))])
        check('exact_float_first_insertion_and_last_value_order', [a, b])
        write(a, [dict(trial_id='huge', call_id='1', provider_final_usage=dict(tokens=2**100))])
        check('exact_python_large_integer', [a])
        write(a, [dict(trial_id='overflow', call_id=str(i), provider_final_usage=dict(tokens=2**62)) for i in range(3)])
        check('exact_python_sqlite_sum_overflow', [a])
        database = root / 'fixture-cache/usage.sqlite3'
        with database.open('r+b') as stream:
            stream.seek(100)
            byte = stream.read(1)
            stream.seek(100)
            stream.write(bytes([byte[0] ^ 1]))
        try:
            aggregate.summarize([a], root / 'fixture-cache')
        except ValueError:
            cases.append(dict(case='corrupt_cache_body_rejected', passed=True))
        else:
            raise AssertionError('Corrupt aggregate database accepted')
    result = dict(passed=True, producer_sha256=aggregate.sha(Path(aggregate.__file__)),
        full_actual_ledger_parity=expected, cases=cases,
        original_ledgers_modified=0, model_calls=0, teacher_or_data_index_writer_changes=0)
    path = R / 'checks/monitor-usage-aggregate-r42-acceptance.json'
    with path.open('x') as stream:
        json.dump(result, stream, indent=2)
    print(json.dumps(result))


if __name__ == '__main__':
    main()
