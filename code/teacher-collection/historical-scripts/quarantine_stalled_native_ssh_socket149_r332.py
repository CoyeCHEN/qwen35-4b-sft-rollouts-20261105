"""Retire one failed listener without signaling existing SSH channels or Trials."""
import datetime
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import time

R = Path('/home/chenkeyi/.local/share/harbor-rsi/qwen35-new-cf500-tmax500-20261029')
OUT = R / 'checks/native-ssh-stalled-socket-maintenance-r332.json'
assert not OUT.exists(), 'Maintenance receipt already exists; inspect it instead of replaying.'
pool = json.loads((R / 'checks/native-ssh-preseed-pool-r119.json').read_text())
master = pool['masters'][14]
pid = master['pid']
socket = Path(master['socket'])
quarantine = socket.with_name(socket.name + '.quarantine-r332')
assert not quarantine.exists()
proc = Path('/proc') / str(pid)
start_ticks = proc.joinpath('stat').read_text().rsplit(')', 1)[1].split()[19]
cmdline = proc.joinpath('cmdline').read_bytes().split(b'\0')
assert start_ticks == master['start_ticks']
assert os.fsencode('-oControlPath=' + str(socket)) in cmdline
assert b'chenkeyi@180.163.192.17' in cmdline
before = socket.stat()
assert stat.S_ISSOCK(before.st_mode) and before.st_uid == os.getuid()
wrapper = R / 'client-bin-native-r119/ssh'
assert hashlib.sha256(wrapper.read_bytes()).hexdigest() == pool['native_client_sha256']
base = ['/usr/bin/ssh', '-F', str(R / 'ssh/client-v2.conf'),
        '-oProxyCommand=none', '-oProxyJump=none', '-oControlMaster=no',
        '-oControlPersist=no', '-oBatchMode=yes', '-oIdentitiesOnly=yes',
        '-oIdentityAgent=' + str(R / 'ssh/campaign17-agent-r6/agent.sock'),
        '-i', str(R / 'ssh/campaign17-agent-r6/identity.pub')]

def probe(path, command, timeout=6):
    begin = time.monotonic()
    try:
        result = subprocess.run(base + ['-S', str(path), 'chenkeyi@180.163.192.17', command],
                                capture_output=True, text=True, timeout=timeout)
        return dict(rc=result.returncode, stdout=result.stdout, stderr=result.stderr,
                    seconds=time.monotonic() - begin)
    except subprocess.TimeoutExpired:
        return dict(timeout=True, seconds=time.monotonic() - begin)

absent = socket.with_name('cftmx17-r332-absent')
assert not absent.exists()
engine_command = ('docker --host unix:///ssd/chenkeyi/qwen35-new-cf500-tmax500-20261029/'
                  "engine17-r1/socket/docker.sock info --format '{{.ID}}'")
fallback = probe(absent, engine_command, 10)
assert fallback.get('rc') == 0 and fallback['stdout'].strip() == '59c8ba22-0aa4-4aed-bc43-4e1b5989fa22', fallback
failed = probe(socket, 'true')
assert failed.get('timeout'), failed
assert socket.stat().st_ino == before.st_ino
socket.rename(quarantine)
after = probe(socket, engine_command, 10)
receipt = dict(checked_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
               source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
               master_pid=pid, master_start_ticks=start_ticks, old_socket=str(socket),
               quarantined_socket=str(quarantine), socket_inode=before.st_ino,
               before_stalled_probe=failed, independent_connection_probe=fallback,
               after_probe=after, native_wrapper_sha256=pool['native_client_sha256'],
               original_master_still_alive=proc.exists(),
               master_start_ticks_after=proc.joinpath('stat').read_text().rsplit(')', 1)[1].split()[19],
               accepted_missing_socket_behavior=pool['disconnected_socket_behavior'],
               teacher_or_verifier_signals=0, model_calls=0,
               frozen_source_changes=0, shared_daemon_changes=0,
               passed=after.get('rc') == 0 and after.get('stdout', '').strip() == '59c8ba22-0aa4-4aed-bc43-4e1b5989fa22')
with OUT.open('x') as stream:
    json.dump(receipt, stream, indent=2)
print(json.dumps(receipt))
assert receipt['passed'], receipt
