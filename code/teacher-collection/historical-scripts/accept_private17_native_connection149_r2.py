"""Bind the campaign's existing SSH client to its accepted private17 daemon."""
import datetime,hashlib,json,os,subprocess
from pathlib import Path
R=Path('/home/chenkeyi/.local/share/harbor-rsi/qwen35-new-cf500-tmax500-20261029')
SOCKET='/ssd/chenkeyi/qwen35-new-cf500-tmax500-20261029/engine17-r1/socket/docker.sock'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def freeze(p,v):
 with p.open('x') as f:json.dump(v,f,indent=2)
def main():
 p=R/'client-bin-v2/ssh';before=p.read_bytes();rsync_sha=sha(R/'client-bin-v2/rsync')
 assert ('Reuse the existing authenticated17 master' in before.decode() or 'is17=' in before.decode())
 backup=R/'checks/ssh-client-v2-before-private-dial-r3.py'
 with backup.open('xb') as f:f.write(before)
 # The provider already records a separate remote_socket_path. Its Docker
 # SSH endpoint cannot contain a socket path. Route only Docker's exact
 # dial-stdio command, keeping native shell and149 transports unchanged.
 program='''#!/usr/bin/python3
import os,sys
args=sys.argv[1:]
is17=any(x in ('180.163.192.17','chenkeyi@180.163.192.17') for x in args)
if is17:
 if args[-3:]==['docker','system','dial-stdio']:
  args[-3:]=['docker','--host','unix://SOCKET','system','dial-stdio']
 elif args and args[-1]=='docker system dial-stdio':
  args[-1]='docker --host unix://SOCKET system dial-stdio'
 command=['/usr/bin/ssh','-S','/home/chenkeyi/.ssh/cf17-20261028.sock','-o','ProxyCommand=false','-F','ROOT/ssh/client-v2.conf',*args]
else:
 command=['/usr/bin/ssh','-o','ControlPath=/home/chenkeyi/.ssh/cftmx2-%C-'+str(os.getppid()),'-F','ROOT/ssh/client-v2.conf',*args]
os.execv(command[0],command)
'''.replace('SOCKET',SOCKET).replace('ROOT',str(R))
 temporary=p.with_suffix('.new');temporary.write_text(program);temporary.chmod(0o755);temporary.replace(p)
 env=dict(os.environ,PATH=str(R/'client-bin-v2')+':'+os.environ['PATH'],SSH_AUTH_SOCK='/home/chenkeyi/.local/share/harbor-rsi/near-r3-20261015/auth.sock')
 rows=[]
 for endpoint,expected in [('ssh://chenkeyi@180.163.192.17:22','59c8ba22-0aa4-4aed-bc43-4e1b5989fa22'),('ssh://chenkeyi@127.0.0.1:5102','c6e16cdf-e878-4cc5-84c8-78a56c54b5c5')]:
  q=subprocess.run(['docker','--host',endpoint,'info','--format','{{.ID}}'],capture_output=True,text=True,env=env,timeout=45)
  rows.append(dict(endpoint=endpoint,returncode=q.returncode,engine_id=q.stdout.strip(),expected_engine_id=expected))
  if q.returncode or q.stdout.strip()!=expected:raise RuntimeError('Native endpoint acceptance failed: '+json.dumps(rows[-1]))
 assert sha(R/'client-bin-v2/rsync')==rsync_sha
 freeze(R/'checks/private17-native-ssh-dial-r3.json',dict(checked_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),ssh_client_before_sha256=hashlib.sha256(before).hexdigest(),ssh_client_sha256=sha(p),
  exact_command_routed=['docker','system','dial-stdio'],private_socket=SOCKET,existing_authenticated_master_reused=True,rsync_sha256=rsync_sha,rsync_unchanged=True,model_calls=0,native_engine_acceptance=rows))
 print(json.dumps(rows),flush=True)
if __name__=='__main__':main()
