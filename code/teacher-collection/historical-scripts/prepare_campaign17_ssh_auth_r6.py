"""Campaign-only SSH agent for independent native Docker control connections.

The private key is deleted after loading into a dedicated149 ssh-agent. Only a
restricted, expiring public key is appended to this user's17 authorized_keys.
No shared sshd configuration or existing authentication entry is changed.
"""
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import uuid

R=Path('/home/chenkeyi/.local/share/harbor-rsi/qwen35-new-cf500-tmax500-20261029')
directory=R/'ssh/campaign17-agent-r6'
directory.mkdir(mode=0o700)
sock=directory/'agent.sock'
reply=subprocess.run(['ssh-agent','-a',str(sock),'-s','-t','604800'],check=True,capture_output=True,text=True)
pid=int(re.search(r'SSH_AGENT_PID=(\d+)',reply.stdout).group(1))
private=directory/('temporary-'+uuid.uuid4().hex)
env=dict(os.environ,SSH_AUTH_SOCK=str(sock))
try:
 subprocess.run(['ssh-keygen','-q','-t','ed25519','-N','','-C','RSI-CF500-TMax500-native17-r6','-f',str(private)],check=True)
 subprocess.run(['ssh-add','-t','604800',str(private)],env=env,check=True,capture_output=True)
 public=private.with_suffix('.pub').read_text().strip()
 (directory/'identity.pub').write_text(public+'\n')
finally:
 private.unlink(missing_ok=True)
 private.with_suffix('.pub').unlink(missing_ok=True)
expires=(datetime.datetime.now(datetime.timezone.utc)+datetime.timedelta(days=7)).strftime('%Y%m%d%H%M%SZ')
entry='restrict,expiry-time="'+expires+'" '+public
remote="""import hashlib,json,os,sys
from pathlib import Path
entry=json.load(sys.stdin)['entry'];p=Path.home()/'.ssh/authorized_keys'
old=p.read_bytes() if p.exists() else b''
if entry.encode() in old.splitlines():raise ValueError('Campaign authorization already exists; no duplicate')
with p.open('ab') as f:
 if old and not old.endswith(b'\\n'):f.write(b'\\n')
 f.write(entry.encode()+b'\\n');f.flush();os.fsync(f.fileno())
new=p.read_bytes()
print(json.dumps(dict(user=os.getuid(),old_sha256=hashlib.sha256(old).hexdigest(),new_sha256=hashlib.sha256(new).hexdigest(),public_entry_sha256=hashlib.sha256(entry.encode()).hexdigest(),existing_bytes_preserved=new.startswith(old),shared_sshd_changes=0)))
"""
ssh=['/usr/bin/ssh','-S','/home/chenkeyi/.ssh/cf17-20261028.sock','-oBatchMode=yes','-oProxyCommand=false','chenkeyi@180.163.192.17']
registered=subprocess.run([*ssh,shlex.join(['python3','-c',remote])],input=json.dumps(dict(entry=entry)),capture_output=True,text=True,check=True,timeout=30)
probe=['/usr/bin/ssh','-F',str(R/'ssh/client-v2.conf'),'-oControlMaster=no','-oControlPath=none','-oBatchMode=yes','-oProxyCommand=none','-oProxyJump=none','-oIdentitiesOnly=yes','-i',str(directory/'identity.pub'),'-oIdentityAgent='+str(sock),'chenkeyi@180.163.192.17']
checked=subprocess.run([*probe,'docker --host unix:///ssd/chenkeyi/qwen35-new-cf500-tmax500-20261029/engine17-r1/socket/docker.sock info --format "{{.ID}}"'],capture_output=True,text=True,check=True,timeout=30)
if checked.stdout.strip()!='59c8ba22-0aa4-4aed-bc43-4e1b5989fa22':raise ValueError('Independent native SSH reached the wrong Engine')
fingerprint=subprocess.run(['ssh-keygen','-lf',str(directory/'identity.pub')],check=True,capture_output=True,text=True).stdout.split()[1]
out=dict(status='CAMPAIGN_ONLY_EXPIRING_SSH_AGENT_AND_INDEPENDENT17_CONNECTION_ACCEPTED',checked_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
 agent_pid=pid,agent_socket=str(sock),public_identity_file=str(directory/'identity.pub'),public_key_fingerprint=fingerprint,expires_utc=expires,
 private_key_files_retained=0,registration=json.loads(registered.stdout),actual_private_engine_id=checked.stdout.strip(),model_calls=0,
 shared_sshd_configuration_changes=0,shared_docker_configuration_changes=0,existing_control_master_retired=False)
with (R/'checks/campaign17-independent-ssh-auth-r6.json').open('x') as f:json.dump(out,f,indent=2)
print(json.dumps({k:out[k] for k in ['status','agent_pid','actual_private_engine_id','private_key_files_retained']}))
