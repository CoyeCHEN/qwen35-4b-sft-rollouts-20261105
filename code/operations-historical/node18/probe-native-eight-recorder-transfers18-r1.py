"""Eight native SSH transfers of a closed archive, with no model or Task runs."""
import asyncio
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

from harbor_remote_docker.transport import run, ssh_target

R = Path('/ssd/chenkeyi/qwen35-sft-772-20261101')
REMOTE = '/home/chenkeyi/.local/share/harbor-rsi/qwen35-new772-tb21-20261101/controller18-network-probe-r1/closed-chess-native.tar'
EXPECTED = 'b6d57540cf09b3ada4c1fdf2524bc424dd6f3701ea642f9b33de3bdf77e4715f'
SIZE = 1646059520
ENDPOINT = 'ssh://chenkeyi@127.0.0.1:18449'
LIMIT = 3600


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def process_identity(pid):
    path = Path('/proc') / str(pid) / 'stat'
    return path.read_text().rsplit(')', 1)[1].split()[19] if path.exists() else None


async def main():
    os.environ['PATH'] = str(R / 'formal-controller18-client-bin-r1') + ':' + os.environ['PATH']
    assert subprocess.check_output(['docker', '--host', ENDPOINT, 'info', '--format', '{{.ID}}'],
        text=True, timeout=20).strip() == 'c6e16cdf-e878-4cc5-84c8-78a56c54b5c5'
    original = {pid: process_identity(pid) for pid in
        [840835, 1194582, 1208295, 1208296, 1208297, 1208298, 1890941, 1911581]}
    assert all(original.values()), original
    output = R / 'native-eight-recorder-transfer-probe-r1'
    output.mkdir()
    states = [dict(index=i, started=None, finished=None, return_code=None) for i in range(8)]
    targets = [output / ('stream-' + str(i) + '.tar') for i in range(8)]

    async def transfer(index):
        state = states[index]
        state['started'] = time.time()
        begin = time.monotonic()
        try:
            result = await run(ssh_target(ENDPOINT) + ['cat ' + REMOTE],
                timeout=LIMIT, target=targets[index])
            state['return_code'] = result.return_code
            state['stderr'] = result.stderr[-500:]
        except Exception as error:
            state['error'] = repr(error)
        finally:
            state['seconds'] = time.monotonic() - begin
            state['finished'] = time.time()
            state['bytes'] = targets[index].stat().st_size if targets[index].exists() else 0

    tasks = [asyncio.create_task(transfer(i)) for i in range(8)]
    overlap = None
    with (output / 'progress.jsonl').open('x') as log:
        while not all(t.done() for t in tasks):
            sample = dict(at=time.time(),
                active=sum(s['started'] is not None and s['finished'] is None for s in states),
                bytes=[p.stat().st_size if p.exists() else 0 for p in targets],
                original_process_ticks={str(pid): process_identity(pid) for pid in original})
            if sample['active'] == 8 and min(sample['bytes']) >= 1024 * 1024 and overlap is None:
                overlap = sample
            log.write(json.dumps(sample) + '\n')
            log.flush()
            await asyncio.sleep(2)
    await asyncio.gather(*tasks)
    for state, target in zip(states, targets):
        state['sha256'] = sha(target) if state.get('return_code') == 0 else None
        state['verified'] = state.get('return_code') == 0 and state['bytes'] == SIZE and state['sha256'] == EXPECTED
        state['exceeded_original_600_sec'] = state['seconds'] > 600
    value = dict(passed=all(s['verified'] for s in states) and overlap is not None,
        at=time.time(), kind='EIGHT_CONCURRENT_NATIVE_TRANSFER_CLOSED_RECORDER_ONLY',
        streams=states, actual_eight_stream_overlap=overlap, source_archive_sha256=EXPECTED,
        source_archive_bytes=SIZE, native_transfer_probe_timeout_sec=LIMIT,
        original_provider_transfer_timeout_sec=600, original_deadline_exceeded=sum(s['exceeded_original_600_sec'] for s in states),
        all_original_process_identities_preserved=all(process_identity(pid) == ticks for pid, ticks in original.items()),
        original_process_identities=original, actual_model_or_task_calls=0,
        official_task_verifier_wheel_provider_or_research_budgets_changed=False,
        no_formal_deployment_promoted=True, source_sha256=sha(Path(__file__)))
    proof = R / 'checks/NATIVE_EIGHT_RECORDER_TRANSFER_ACCEPTANCE_R1.json'
    assert not proof.exists()
    proof.write_text(json.dumps(value, indent=2) + '\n')
    print(json.dumps(value), flush=True)


if __name__ == '__main__':
    asyncio.run(main())
