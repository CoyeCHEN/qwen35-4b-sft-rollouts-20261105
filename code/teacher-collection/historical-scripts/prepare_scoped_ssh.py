"""Prove standard OpenSSH multiplexing without changing shared SSH settings.

Only future controller processes that explicitly opt into this PATH use the
client config. Existing trials, system sshd, user config and daemon stay intact.
"""
from concurrent.futures import ThreadPoolExecutor
import datetime
import hashlib
import json
import os
from pathlib import Path
import shlex
import subprocess
import time

ROOT=Path('/home/chenkeyi/.local/share/harbor-rsi/qwen35-new-cf500-tmax500-20261029')
DAEMON='c6e16cdf-e878-4cc5-84c8-78a56c54b5c5'


def main():
    directory=ROOT/'ssh';directory.mkdir(exist_ok=True,mode=0o700)
    clients=ROOT/'client-bin';clients.mkdir(exist_ok=True,mode=0o700)
    config=directory/'client.conf'
    content='Host 127.0.0.1\n    ControlMaster auto\n    ControlPersist 600\n    ControlPath /home/chenkeyi/.ssh/cftmx-20261029-%C\n    BatchMode yes\n'
    if config.exists():
        if config.read_text()!=content:raise ValueError('Reviewed scoped SSH config differs')
    else:
        with config.open('x') as stream:stream.write(content)
    config.chmod(0o600)
    wrapper=clients/'ssh'
    wrapper_content='#!/bin/sh\nexec /usr/bin/ssh -F '+shlex.quote(str(config))+' "$@"\n'
    if wrapper.exists():
        if wrapper.read_text()!=wrapper_content:raise ValueError('Scoped SSH executable differs')
    else:
        with wrapper.open('x') as stream:stream.write(wrapper_content)
    wrapper.chmod(0o700)
    environment=os.environ.copy();environment['SSH_AUTH_SOCK']='/home/chenkeyi/.local/share/harbor-rsi/near-r3-20261015/auth.sock'
    environment['PATH']=str(clients)+':'+environment['PATH']
    subprocess.run(['/usr/bin/ssh','-F',str(config),'-MNf','-p','5102','chenkeyi@127.0.0.1'],
        env=environment,check=True,capture_output=True,text=True,timeout=30)
    def probe(index):
        start=time.monotonic()
        result=subprocess.run(['docker','--host','ssh://chenkeyi@127.0.0.1:5102','info','--format','{{.ID}}'],
            env=environment,capture_output=True,text=True,timeout=45)
        return dict(index=index,returncode=result.returncode,daemon_id=result.stdout.strip(),
            stderr=result.stderr[-2000:],seconds=time.monotonic()-start)
    with ThreadPoolExecutor(max_workers=8) as pool:results=list(pool.map(probe,range(24)))
    passed=all(x['returncode']==0 and x['daemon_id']==DAEMON for x in results)
    report=dict(passed=passed,checked_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        native_docker_cli_probes=24,concurrent_probes=8,results=results,model_calls=0,
        future_process_path_prefix=str(clients),client_config=str(config),
        client_config_sha256=hashlib.sha256(config.read_bytes()).hexdigest(),
        ssh_executable_sha256=hashlib.sha256(wrapper.read_bytes()).hexdigest(),
        ssh_auth_socket_reference_only=True,shared_sshd_or_user_config_changed=False,
        active_trial_configuration_changed=False,backend_endpoint_changed=False,daemon_id=DAEMON,
        native_harbor_lifecycle_concurrency_acceptance='Pending separate model-free native check after current canary ends')
    (ROOT/'checks/scoped-ssh-multiplexing.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))
    if not passed:raise RuntimeError('Scoped native SSH concurrency probe failed')


if __name__=='__main__':main()
