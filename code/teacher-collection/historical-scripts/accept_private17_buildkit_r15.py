"""Accept native rootless BuildKit inside the existing private SSD Engine.

Uses a pinned public image, an isolated Docker client context and the existing
public-dependency proxy. No Task/model/verifier or old builder is changed.
"""
import datetime
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import time

R=Path('/home/chenkeyi/workspace/RSI/runtime-evidence/qwen35-new-cf500-tmax500-20261029')
S=Path('/ssd/chenkeyi/qwen35-new-cf500-tmax500-20261029')
B=S/'buildkit-private-engine17-r15'
ENGINE='59c8ba22-0aa4-4aed-bc43-4e1b5989fa22'
SOCKET=S/'engine17-r1/socket/docker.sock'
NAME='rsi-cftmax-buildkit-private17-r15'
CONTEXT='rsi-cftmax-private17-r15'
PINNED='moby/buildkit@sha256:ace6811c21334fa502644b9711e0ea48e8539c5c2a843c2325dfb7b987ab260b'
BRIDGE_PROXY='http://172.17.0.1:49179'
HOST_PROXY='http://127.0.0.1:7890'


def sha(path):
    with Path(path).open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()
def now():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def run(args,**kwargs):return subprocess.run(args,check=True,capture_output=True,text=True,**kwargs)
def freeze(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('x') as stream:json.dump(value,stream,indent=2)


def main():
    B.mkdir(mode=0o700,exist_ok=True)
    lock=(B/'bootstrap.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    acceptance=R/'checks/private17-buildkit-r15-acceptance.json'
    if acceptance.exists() or (B/'PLAN.json').exists():raise FileExistsError('Inspect the existing acceptance/checkpoint before resumption')
    docker=['docker','--host','unix://'+str(SOCKET)]
    actual=json.loads(run([*docker,'info','--format','{{json .}}']).stdout)
    if actual['ID']!=ENGINE:raise ValueError('Private SSD Engine identity changed')
    parent=json.loads(run(['docker','inspect','rsi-cftmax-ssd-engine17-r1']).stdout)[0]
    mounts={m['Destination']:m['Source'] for m in parent['Mounts']}
    if mounts.get('/var/lib/docker')!=str(S/'engine17-r1/docker') or mounts.get('/var/lib/containerd')!=str(S/'engine17-r1/containerd'):
        raise ValueError('Private Engine storage escaped SSD')
    if parent['NetworkSettings']['Networks']['bridge']['Gateway']!='172.17.0.1' or parent['NetworkSettings']['Networks']['bridge']['IPAddress']!='172.17.0.3':
        raise ValueError('Existing private-parent network changed; do not open a broader dependency proxy')
    if shutil.disk_usage(S).free<128*1024**3:raise RuntimeError('Campaign SSD headroom below128GiB')
    if subprocess.run([*docker,'inspect',NAME],capture_output=True).returncode==0:raise FileExistsError('Observe existing owned private builder')
    env=dict(os.environ)
    for key in ['DEEPSEEK_API_KEY','GH_TOKEN','OPENAI_API_KEY']:env.pop(key,None)
    for key in ['HTTP_PROXY','HTTPS_PROXY','http_proxy','https_proxy']:env[key]=HOST_PROXY
    client=R/'tools/buildkit-rootless-r2/buildctl'
    if sha(client)!='8e64362dceba989827b23af567915feda10426ebd40611772318662e33bf2bfd':raise ValueError('Accepted native BuildKit client changed')
    skopeo=R/'tools/skopeo/root/usr/bin/skopeo';policy=R/'tools/skopeo/root/etc/containers/policy.json'
    apt=run(['apt-cache','show','socat=1.7.4.1-3ubuntu4']).stdout
    expected=next(line.split(':',1)[1].strip() for line in apt.splitlines() if line.startswith('SHA256:'))
    package_name=Path(next(line.split(':',1)[1].strip() for line in apt.splitlines() if line.startswith('Filename:'))).name
    plan=dict(created_at=now(),source_sha256=sha(Path(__file__)),engine_id=ENGINE,socket=str(SOCKET),node='17',
        image=PINNED,bootstrap_archive=str(B/'bootstrap.oci.tar'),rootless_state=str(B/'state'),
        logs_root=str(B/'logs'),docker_client_config=str(B/'docker-client'),docker_context=CONTEXT,
        native_buildctl=str(client),native_buildctl_sha256=sha(client),buildkit_container=NAME,
        public_dependency_proxy=dict(source=HOST_PROXY,bridge=BRIDGE_PROXY,allowed_peer='172.17.0.3/32',max_children=16,
            purpose='Public build dependencies only; no model transport or teacher environment is reconfigured'),
        socat_package=dict(version='1.7.4.1-3ubuntu4',filename=package_name,sha256=expected),
        resources=dict(cpus=4,memory_bytes=16*1024**3,gpu_devices=0,privileged=False),
        model_calls=0,benchmark_tasks_claimed_ready=0,old_builder_or_teacher_changes=0,
        upstream='https://github.com/moby/buildkit/blob/f5b59a1f2fb25a0cb7072c398cab9aed7835da4e/docs/rootless.md')
    freeze(B/'PLAN.json',plan);(B/'logs').mkdir()
    state_file=R/'checks/private17-buildkit-r15-state.json'
    def state(stage):
        value=dict(pid=os.getpid(),checked_at=now(),stage=stage,engine_id=ENGINE,model_calls=0,source_sha256=plan['source_sha256'])
        temporary=state_file.with_suffix('.tmp');temporary.write_text(json.dumps(value,indent=2));temporary.replace(state_file)
    state('COPY_PINNED_PUBLIC_BOOTSTRAP_DIRECTLY_TO17_SSD')
    archive=B/'bootstrap.oci.tar'
    with (B/'logs/bootstrap-copy.log').open('x') as log:
        subprocess.run([str(skopeo),'--policy',str(policy),'copy','--preserve-digests','docker://'+PINNED,
            'oci-archive:'+str(archive)+':rsi-cftmax-buildkit-private17-r15'],env=env,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=1800)
    from inspect_cold_oci_r1 import inspect_archive
    bootstrap=inspect_archive(str(archive),PINNED.split('@')[1],sha(archive));freeze(B/'bootstrap-content-proof.json',bootstrap)
    state('LOAD_PUBLIC_BOOTSTRAP_IN_PRIVATE_ENGINE')
    with (B/'logs/bootstrap-load.log').open('x') as log:
        subprocess.run([*docker,'image','load','--input',str(archive)],stdout=log,stderr=subprocess.STDOUT,check=True,timeout=300)
    image=json.loads(run([*docker,'image','inspect',PINNED.split('@')[1]]).stdout)[0]
    if image['Id']!=PINNED.split('@')[1]:raise ValueError('Bootstrap identity changed on load')
    state('EXTRACT_PINNED_USER_LOCAL_PROXY_TOOL')
    tool=B/'socat';tool.mkdir()
    with (B/'logs/socat-download.log').open('x') as log:
        subprocess.run(['apt-get','download','socat=1.7.4.1-3ubuntu4'],cwd=tool,env=env,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=180)
    deb=tool/package_name
    if sha(deb)!=expected:raise ValueError('socat differs from the native signed apt index')
    run(['dpkg-deb','-x',str(deb),str(tool/'root')],timeout=30)
    socat=tool/'root/usr/bin/socat';run([str(socat),'-V'],timeout=10)
    proxy_args=[str(socat),'TCP4-LISTEN:49179,bind=172.17.0.1,reuseaddr,fork,max-children=16,range=172.17.0.3/32','TCP4:127.0.0.1:7890']
    proxy_log=(B/'logs/public-dependency-bridge.log').open('ab')
    proxy=subprocess.Popen(proxy_args,stdout=proxy_log,stderr=proxy_log,start_new_session=True)
    time.sleep(.2)
    if proxy.poll() is not None:raise RuntimeError('Owned dependency bridge failed; do not change shared proxy configuration')
    freeze(B/'public-dependency-bridge.json',dict(pid=proxy.pid,started_at=now(),argv=proxy_args,binary_sha256=sha(socat),purpose=plan['public_dependency_proxy']))
    state('CREATE_PRIVATE_NATIVE_ROOTLESS_BUILDER')
    build_state=B/'state';build_state.mkdir()
    run([*docker,'run','--rm','--runtime','runc','--cpus','1','--memory','256m','--user','0:0','--entrypoint','/bin/sh',
        '--mount','type=bind,src='+str(build_state)+',dst=/owned-state',image['Id'],'-c','chown 1000:1000 /owned-state'],timeout=60)
    container=run([*docker,'create','--name',NAME,'--label','rsi.campaign='+R.name,'--runtime','runc','--init','--restart','unless-stopped',
        '--cpus','4','--memory','16g','--network','host','--security-opt','seccomp=unconfined','--security-opt','apparmor=unconfined',
        '--security-opt','systempaths=unconfined','--device','/dev/fuse','--mount','type=bind,src='+str(build_state)+',dst=/home/user/.local/share/buildkit',
        '--env','HTTP_PROXY='+BRIDGE_PROXY,'--env','HTTPS_PROXY='+BRIDGE_PROXY,'--env','NO_PROXY=localhost,127.0.0.1',
        image['Id'],'--oci-worker-snapshotter=fuse-overlayfs'],timeout=60).stdout.strip()
    configured=json.loads(run([*docker,'inspect',container]).stdout)[0];host=configured['HostConfig']
    if host['Privileged'] or host.get('DeviceRequests') or host['Memory']!=16*1024**3 or host['NanoCpus']!=4*10**9:
        raise ValueError('Owned rootless service resource/device identity differs')
    run([*docker,'start',container],timeout=60)
    for _ in range(60):
        probe=subprocess.run([*docker,'exec',container,'buildctl','debug','workers'],capture_output=True,text=True,timeout=10)
        if probe.returncode==0:break
        configured=json.loads(run([*docker,'inspect',container]).stdout)[0]
        if not configured['State']['Running']:raise RuntimeError('Private rootless service exited; original logs retained')
        time.sleep(1)
    else:raise TimeoutError('Private rootless worker not ready')
    client_config=B/'docker-client';client_config.mkdir()
    run(['docker','--config',str(client_config),'context','create',CONTEXT,'--docker','host=unix://'+str(SOCKET)],timeout=30)
    build_env=dict(env);build_env['DOCKER_CONFIG']=str(client_config);build_env.pop('DOCKER_HOST',None)
    address='docker-container://'+NAME+'?context='+CONTEXT
    run([str(client),'--addr',address,'debug','workers'],env=build_env,timeout=30)
    state('NATIVE_RUN_EXPORT_LOAD_AND_RUN_DIAGNOSTIC_ON_PRIVATE_ENGINE')
    context=B/'diagnostic-context';context.mkdir()
    (context/'Dockerfile').write_text('FROM '+PINNED+'\nUSER 0:0\nRUN printf "%s\\n" "private17-buildkit-r15" > /private-marker && test ! -e /dev/nvidia0\n')
    output=B/'diagnostic-run.oci.tar';metadata=B/'diagnostic-build-metadata.json'
    with (B/'logs/diagnostic-build.log').open('x') as log:
        subprocess.run([str(client),'--addr',address,'build','--frontend','dockerfile.v0','--local','context='+str(context),'--local','dockerfile='+str(context),
            '--output','type=oci,name=rsi-cftmax-private-builder-r15:diagnostic,dest='+str(output),'--metadata-file',str(metadata)],
            env=build_env,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=600)
    digest=json.loads(metadata.read_text())['containerimage.digest']
    diagnostic=inspect_archive(str(output),digest,sha(output));freeze(B/'diagnostic-content-proof.json',diagnostic)
    with (B/'logs/diagnostic-load.log').open('x') as log:
        subprocess.run([*docker,'image','load','--input',str(output)],stdout=log,stderr=subprocess.STDOUT,check=True,timeout=300)
    run([*docker,'run','--rm','--runtime','runc','--cpus','1','--memory','256m','--network','none','--entrypoint','/bin/sh',digest,
        '-c','set -eu; test "$(cat /private-marker)" = private17-buildkit-r15; test ! -e /dev/nvidia0'],timeout=30)
    space=run([*docker,'exec',container,'df','-B1','/home/user/.local/share/buildkit'],timeout=30).stdout
    if '/dev/nvme' not in space:raise ValueError('Actual rootless builder state is not on the accepted SSD')
    devices=run([*docker,'exec',container,'sh','-c','set -eu; test ! -e /dev/nvidia0; test ! -e /dev/nvidiactl; id'],timeout=30).stdout
    freeze(acceptance,dict(passed=True,checked_at=now(),source_sha256=plan['source_sha256'],deployment=plan,bootstrap_content=bootstrap,
        builder_container_id=container,builder_engine_id=ENGINE,private_docker_root_physical=str(S/'engine17-r1/docker'),
        buildctl_address=address,buildctl_environment=dict(DOCKER_CONFIG=str(client_config)),native_workers=probe.stdout,
        ssd_space_observed=space,cpu_only_check=devices,native_run_export_load_and_run_passed=True,
        diagnostic_content=diagnostic,public_dependency_bridge_pid=proxy.pid,shared_daemon_modified=False,
        old_builder_interrupted=False,teacher_or_verifier_signals=0,model_calls=0,benchmark_tasks_claimed_ready=0))
    state('PRIVATE_NATIVE_BUILD_SERVICE_ACCEPTED_NO_BENCHMARK_SWITCH_YET')
    print(json.dumps(dict(passed=True,acceptance=str(acceptance),engine_id=ENGINE,model_calls=0)),flush=True)


if __name__=='__main__':
    for name in ['DEEPSEEK_API_KEY','GH_TOKEN','OPENAI_API_KEY']:os.environ.pop(name,None)
    main()
