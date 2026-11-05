"""Prepare campaign-only loopback SSH, without changing any shared daemon."""
import datetime
import hashlib
import json
import os
from pathlib import Path
import subprocess

S=Path('/ssd/chenkeyi/qwen35-new-cf500-tmax500-20261029')
D=S/'controller17-r1/ssh';D.mkdir(parents=True,exist_ok=True);D.chmod(0o700)
sha=lambda path:hashlib.sha256(path.read_bytes()).hexdigest()
proof=D/'LOOPBACK_ACCEPTANCE_R154.json'
if proof.exists():raise FileExistsError('Observe existing accepted loopback identity')
private=D/'identity';public=D/'identity.pub'
if private.exists() or public.exists():raise FileExistsError('Inspect existing campaign key rather than overwriting')
subprocess.run(['ssh-keygen','-q','-t','ed25519','-N','','-C','cftmax-controller17-r1-loopback','-f',str(private)],check=True)
private.chmod(0o600)
ssh_home=Path.home()/'.ssh';ssh_home.mkdir(mode=0o700,exist_ok=True)
authorized=ssh_home/'authorized_keys'
if authorized.is_symlink() or (authorized.exists() and authorized.stat().st_uid!=os.getuid()):raise ValueError('Do not alter another owner or symlinked authorization file')
original=authorized.read_bytes() if authorized.exists() else b''
backup=D/'authorized_keys.before-r154'
with backup.open('xb') as stream:stream.write(original)
backup.chmod(0o600)
key=' '.join(public.read_text().strip().split()[:2])
entry='from="127.0.0.1",restrict '+key+' cftmax-controller17-r1-loopback\n'
with authorized.open('ab') as stream:
    if original and not original.endswith(b'\n'):stream.write(b'\n')
    stream.write(entry.encode())
authorized.chmod(0o600)
known=D/'known_hosts';hostkey=' '.join(Path('/etc/ssh/ssh_host_ed25519_key.pub').read_text().split()[:2])
expected='127.0.0.1 '+hostkey+'\n[127.0.0.1]:22 '+hostkey+'\n'
if known.exists() and known.read_text()!=expected:raise ValueError('Pinned host public identity changed')
known.write_text(expected);known.chmod(0o600)
client=['ssh','-F','/dev/null','-oBatchMode=yes','-oControlMaster=no','-oControlPath=none','-oIdentitiesOnly=yes',
    '-oStrictHostKeyChecking=yes','-oUserKnownHostsFile='+str(known),'-i',str(private),'chenkeyi@127.0.0.1']
socket=S/'engine17-r1/socket/docker.sock'
reply=subprocess.run([*client,'docker --host unix://'+str(socket)+" info --format '{{.ID}}'"],capture_output=True,text=True,check=True,timeout=15)
if reply.stdout.strip()!='59c8ba22-0aa4-4aed-bc43-4e1b5989fa22':raise ValueError('Loopback selected another Docker Engine')
value=dict(checked_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),passed=True,engine_id=reply.stdout.strip(),
    socket=str(socket),known_hosts_sha256=sha(known),public_key_sha256=sha(public),private_key_path=str(private),private_key_contents_recorded=False,
    authorization_scope='Only connections from127.0.0.1; restrict disables PTY/forwarding/user rc; previous authorized keys preserved byte-for-byte',
    authorized_keys_before_sha256=hashlib.sha256(original).hexdigest(),authorized_keys_after_sha256=sha(authorized),
    appended_line_sha256=hashlib.sha256(entry.encode()).hexdigest(),source_sha256=sha(Path(__file__)),
    shared_sshd_or_docker_daemon_changes=0,teacher_or_verifier_signals=0,model_calls=0)
with proof.open('x') as stream:json.dump(value,stream,indent=2)
print(json.dumps(value))
