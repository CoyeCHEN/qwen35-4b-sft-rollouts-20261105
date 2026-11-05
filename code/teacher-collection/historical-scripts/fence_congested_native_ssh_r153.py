"""Retire only a congested campaign multiplex listener; preserve all sessions.

The frozen client already uses ordinary direct SSH when a control socket is
absent. Do not kill the master, Task, CLI, Verifier, or shared service.
"""
import datetime
import hashlib
import json
import os
from pathlib import Path
import shlex
import subprocess
import tempfile
import time

R=Path('/home/chenkeyi/.local/share/harbor-rsi/qwen35-new-cf500-tmax500-20261029')
sha=lambda path:hashlib.sha256(path.read_bytes()).hexdigest()
d=json.loads((R/'configs/campaign-deployment17-r16.json').read_text())
pool_path=Path(d['native_ssh_pool']['path'])
if sha(pool_path)!=d['native_ssh_pool']['sha256']:raise ValueError('Frozen pool identity changed')
pool=json.loads(pool_path.read_text());member=next(x for x in pool['masters'] if x['slot']==6)
proc=Path('/proc')/str(member['pid'])
def same():
    return proc.exists() and (proc/'stat').read_text().rsplit(')',1)[1].split()[19]==member['start_ticks']
if not same() or not Path(member['socket']).exists():raise ValueError('Observe existing member status; do not repeat listener retirement')
D=R/'checks/native-ssh-congestion-r153';D.mkdir(exist_ok=False)
tcp=subprocess.run(['ss','-tinp','dst','180.163.192.17'],capture_output=True,text=True,check=True,timeout=10).stdout.splitlines()
observed=[]
for i,line in enumerate(tcp):
    if 'pid='+str(member['pid'])+',' in line:observed=[line,tcp[i+1] if i+1<len(tcp) else '']
if not observed:raise ValueError('No current TCP evidence for this exact accepted member')
with (D/'STARTED.json').open('x') as stream:
    json.dump(dict(checked_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),member=member,
        tcp=observed,source_sha256=sha(Path(__file__)),model_calls=0,teacher_or_verifier_signals=0),stream,indent=2)
payload=hashlib.shake_256(b'cftmax-native-transfer-r153-synthetic-not-task-data').digest(6604800)
expected=hashlib.sha256(payload).hexdigest()
remote=d['runtime']['ssd_root']+'/native-transfer-diagnostic-r153.bin'
command='umask 077; timeout 20 sh -c '+shlex.quote('cat > '+shlex.quote(remote)+'; sha256sum -- '+shlex.quote(remote))
fresh=[d['ssh'][0],'-oControlMaster=no','-oControlPath=none','-oControlPersist=no',*d['ssh'][1:],d['host'],command]
with tempfile.TemporaryDirectory(prefix='cftmax-stream-r153-',dir=D) as temp:
    root=Path(temp);source=root/'synthetic.bin';source.write_bytes(payload)
    out=root/'stdout';err=root/'stderr';started=time.monotonic()
    with source.open('rb') as stdin,out.open('wb') as stdout,err.open('wb') as stderr:
        child=subprocess.Popen(fresh,stdin=stdin,stdout=stdout,stderr=stderr)
        try:code=child.wait(timeout=25)
        except subprocess.TimeoutExpired:
            child.kill();child.wait(timeout=5)
            with (D/'INDEPENDENT_TRANSFER_FAILED.json').open('x') as stream:
                json.dump(dict(timeout=True,elapsed_seconds=time.monotonic()-started,probe_pid=child.pid,
                    listener_changed=False,teacher_or_verifier_signals=0),stream,indent=2)
            raise TimeoutError('Fresh transfer also failed; keep the accepted existing listener untouched')
    elapsed=time.monotonic()-started
    with (D/'INDEPENDENT_TRANSFER_RESULT.json').open('x') as stream:
        json.dump(dict(exit_code=code,seconds=elapsed,stdout=out.read_text()[-300:],
            stderr=err.read_text()[-600:],bytes=len(payload),expected_sha256=expected),stream,indent=2)
    if code or out.read_text().split()[0]!=expected:raise ValueError('Independent SSH did not transfer and verify the exact synthetic payload')
    transfer=dict(seconds=elapsed,bytes=len(payload),sha256=expected,exit_code=code,remote_path=remote)
if not same():raise ValueError('Master identity changed during independent comparison')
if elapsed>=15:raise ValueError('Fresh transfer did not provide adequate evidence; do not alter the listener')
# OpenSSH -O stop requests no new multiplexing sessions. Unlike -O exit,
# it leaves every existing channel and its master process running.
reply=subprocess.run([d['ssh'][0],'-F',str(R/'ssh/client-v2.conf'),'-S',member['socket'],'-O','stop',d['host']],
    capture_output=True,text=True,timeout=15)
if reply.returncode:raise ValueError('Native stop-listening control operation failed; inspect exact member')
value=dict(checked_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
    frozen_pool_manifest_sha256=sha(pool_path),accepted_member=member,observed_tcp=observed,
    independent_synthetic_transfer=transfer,operation='OpenSSH -O stop: stop accepting new multiplex sessions; preserve existing channels',
    operation_exit_code=reply.returncode,operation_reply=reply.stderr.strip(),
    master_same_pid_still_alive=same(),control_socket_present_after_stop=Path(member['socket']).exists(),
    new_connections='Frozen r119 client uses its already-documented ordinary direct SSH behavior for the absent socket',
    native_client_sha256=sha(Path(d['native_client_bin'])/'ssh'),source_sha256=sha(Path(__file__)),
    controller_source_or_config_changed=False,teacher_or_verifier_signals=0,master_killed=False,model_calls=0,
    underlying_tcp_network_root_cause='Not established; high retransmissions and shared-stream congestion observed, fresh same-host authenticated transfer accepted')
with (R/'checks/native-ssh-listener-retirement-r153.json').open('x') as stream:json.dump(value,stream,indent=2)
print(json.dumps(dict(retired_listener_slot=6,master_alive=value['master_same_pid_still_alive'],socket_present=value['control_socket_present_after_stop'],independent_transfer=transfer,teacher_or_verifier_signals=0)))
