"""Supply public fonts, then execute the exact original input-image initializer.

Use the already accepted native BuildKit service and exact original OCI base.
No Goal implementation, official tests or Task resources are modified.
"""
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile

from inspect_cold_oci_r1 import inspect_archive, publish

S=Path('/ssd/chenkeyi/qwen35-new-cf500-tmax500-20261029')
R=Path('/home/chenkeyi/workspace/RSI/runtime-evidence/qwen35-new-cf500-tmax500-20261029')
D=S/'original-public-image-font-r72b'


def sha(p):
    with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()


def main():
    lock=(D/'worker.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    if (D/'PLAN.json').exists():raise FileExistsError('Inspect preserved native build; no replay')
    scope=json.loads((D/'SOURCE_SCOPE.json').read_text())
    source=S/'buildkit-rootless-r2/contexts/task_001742_6788502c/post_install.sh'
    command=scope['original_input_initializer']
    if sha(source)!=scope['original_post_install_sha256'] or command not in [x.strip() for x in source.read_text().splitlines()]:
        raise ValueError('Original public input-image generation command changed')
    if 'chmod -R 777 /app' not in [x.strip() for x in source.read_text().splitlines()]:raise ValueError('Original input permission initializer changed')
    campaign=R/'configs/campaign-build17-r17.json';cfg=json.loads(campaign.read_text())
    acceptance_path=Path(cfg['native_build_service_acceptance']);a=json.loads(acceptance_path.read_text())
    if sha(acceptance_path)!=cfg['native_build_service_acceptance_sha256'] or not a['passed'] or a['builder_engine_id']!=scope['engine_id']:
        raise ValueError('Accepted native private builder changed')
    if sha(a['deployment']['native_buildctl'])!=a['deployment']['native_buildctl_sha256']:
        raise ValueError('Native buildctl identity changed')
    os.environ['DOCKER_CONFIG']=a['deployment']['docker_client_config'];os.environ.pop('DOCKER_HOST',None)
    if shutil.disk_usage(S).free<128*1024**3:raise RuntimeError('Insufficient bounded SSD headroom')
    archive=Path(scope['original_archive'])
    original=inspect_archive(str(archive),scope['original_image_id'],scope['original_archive_sha256'])
    publish(D/'original-image-audit.json',original)
    # Extract only the validated OCI transport layout, never the rootfs.
    layout=D/'original-oci-layout';layout.mkdir(exist_ok=False)
    with tarfile.open(archive) as tar:
        for member in tar:
            name=member.name.removeprefix('./')
            if name not in ['index.json','oci-layout'] and not name.startswith('blobs/sha256/'):continue
            if member.isdir():continue
            if not member.isfile() or '..' in Path(name).parts:raise ValueError('Unexpected OCI transport member')
            target=layout/name;target.parent.mkdir(parents=True,exist_ok=True)
            with tar.extractfile(member) as src,target.open('xb') as dst:shutil.copyfileobj(src,dst)
            if name.startswith('blobs/sha256/') and sha(target)!=Path(name).name:raise ValueError('OCI blob identity differs')
    context=D/'context';context.mkdir(exist_ok=False)
    dockerfile='FROM original_base\nARG HTTP_PROXY\nARG HTTPS_PROXY\n'
    dockerfile+='RUN http_proxy="$HTTP_PROXY" https_proxy="$HTTPS_PROXY" apt-get update && http_proxy="$HTTP_PROXY" https_proxy="$HTTPS_PROXY" apt-get install -y --no-install-recommends gsfonts fonts-urw-base35 && '+command+' && chmod -R 777 /app && test -s /app/audit_policy.png\n'
    (context/'Dockerfile').write_text(dockerfile)
    output=D/'image.oci.tar'
    cmd=[a['deployment']['native_buildctl'],'--addr',a['buildctl_address'],'build','--frontend','dockerfile.v0',
        '--local','context='+str(context),'--local','dockerfile='+str(context),
        '--oci-layout','original_image='+str(layout),'--opt','context:original_base=oci-layout://original_image@'+scope['original_image_id'],
        '--opt','platform=linux/amd64','--opt','build-arg:HTTP_PROXY='+a['deployment']['public_dependency_proxy']['bridge'],
        '--opt','build-arg:HTTPS_PROXY='+a['deployment']['public_dependency_proxy']['bridge'],
        '--output','type=oci,name=rsi-cftmax-public-font-r72b:task1742,dest='+str(output),
        '--metadata-file',str(D/'buildctl-metadata.json')]
    publish(D/'PLAN.json',dict(source_scope_sha256=sha(D/'SOURCE_SCOPE.json'),source_sha256=sha(__file__),
        dockerfile_sha256=sha(context/'Dockerfile'),command=cmd,engine_id=scope['engine_id'],
        official_original_initializer_reused=True,provided_input_generated_from_original_definition=True,
        assigned_goal_repairs=0,model_calls=0,teacher_dispatches=0,native_build_concurrency=1,
        official_task_or_test_modifications=0,native_buildkit_reference='https://github.com/moby/buildkit/blob/master/docs/reference/buildctl.md'))
    with (D/'build.log').open('x') as log:
        subprocess.run(cmd,check=True,stdout=log,stderr=subprocess.STDOUT,timeout=scope['original_build_timeout_sec'])
    with tarfile.open(output) as tar:
        index=json.loads(tar.extractfile('index.json').read());image=index['manifests'][0]['digest']
    proof=inspect_archive(str(output),image,sha(output));publish(D/'image-audit.json',proof)
    if [x['diff_id'] for x in proof['layers'][:len(original['layers'])]]!=[x['diff_id'] for x in original['layers']]:
        raise ValueError('Exact original image layer prefix was not preserved')
    publish(D/'build.json',dict(status='PUBLIC_FONT_ORIGINAL_INPUT_IMAGE_CANDIDATE_NATIVE_ACCEPTANCE_PENDING',
        task_id='task_001742_6788502c',original_image_id=scope['original_image_id'],image_id=image,
        archive=str(output),archive_sha256=proof['archive_sha256'],image_audit_sha256=sha(D/'image-audit.json'),
        original_rootfs_diffid_prefix_preserved=True,original_input_initializer_sha256=hashlib.sha256(command.encode()).hexdigest(),
        added_public_packages=['gsfonts','fonts-urw-base35'],original_input_image_path='/app/audit_policy.png',original_input_permission_initialization='chmod -R 777 /app',
        task_goal_repairs=0,model_calls=0,teacher_dispatches=0,accepted_by_controller=False,source_sha256=sha(__file__)))
    print(json.dumps(dict(image_id=image,status='PUBLIC_DEPENDENCY_CANDIDATE_ONLY')))


if __name__=='__main__':main()
