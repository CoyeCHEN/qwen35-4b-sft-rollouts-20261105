"""Single-worker public image cache helper, invoked by controller 149 over SSH."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time

ROOT = Path('/ssd/chenkeyi/qwen35-new-cf500-tmax500-20261029/registry/tasks')


def file_sha(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024*1024), b''):
            h.update(chunk)
    return h.hexdigest()


def main():
    source = json.load(sys.stdin)
    ident = source['task_id']; digest = source['top_manifest_digest']
    if not ident.replace('_','').replace('-','').isalnum() or not digest.startswith('sha256:'):
        raise ValueError('Invalid public image identity')
    if source['status'] != 'OFFICIAL_REGISTRY_IDENTITY_FROZEN' or source['pinned'] != 'aweaiteam/calibforge@'+digest:
        raise ValueError('Only independently frozen official identities can be cached')
    directory = ROOT/ident; directory.mkdir(parents=True, exist_ok=True)
    receipt = directory/'cache.json'
    if receipt.exists():
        old = json.loads(receipt.read_text())
        if old.get('status') == 'PINNED_PUBLIC_IMAGE_ARCHIVE_READY':
            if old['pinned'] != source['pinned']:
                raise ValueError('Public image identity changed')
            print(json.dumps(old)); return
        raise RuntimeError('Previous incomplete cache request requires inspection')
    if shutil.disk_usage(ROOT).free < 100*1024**3:
        raise RuntimeError('Cache disk headroom below 100 GiB')
    start = time.monotonic()
    record = dict(task_id=ident, pinned=source['pinned'], source=source, model_calls=0,
        status='PULLING_PINNED_PUBLIC_IMAGE', cache_daemon='9e09f846-3672-4739-b45b-2eb4330320d1')
    receipt.write_text(json.dumps(record,indent=2))
    try:
        with (directory/'pull.log').open('x') as log:
            subprocess.run(['docker','pull',source['pinned']],check=True,stdout=log,stderr=subprocess.STDOUT,timeout=900)
        image = json.loads(subprocess.run(['docker','image','inspect',source['pinned']],check=True,
            capture_output=True,text=True,timeout=20).stdout)[0]
        if source['media_type'].endswith('manifest.v1+json') or source['media_type'].endswith('manifest.v2+json'):
            if image['Id'] != digest:
                raise ValueError('Cache daemon image differs from the frozen manifest')
        archive = directory/'image.tar'
        subprocess.run(['docker','image','save','--output',str(archive),image['Id']],check=True,
            capture_output=True,text=True,timeout=900)
        record.update(status='PINNED_PUBLIC_IMAGE_ARCHIVE_READY', image_id=image['Id'],
            image_size_bytes=image['Size'],repo_digests=image.get('RepoDigests',[]),
            archive=str(archive),archive_bytes=archive.stat().st_size,archive_sha256=file_sha(archive))
    except (OSError,ValueError,subprocess.SubprocessError) as error:
        record.update(status='PUBLIC_CACHE_FAILED',error_type=type(error).__name__)
    record['seconds']=time.monotonic()-start
    receipt.write_text(json.dumps(record,indent=2)); print(json.dumps(record))
    if record['status']!='PINNED_PUBLIC_IMAGE_ARCHIVE_READY':
        raise RuntimeError('Public image cache did not complete')


if __name__=='__main__':
    main()
