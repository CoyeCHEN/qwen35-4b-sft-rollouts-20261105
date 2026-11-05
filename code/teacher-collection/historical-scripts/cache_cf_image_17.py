"""One pinned public image cache diagnostic, no teacher or GPU work.

The Harbor controller/engine remains 149. This checks the already authorized
17 download path after three completed 149 registry-pull timeouts.
"""
import datetime
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import time

ROOT = Path('/ssd/chenkeyi/qwen35-new-cf500-tmax500-20261029/registry')
IMAGE = 'aweaiteam/calibforge:software-engineering_20260605_015435_004_20260620_203601_463987'


def main():
    ROOT.mkdir(parents=True, exist_ok=True)
    receipt = ROOT / 'software-canary-cache.json'
    if receipt.exists():
        raise FileExistsError('Previous cache diagnostic is preserved; inspect it before another request')
    metadata_file = ROOT / 'software-canary-source.json'
    metadata = json.loads(metadata_file.read_text())
    manifest_raw = (ROOT / 'software-canary-official-manifest.json').read_bytes()
    if hashlib.sha256(manifest_raw).hexdigest() != metadata['manifest_sha256'] or metadata['image'] != IMAGE:
        raise ValueError('Official pinned manifest identity changed')
    data = json.loads(manifest_raw)
    pinned = metadata['pinned']
    top_sha = metadata['top_manifest_digest']
    if shutil.disk_usage(ROOT).free < 100 * 1024**3:
        raise ValueError('Public cache disk headroom is insufficient')
    started = time.monotonic()
    info = subprocess.run(['docker','info','--format','{{.ID}} {{.Name}}'],check=True,capture_output=True,text=True,timeout=15)
    record = dict(status='PINNED_PUBLIC_IMAGE_PULL', started_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        original_image=IMAGE, pinned_image=pinned, top_manifest_sha256=top_sha,
        config_digest=data.get('config',{}).get('digest'), compressed_layer_bytes=sum(layer['size'] for layer in data['layers']),
        cache_daemon=info.stdout.strip(), destination_controller='aibox-149', model_calls=0, gpu_work=False,
        model_provider_changed=False, worker_count=1)
    receipt.write_text(json.dumps(record, indent=2))
    try:
        with (ROOT / 'software-canary-pull.log').open('x') as log:
            subprocess.run(['docker','pull',pinned],check=True,stdout=log,stderr=subprocess.STDOUT,timeout=900)
        inspected = subprocess.run(['docker','image','inspect',pinned],check=True,capture_output=True,text=True,timeout=20)
        image = json.loads(inspected.stdout)[0]
        record.update(status='PUBLIC_IMAGE_PULLED_SAVING_ARCHIVE', image_id=image['Id'], image_size_bytes=image['Size'],
            repo_digests=image.get('RepoDigests', []))
        receipt.write_text(json.dumps(record, indent=2))
        archive = ROOT / 'software-canary-image.tar'
        subprocess.run(['docker','image','save','--output',str(archive),image['Id']],check=True,capture_output=True,text=True,timeout=600)
        with archive.open('rb') as stream:
            hasher = hashlib.sha256()
            for chunk in iter(lambda: stream.read(1024 * 1024), b''):
                hasher.update(chunk)
            sha = hasher.hexdigest()
        record.update(status='PINNED_PUBLIC_IMAGE_ARCHIVE_READY', archive=str(archive),archive_sha256=sha,
            archive_bytes=archive.stat().st_size, seconds=time.monotonic()-started)
    except (OSError, subprocess.SubprocessError) as error:
        record.update(status='PUBLIC_CACHE_DIAGNOSTIC_FAILED',error_type=type(error).__name__,seconds=time.monotonic()-started)
    receipt.write_text(json.dumps(record, indent=2)); print(json.dumps(record),flush=True)


if __name__ == '__main__':
    main()
