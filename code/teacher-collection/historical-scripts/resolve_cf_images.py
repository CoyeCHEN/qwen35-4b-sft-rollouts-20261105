"""Freeze original public CF image identities; no model or benchmark changes."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
ACCEPT = ', '.join(['application/vnd.oci.image.manifest.v1+json',
    'application/vnd.docker.distribution.manifest.v2+json',
    'application/vnd.oci.image.index.v1+json',
    'application/vnd.docker.distribution.manifest.list.v2+json'])


def main():
    rows = list(map(json.loads, (ROOT/'manifests/CALIBFORGE_500_TASKS.jsonl').open()))
    out = ROOT/'checks/cf-public-image-identities'; out.mkdir(exist_ok=True)
    url = 'https://auth.docker.io/token?service=registry.docker.io&scope=repository:aweaiteam/calibforge:pull'
    with urlopen(url, timeout=30) as response:
        token = json.load(response)['token']

    def resolve(row):
        destination = out/(row['task_id']+'.json')
        previous=[]
        if destination.exists():
            old=json.loads(destination.read_text())
            if old['status']=='OFFICIAL_REGISTRY_IDENTITY_FROZEN':
                return old
            previous=old.get('previous_resolution_attempts',[])+[{k:v for k,v in old.items() if k!='previous_resolution_attempts'}]
        image = row['docker_image']
        if not image.startswith('aweaiteam/calibforge:'):
            raise ValueError('Unexpected official image repository')
        tag = image.split(':', 1)[1]
        record = dict(task_id=row['task_id'], image=image,previous_resolution_attempts=previous)
        try:
            request = Request('https://registry-1.docker.io/v2/aweaiteam/calibforge/manifests/'+tag,
                headers={'Authorization':'Bearer '+token, 'Accept':ACCEPT})
            with urlopen(request, timeout=40) as response:
                raw = response.read(); declared = response.headers['Docker-Content-Digest']
            sha = hashlib.sha256(raw).hexdigest()
            if declared != 'sha256:'+sha:
                raise ValueError('Official registry manifest digest mismatch')
            manifest = json.loads(raw)
            (out/(row['task_id']+'.manifest.json')).write_bytes(raw)
            record.update(status='OFFICIAL_REGISTRY_IDENTITY_FROZEN',manifest_sha256=sha,
                pinned='aweaiteam/calibforge@'+declared,top_manifest_digest=declared,
                media_type=manifest['mediaType'],config_digest=manifest.get('config',{}).get('digest'),
                compressed_layer_bytes=sum(x['size'] for x in manifest.get('layers',[])))
        except (OSError, ValueError, KeyError) as error:
            record.update(status='PUBLIC_MANIFEST_RESOLUTION_FAILED',error_type=type(error).__name__,error=str(error))
        destination.write_text(json.dumps(record, indent=2))
        return record

    with ThreadPoolExecutor(max_workers=4) as pool:
        records = list(pool.map(resolve, rows))
    report = dict(planned=len(rows),frozen=sum(x['status']=='OFFICIAL_REGISTRY_IDENTITY_FROZEN' for x in records),
        unresolved=[x for x in records if x['status']!='OFFICIAL_REGISTRY_IDENTITY_FROZEN'],
        model_calls=0,identity_source='Official DockerHub registry via HTTPS; original tags preserved')
    (ROOT/'checks/cf-public-image-identities.json').write_text(json.dumps(report,indent=2))
    print(json.dumps(report))


if __name__ == '__main__':
    main()
