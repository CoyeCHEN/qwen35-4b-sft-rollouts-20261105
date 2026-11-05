"""Exact usage totals cached with SQLite; every source ledger is fully hashed.

Retain original file/line precedence and duplicate-call last-value semantics.
Integer totals use SQLite; floating/large-integer arithmetic uses the original
ordered Python calculation. This is a disposable monitor cache, never a data
writer, model ledger, scheduler, or source of billed USD.
"""
from collections import Counter
import fcntl
import hashlib
import json
from pathlib import Path
import sqlite3
from uuid import uuid4


ROOT = Path('/home/chenkeyi/.local/share/harbor-rsi/qwen35-new-cf500-tmax500-20261029')
CACHE_ROOT = ROOT / 'derived/monitor-usage-aggregate-r42'


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def exact_python(connection):
    calls = {}
    for trial, call, present, numeric in connection.execute(
            'SELECT r.trial,r.call,r.present,r.numeric FROM rows r JOIN files f ON r.path=f.path ORDER BY f.ordinal,r.ordinal'):
        calls[(trial, call)] = (present, json.loads(numeric))
    totals = Counter()
    for _, numeric in calls.values():
        totals.update(numeric)
    return dict(exported_unique_model_calls=len(calls),
        calls_with_provider_final_usage=sum(value[0] for value in calls.values()),
        raw_provider_usage_totals=dict(totals))


def summarize(paths, cache_root=CACHE_ROOT):
    paths = list(paths)
    cache_root = Path(cache_root)
    cache_root.mkdir(parents=True, exist_ok=True)
    lock = (cache_root / 'cache.lock').open('a')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    producer = sha(Path(__file__))
    database = cache_root / 'usage.sqlite3'
    head = cache_root / 'head.json'
    if head.exists():
        pointer = json.loads(head.read_text())
        if pointer['producer_sha256'] != producer or sha(database) != pointer['database_sha256']:
            raise ValueError('Usage aggregate cache producer/body changed; preserve evidence and use a new version')
    elif database.exists():
        raise ValueError('Usage aggregate database has no matching integrity head')
    connection = sqlite3.connect(database)
    stats = dict(source_ledgers=len(paths), changed_ledgers=0, parsed_raw_lines=0,
        reused_line_metadata=0, relocated_line_metadata=0, every_source_fully_rehashed=True,
        producer_sha256=producer, arithmetic='EXACT_SQLITE_INTEGER')
    sources = []
    try:
        connection.execute('CREATE TABLE IF NOT EXISTS files(path TEXT PRIMARY KEY,ordinal INTEGER,sha TEXT)')
        connection.execute('CREATE TABLE IF NOT EXISTS rows(path TEXT,ordinal INTEGER,line_sha TEXT,trial TEXT,call TEXT,present INTEGER,numeric TEXT,PRIMARY KEY(path,ordinal))')
        connection.execute('CREATE INDEX IF NOT EXISTS call_identity ON rows(trial,call)')
        retained = {str(path) for path in paths}
        for path, in connection.execute('SELECT path FROM files').fetchall():
            if path not in retained:
                connection.execute('DELETE FROM rows WHERE path=?', (path,))
                connection.execute('DELETE FROM files WHERE path=?', (path,))
        for ordinal, path in enumerate(paths):
            path = Path(path)
            with path.open('rb') as stream:
                checksum = hashlib.file_digest(stream, 'sha256').hexdigest()
                sources.append(dict(path=str(path), sha256=checksum))
                prior = connection.execute('SELECT sha FROM files WHERE path=?', (str(path),)).fetchone()
                connection.execute('INSERT INTO files VALUES(?,?,?) ON CONFLICT(path) DO UPDATE SET ordinal=excluded.ordinal',
                    (str(path), ordinal, checksum))
                if prior and prior[0] == checksum:
                    continue
                stats['changed_ledgers'] += 1
                old = connection.execute('SELECT ordinal,line_sha,trial,call,present,numeric FROM rows WHERE path=?', (str(path),)).fetchall()
                by_position = {row[0]:row[1:] for row in old}
                by_sha = {row[1]:row[1:] for row in old}
                updates = []
                length = 0
                stream.seek(0)
                for line_no, line in enumerate(stream):
                    length += 1
                    digest = hashlib.sha256(line).hexdigest()
                    if line_no in by_position and by_position[line_no][0] == digest:
                        stats['reused_line_metadata'] += 1
                        continue
                    if digest in by_sha:
                        data = by_sha[digest]
                        stats['relocated_line_metadata'] += 1
                    else:
                        record = json.loads(line)
                        usage = record.get('provider_final_usage')
                        numeric = {key:value for key,value in (usage or {}).items() if type(value) in [int, float]}
                        data = (digest, record['trial_id'], record['call_id'], int(bool(usage)), json.dumps(numeric))
                        stats['parsed_raw_lines'] += 1
                    updates.append((str(path), line_no, *data))
                stream.seek(0)
                if hashlib.file_digest(stream, 'sha256').hexdigest() != checksum:
                    raise ValueError('Raw usage ledger changed in place while indexing')
                connection.executemany('INSERT INTO rows VALUES(?,?,?,?,?,?,?) ON CONFLICT(path,ordinal) DO UPDATE SET line_sha=excluded.line_sha,trial=excluded.trial,call=excluded.call,present=excluded.present,numeric=excluded.numeric', updates)
                connection.execute('DELETE FROM rows WHERE path=? AND ordinal>=?', (str(path), length))
                connection.execute('UPDATE files SET sha=? WHERE path=?', (checksum, str(path)))
        connection.execute('DROP VIEW IF EXISTS winners')
        connection.execute('CREATE TEMP VIEW winners AS SELECT * FROM (SELECT r.*,ROW_NUMBER() OVER(PARTITION BY r.trial,r.call ORDER BY f.ordinal DESC,r.ordinal DESC) AS precedence FROM rows r JOIN files f ON r.path=f.path) WHERE precedence=1')
        unique, present = connection.execute('SELECT COUNT(*),COALESCE(SUM(present),0) FROM winners').fetchone()
        complex_arithmetic = connection.execute("SELECT EXISTS(SELECT 1 FROM winners w,json_each(w.numeric) j WHERE j.type!='integer' OR typeof(j.value)!='integer')").fetchone()[0]
        if complex_arithmetic:
            result = exact_python(connection)
            stats['arithmetic'] = 'EXACT_ORDERED_PYTHON_FLOAT_OR_LARGE_INTEGER'
        else:
            try:
                totals = dict(connection.execute('SELECT j.key,SUM(j.value) FROM winners w,json_each(w.numeric) j GROUP BY j.key'))
                result = dict(exported_unique_model_calls=unique, calls_with_provider_final_usage=present,
                    raw_provider_usage_totals=totals)
            except sqlite3.OperationalError as error:
                if str(error) != 'integer overflow':
                    raise
                result = exact_python(connection)
                stats['arithmetic'] = 'EXACT_ORDERED_PYTHON_INTEGER_OVERFLOW'
        connection.commit()
    finally:
        connection.close()
    checksum = sha(database)
    pending = head.with_name('head.pending-' + uuid4().hex)
    pending.write_text(json.dumps(dict(producer_sha256=producer, database_sha256=checksum,
        sources=sources, sqlite_version=sqlite3.sqlite_version)))
    pending.replace(head)
    stats.update(database_sha256=checksum, cache_root=str(cache_root), sources=sources)
    return result, stats
