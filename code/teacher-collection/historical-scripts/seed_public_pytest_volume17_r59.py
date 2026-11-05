"""Populate one immutable public-library volume on the owned SSD Engine."""
import fcntl
import hashlib
import io
import json
from pathlib import Path
import subprocess
import tarfile

S = Path('/ssd/chenkeyi/qwen35-new-cf500-tmax500-20261029')
D = S / 'verifier-public-python-r59'
SOCKET = S / 'engine17-r1/socket/docker.sock'
ENGINE = '59c8ba22-0aa4-4aed-bc43-4e1b5989fa22'
IMAGE = 'sha256:80ad1b1f9a0a02cb3771d15903b831f6a527eba1a62fa5e72a7742f3fad0ce7f'
VOLUME = 'rsi-cftmax-public-pytest310-r59'
CONTAINER = 'cftmax-public-python-seed-r59'


def docker(*args, binary=False):
    return subprocess.run(['docker','--host','unix://' + str(SOCKET),*args],
        check=True, capture_output=True, text=not binary, timeout=120).stdout


def main():
    lock = (D / 'volume-seed.lock').open('a')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    receipt = D / 'PUBLIC_PYTEST_VOLUME.json'
    if receipt.exists():
        raise FileExistsError('Observe the existing immutable public volume')
    raw = (D / 'PUBLIC_PYTEST_CACHE.json').read_bytes()
    expected = json.loads(raw)
    digest = hashlib.sha256(raw).hexdigest()
    if docker('info','--format','{{.ID}}').strip() != ENGINE:
        raise ValueError('The selected Docker Engine is not the accepted private SSD Engine')
    existing = subprocess.run(['docker','--host','unix://' + str(SOCKET),'volume','inspect',VOLUME], capture_output=True)
    if existing.returncode == 0:
        raise FileExistsError('Inspect the prior public volume before any retry')
    docker('volume','create','--label','rsi.campaign=' + S.name,
        '--label','rsi.public-python-manifest-sha256=' + digest,VOLUME)
    created = False
    try:
        docker('create','--name',CONTAINER,'--label','rsi.campaign=' + S.name,
            '--mount','type=volume,src=' + VOLUME + ',dst=/public-python',
            '--entrypoint','/bin/true',IMAGE)
        created = True
        docker('cp',str(Path(expected['target'])) + '/.',CONTAINER + ':/public-python/')
        payload = docker('cp',CONTAINER + ':/public-python/.','-',binary=True)
        files = {}
        with tarfile.open(fileobj=io.BytesIO(payload)) as stream:
            for item in stream:
                if item.isfile():
                    path = str(Path(item.name).relative_to('public-python')) if item.name.startswith('public-python/') else item.name.removeprefix('./')
                    files[path] = hashlib.sha256(stream.extractfile(item).read()).hexdigest()
        wanted = {item['path']:item['sha256'] for item in expected['files']}
        if files != wanted:
            raise ValueError('Public volume content differs from the official wheel cache')
        volume = json.loads(docker('volume','inspect',VOLUME))[0]
        result = dict(status='PUBLIC_LIBRARY_VOLUME_SEEDED_NATIVE_ACCEPTANCE_PENDING',
            engine_id=ENGINE, volume=VOLUME, manifest=str(D/'PUBLIC_PYTEST_CACHE.json'),
            manifest_sha256=digest, verified_files=len(files), volume_mountpoint_inside_engine=volume['Mountpoint'],
            physical_ssd_engine_root=str(S/'engine17-r1/docker'), model_calls=0,
            task_or_test_changes=0, image_changes=0, official_verifier_executed=False)
        with receipt.open('x') as target:
            json.dump(result,target,indent=2)
        print(json.dumps(result))
    finally:
        if created:
            docker('rm',CONTAINER)


if __name__ == '__main__':
    main()
