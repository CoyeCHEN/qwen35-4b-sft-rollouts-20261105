"""Add hash-locked public libraries to one exact original image on private17.

No original container is started. Preserve the original rootfs layer prefix and
runtime configuration. The result is only a candidate until native acceptance.
"""
import datetime
import fcntl
import hashlib
import io
import json
from pathlib import Path
import subprocess
import tarfile

from inspect_cold_oci_r1 import inspect_archive, publish

S=Path('/ssd/chenkeyi/qwen35-new-cf500-tmax500-20261029')
D=S/'public-pytest-image-r68'
IMAGE='sha256:80ad1b1f9a0a02cb3771d15903b831f6a527eba1a62fa5e72a7742f3fad0ce7f'
NAME='cftmax-public-pytest-image-r68'
TARGET='/usr/local/lib/python3.10/dist-packages'


def sha(path):
    with Path(path).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()


def main():
    D.mkdir(parents=True,exist_ok=True)
    lock=(D/'worker.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    if (D/'PLAN.json').exists():raise FileExistsError('Inspect existing candidate; do not replay')
    cli=['docker','--host','unix://'+str(S/'engine17-r1/socket/docker.sock')]
    def run(*args,timeout=180, binary=False):
        return subprocess.run([*cli,*args],check=True,capture_output=True,text=not binary,timeout=timeout)
    engine=run('info','--format','{{.ID}}').stdout.strip()
    if engine!='59c8ba22-0aa4-4aed-bc43-4e1b5989fa22':raise ValueError('Private Engine changed')
    parent=json.loads(subprocess.run(['docker','inspect','rsi-cftmax-ssd-engine17-r1'],check=True,capture_output=True,text=True).stdout)[0]
    if {x['Destination']:x['Source'] for x in parent['Mounts']}.get('/var/lib/docker')!=str(S/'engine17-r1/docker'):
        raise ValueError('Image writable layer is outside SSD')
    manifest=S/'verifier-public-python-r59/PUBLIC_PYTEST_CACHE.json';cache=json.loads(manifest.read_text())
    if sha(manifest)!='bfddae201d7d38d1da30fa9216965719eaea08a969a5935033391a14e40fd4a1':raise ValueError('Public package cache changed')
    root=Path(cache['target']);expected={x['path']:x['sha256'] for x in cache['files']}
    if len(expected)!=540 or any(sha(root/p)!=digest for p,digest in expected.items()):raise ValueError('Public package file hashes differ')
    original=json.loads(run('image','inspect',IMAGE).stdout)[0]
    if original['Id']!=IMAGE or original['Config'].get('Volumes'):raise ValueError('Unexpected original image identity/volumes')
    publish(D/'PLAN.json',dict(task_id='task_007141_26892089',original_image_id=IMAGE,engine_id=engine,
        public_cache_manifest=str(manifest),public_cache_manifest_sha256=sha(manifest),source_sha256=sha(__file__),
        target=TARGET,model_calls=0,teacher_dispatches=0,original_container_started=False,
        original_task_test_resource_deadline_changes=0,accepted_by_controller=False))
    run('create','--name',NAME,'--label','rsi.campaign='+S.name,IMAGE)
    try:
        def files():
            content=run('cp',NAME+':'+TARGET+'/.','-',binary=True).stdout
            result={}
            with tarfile.open(fileobj=io.BytesIO(content)) as archive:
                for m in archive:
                    if not m.isfile():continue
                    p=m.name.removeprefix('./').removeprefix('dist-packages/')
                    if p in expected:result[p]=hashlib.sha256(archive.extractfile(m).read()).hexdigest()
            return result
        before=files()
        if any(expected[p]!=digest for p,digest in before.items()):raise ValueError('Public cache would overwrite a different original library')
        run('cp',str(root)+'/.',NAME+':'+TARGET+'/')
        if files()!=expected:raise ValueError('Public library round-trip differs')
        changes=run('diff',NAME).stdout.splitlines()
        parents={str(p) for p in Path(TARGET).parents}
        if any(line[2:] not in parents|{TARGET} and not line[2:].startswith(TARGET+'/') for line in changes):
            raise ValueError('A non-public-library path changed')
        publish(D/'container-changes.json',dict(changes=changes,public_files_verified=540,original_library_conflicts=0))
        image=run('commit',NAME).stdout.strip()
        candidate=json.loads(run('image','inspect',image).stdout)[0]
        a=dict(original['Config']);b=dict(candidate['Config'])
        # The ownership label on the temporary container is metadata only.
        a.pop('Labels',None);b.pop('Labels',None)
        if a!=b:raise ValueError('Commit changed runtime configuration keys: '+','.join(k for k in a.keys()|b.keys() if a.get(k)!=b.get(k)))
        old_layers=original['RootFS']['Layers'];layers=candidate['RootFS']['Layers']
        if layers[:len(old_layers)]!=old_layers or len(layers)!=len(old_layers)+1:raise ValueError('Original rootfs layer prefix not preserved')
        archive=D/'image.tar';run('image','save','--output',str(archive),image,timeout=1800)
        proof=inspect_archive(str(archive),image,sha(archive));publish(D/'image-audit.json',proof)
        publish(D/'build.json',dict(status='PUBLIC_DEPENDENCY_IMAGE_CANDIDATE_NATIVE_ACCEPTANCE_PENDING',
            task_id='task_007141_26892089',original_image_id=IMAGE,image_id=image,archive=str(archive),
            archive_sha256=proof['archive_sha256'],image_audit_sha256=sha(D/'image-audit.json'),
            original_rootfs_diffid_prefix_preserved=True,runtime_environment_config_unchanged=True,
            original_public_goal_files_unchanged=True,added_public_files=540,public_cache_manifest_sha256=sha(manifest),
            engine_id=engine,model_calls=0,teacher_dispatches=0,source_sha256=sha(__file__),accepted_by_controller=False))
        print((D/'build.json').read_text())
    finally:
        run('rm',NAME)


if __name__=='__main__':main()
