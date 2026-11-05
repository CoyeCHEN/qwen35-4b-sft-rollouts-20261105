"""Serve verified public archive receipts; no daemon, downloads, model or scheduling."""
import hashlib,json,sys
from pathlib import Path
root=Path('/ssd/chenkeyi/qwen35-new-cf500-tmax500-20261029/registry')
source=json.load(sys.stdin);ident=source['task_id']
assert ident.replace('_','').replace('-','').isalnum() and source['status']=='OFFICIAL_REGISTRY_IDENTITY_FROZEN'
for directory in ['tasks-local-skopeo-r1','tasks']:
 p=root/directory/ident/'cache.json'
 if not p.exists():continue
 x=json.loads(p.read_text())
 if x.get('status')!='PINNED_PUBLIC_IMAGE_ARCHIVE_READY':continue
 assert x['pinned']==source['pinned'] and x['source']['top_manifest_digest']==source['top_manifest_digest']
 archive=Path(x['archive']);assert archive.is_file()
 with archive.open('rb') as stream:
  h=hashlib.sha256()
  for block in iter(lambda:stream.read(1024*1024),b''):h.update(block)
 assert h.hexdigest()==x['archive_sha256']
 print(json.dumps(x));break
else:raise RuntimeError('Frozen public archive not staged; prepare assets before native image import')
