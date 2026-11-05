"""Read-only Docker/SSH timing and pipe ownership; no Task or model execution."""
import datetime
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

R=Path('/home/chenkeyi/.local/share/harbor-rsi/qwen35-new-cf500-tmax500-20261029')
S=R/'checks/native-ssh-measurement-r117'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()


def profile(kind):
    root=S/kind;root.mkdir();path=root/'ssh'
    if kind=='auto':
        source=(R/'client-bin-v2/ssh').read_text().replace("'-o','ControlPersist=600'","'-o','ControlPersist=8'")
        old="'-o','ControlPath=/home/chenkeyi/.ssh/cftmx17-r6b-%C-'+str(int.from_bytes(hashlib.blake2b(str(os.getppid()).encode(),digest_size=2).digest(),'big')%16),"
        if old not in source:raise ValueError('Existing native SSH source changed')
        source=source.replace(old,"'-o','ControlPath="+str(S/'auto-socket')+"',")
    else:
        source=(R/'client-bin-preflight-r108/ssh').read_text()
        source=source.replace("'-o','ControlPath=none'","'-o','ControlPath="+str(S/'preseed-socket')+"'")
    path.write_text(source);path.chmod(0o700);return root


def probe(kind,d):
    env=dict(os.environ);env['PATH']=str(S/kind)+':'+str(R/'client-bin-v2')+':'+env['PATH']
    started=time.monotonic();process=subprocess.Popen(['docker','--host',d['environment']['kwargs']['endpoint'],'info','--format','{{.ID}}'],env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    stderr_pipe=os.readlink('/proc/self/fd/'+str(process.stderr.fileno()))
    while process.poll() is None and time.monotonic()-started<20:time.sleep(.05)
    exited=time.monotonic();owners=[]
    for p in Path('/proc').iterdir():
        if not p.name.isdigit():continue
        try:
            command=(p/'cmdline').read_bytes()
            if str(S).encode() not in command:continue
            for fd in (p/'fd').iterdir():
                try:link=os.readlink(fd)
                except OSError:continue
                if link==stderr_pipe:owners.append(dict(pid=int(p.name),fd=fd.name))
        except (OSError,ProcessLookupError):continue
    try:
        stdout,stderr=process.communicate(timeout=15);timeout=False
    except subprocess.TimeoutExpired:
        # Only this read-only Docker-info client is stopped; no Task process,
        # shared SSH master, model or verifier is signalled.
        if process.poll() is None:process.kill();process.wait()
        stdout=b'';stderr=b'';timeout=True
        process.stdout.close();process.stderr.close()
    return dict(profile=kind,docker_client_exit_seconds=exited-started,total_pipe_completion_seconds=time.monotonic()-started,
        returncode=process.returncode,engine_id=stdout.decode().strip(),stderr=stderr.decode()[-1000:],
        stderr_pipe=stderr_pipe,post_client_exit_pipe_owners=owners,pipe_completion_timed_out=timeout)


def main():
    S.mkdir();d=json.loads((R/'configs/campaign-deployment17-r13.json').read_text())
    profile('auto');profile('preseed')
    auto=probe('auto',d)
    socket=S/'preseed-socket'
    command=[d['ssh'][0],'-M','-N','-f','-oControlMaster=yes','-oControlPersist=no','-oControlPath='+str(socket),*d['ssh'][1:],d['host']]
    with (S/'preseed-master.log').open('xb') as log:
        subprocess.run(command,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=log,check=True,timeout=30)
    check=subprocess.run([d['ssh'][0],'-S',str(socket),'-O','check',*d['ssh'][1:],d['host']],capture_output=True,text=True,check=True,timeout=15)
    first=probe('preseed',d);second=probe('preseed',d)
    value=dict(checked_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),auto=auto,preseed_first=first,preseed_repeated=second,
        preseed_master_check=check.stderr.strip(),test_socket=str(socket),
        all_successful_same_private_engine=all(x['returncode']==0 and x['engine_id']==d['runtime']['engine_id'] and not x['pipe_completion_timed_out'] for x in [auto,first,second]),
        task_containers_created=0,teacher_or_verifier_processes_signalled=0,model_calls=0,
        old_rsync_sha256=sha(R/'client-bin-v2/rsync'),source_sha256=sha(Path(__file__)))
    with (R/'checks/native-ssh-startup-measurement-r117.json').open('x') as f:json.dump(value,f,indent=2)
    print(json.dumps(value),flush=True)


if __name__=='__main__':main()
