"""Pre-open a fixed native OpenSSH pool; never manage Task/model processes."""
from concurrent.futures import ThreadPoolExecutor
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import time

R=Path('/home/chenkeyi/.local/share/harbor-rsi/qwen35-new-cf500-tmax500-20261029')
S=R/'checks/native-ssh-pool-r119'
SOCKET_PREFIX='/home/chenkeyi/.ssh/cftmx17-r119-'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    S.mkdir();d=json.loads((R/'configs/campaign-deployment17-r13.json').read_text())
    measurement=R/'checks/native-ssh-startup-measurement-r118.json'
    observed=json.loads(measurement.read_text())
    if not observed['all_successful_same_private_engine']:raise ValueError('Native timing measurement was not accepted')
    test=Path(observed['test_socket'])
    if test.exists():
        # This exact socket has served only the zero-Task read-only measurement.
        reply=subprocess.run([d['ssh'][0],'-S',str(test),'-O','check',*d['ssh'][1:],d['host']],capture_output=True,text=True,check=True,timeout=15)
        if reply.stderr.strip()!=observed['preseed_master_check']:raise ValueError('Measurement-only SSH master identity changed')
        subprocess.run([d['ssh'][0],'-S',str(test),'-O','exit',*d['ssh'][1:],d['host']],capture_output=True,text=True,check=True,timeout=15)
    source=(R/'client-bin-preflight-r108/ssh').read_text()
    old="'-o','ControlPath=none'"
    new="'-o','ControlPath="+SOCKET_PREFIX+"'+str(int.from_bytes(hashlib.blake2b(str(os.getppid()).encode(),digest_size=2).digest(),'big')%16)"
    if old not in source:raise ValueError('Accepted independent-SSH source changed')
    source=source.replace(old,new)
    root=R/'client-bin-native-r119';root.mkdir();client=root/'ssh';client.write_text(source);client.chmod(0o700)
    masters=[]
    for slot in range(16):
        socket=SOCKET_PREFIX+str(slot)
        if Path(socket).exists():raise ValueError('Do not replace an existing SSH control socket')
        log=S/('master-'+str(slot)+'.log')
        command=[d['ssh'][0],'-M','-N','-f','-oControlMaster=yes','-oControlPersist=no','-oControlPath='+socket,*d['ssh'][1:],d['host']]
        with log.open('xb') as stream:
            subprocess.run(command,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=stream,check=True,timeout=30)
        check=subprocess.run([d['ssh'][0],'-S',socket,'-O','check',*d['ssh'][1:],d['host']],capture_output=True,text=True,check=True,timeout=15)
        match=re.fullmatch(r'Master running \(pid=(\d+)\)',check.stderr.strip())
        if not match:raise ValueError('Unrecognized native SSH master identity')
        pid=int(match.group(1));proc=Path('/proc')/str(pid)
        masters.append(dict(slot=slot,socket=socket,pid=pid,start_ticks=(proc/'stat').read_text().rsplit(')',1)[1].split()[19],
            stdout=os.readlink(proc/'fd/1'),stderr=os.readlink(proc/'fd/2'),log=str(log)))
        (S/'masters-progress.json').write_text(json.dumps(masters,indent=2))
    env=dict(os.environ);env['PATH']=str(root)+':'+str(R/'client-bin-v2')+':'+env['PATH']
    def probe(slot):
        begin=time.monotonic();reply=subprocess.run(['docker','--host',d['environment']['kwargs']['endpoint'],'info','--format','{{.ID}}'],env=env,capture_output=True,text=True,timeout=30)
        return dict(probe=slot,seconds=time.monotonic()-begin,exit_code=reply.returncode,engine_id=reply.stdout.strip(),stderr=reply.stderr[-300:])
    with ThreadPoolExecutor(max_workers=8) as pool:rows=list(pool.map(probe,range(24)))
    if any(x['exit_code'] or x['engine_id']!=d['runtime']['engine_id'] for x in rows):raise ValueError('Native SSH pool changed Engine or failed a read-only probe')
    value=dict(checked_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),passed=True,
        native_client_bin=str(root),native_client_sha256=sha(client),masters=masters,maximum_open_native_ssh_masters=16,
        native_control_master='no automatic background-master creation; reuse only the explicit pre-opened sockets',
        disconnected_socket_behavior='Ordinary independent OpenSSH connection; no automatic background process or model/provider fallback',
        probes=rows,probe_concurrency=8,measurement=str(measurement),measurement_sha256=sha(measurement),
        original_30_second_timeout_root_cause='Not established; pipe retention was not reproduced by the read-only timing experiment',
        rsync_sha256=sha(R/'client-bin-v2/rsync'),task_containers_created=0,model_calls=0,
        existing_controller_or_teacher_environment_changed=False,shared_sshd_or_docker_daemon_changes=0,
        source_sha256=sha(Path(__file__)))
    with (R/'checks/native-ssh-preseed-pool-r119.json').open('x') as f:json.dump(value,f,indent=2)
    print(json.dumps(dict(passed=True,masters=16,probes=len(rows),maximum_seconds=max(x['seconds'] for x in rows),native_client_sha256=value['native_client_sha256'])))


if __name__=='__main__':main()
