"""Fresh read-only149 retirement evidence from the uninterrupted native event reader."""
import datetime
import hashlib
import json
import os
from pathlib import Path
import subprocess

R = Path('/home/chenkeyi/.local/share/harbor-rsi/qwen35-new-cf500-tmax500-20261029')
sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
read = lambda path: json.loads(path.read_text())


def main():
    scope = ('cftmaxstreamr420261030-', 'cftmaxresidentbufferr120261030-',
        'cftmaxresidentbufferr150261030-', 'cftmaxinfraacceptancer720261030-', 'rsi-tmax-infra-recovery-r7-')
    capture_path = R / 'checks/owned-docker-events149-r7.json'
    capture = read(capture_path)
    started = datetime.datetime.fromisoformat(capture['started_at']).timestamp()
    boot = next(int(line.split()[1]) for line in Path('/proc/stat').read_text().splitlines() if line.startswith('btime '))
    processes = []
    expected = str(R / 'scripts/capture_owned_docker_events149_r7.py').encode()
    for process in Path('/proc').iterdir():
        if not process.name.isdigit():
            continue
        try:
            argv = (process / 'cmdline').read_bytes().split(b'\0')
            fields = (process / 'stat').read_text().rsplit(')', 1)[1].split()
        except OSError:
            continue
        if expected in argv:
            timestamp = boot + int(fields[19]) / os.sysconf('SC_CLK_TCK')
            assert abs(timestamp - started) < 5
            processes.append(dict(pid=int(process.name), start_ticks=fields[19], start_time_matches_original_capture=True))
    assert len(processes) == 1, 'Continuous event coverage is unproved; do not claim a zero-create interval'
    parent = processes[0]['pid']
    children = []
    for process in Path('/proc').iterdir():
        if not process.name.isdigit():
            continue
        try:
            fields = (process / 'stat').read_text().rsplit(')', 1)[1].split()
            argv = (process / 'cmdline').read_bytes().split(b'\0')
            if int(fields[1]) == parent and b'events' in argv:
                children.append(int(process.name))
        except OSError:
            continue
    assert len(children) == 1
    retired_path = R / 'checks/legacy-resident-preparation-retired-r7.json'
    retired = read(retired_path)
    fence_path = Path(retired['fence'])
    assert sha(fence_path) == retired['fence_sha256']
    fence = read(fence_path)
    cutoff = datetime.datetime.fromisoformat(fence['checked_at']).timestamp()
    assert started <= cutoff
    event_path = R / 'checks/owned-docker-events149-r7.jsonl'
    events = [json.loads(line) for line in event_path.open()]
    creates = [row for row in events if row['action'] == 'create' and row['time_nano'] / 1e9 >= cutoff]
    assert not creates
    engine = subprocess.run(['docker', 'info', '--format', '{{.ID}}'], capture_output=True, text=True, check=True, timeout=30).stdout.strip()
    assert engine == capture['engine_id'] == 'c6e16cdf-e878-4cc5-84c8-78a56c54b5c5'
    rows = subprocess.run(['docker', 'ps', '-a', '--format', '{{.ID}} {{.Names}}'],
        capture_output=True, text=True, check=True, timeout=30).stdout.splitlines()
    containers = [row for row in rows if row.split(' ', 1)[1].startswith(scope)]
    assert not containers
    out = dict(passed=True, checked_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        engine_id=engine, capture_started_at=capture['started_at'], no_owned_creates_since=fence['checked_at'],
        original_continuous_event_reader=processes[0], native_event_stream_child=children[0],
        event_log_sha256=sha(event_path), observed_owned_events=len(events),
        new_owned149_creates_after_fence=creates, all_running_or_stopped_owned149_containers=containers,
        full_149_daemon_history_is_not_assumed=True, other_window_resources_not_modified=True,
        scope_prefixes=scope, original_retirement_proof_sha256=sha(retired_path),
        admission_fence_sha256=sha(fence_path), model_calls=0, mutations=0, source_sha256=sha(Path(__file__)))
    destination = R / 'checks/LEGACY149_RETIRED_CURRENT_R438.json'
    with destination.open('x') as stream:
        json.dump(out, stream, indent=2)
    print(json.dumps(out))


if __name__ == '__main__':
    main()
