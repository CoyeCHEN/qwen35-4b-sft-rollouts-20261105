"""Admit one exact public OCI archive into the persistent download cache."""
import hashlib,json,shutil,sys
from pathlib import Path
from verify_public_oci import verify,file_sha
ident=sys.argv[1];assert ident.replace('_','').replace('-','').isalnum()
r=Path('/ssd/chenkeyi/qwen35-new-cf500-tmax500-20261029/registry/tasks-local-skopeo-r1')/ident
origin=r/'cache-origin.json';source=json.loads(origin.read_text())
if (r/'cache.json').exists():
 old=json.loads((r/'cache.json').read_text());assert old['archive_sha256']==source['archive_sha256'];print(old['status']);raise SystemExit
assert shutil.disk_usage(r).free>100*1024**3
value=verify(source['source'],r/'image.oci.tar');assert value['archive_sha256']==source['archive_sha256']
value['origin_cache_receipt_sha256']=file_sha(origin)
with (r/'cache.json').open('x') as stream:stream.write(json.dumps(value,indent=2))
print(value['status'],value['archive_sha256'])
