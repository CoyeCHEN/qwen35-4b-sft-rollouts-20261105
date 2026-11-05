"""Download one pinned public uv wheel into the campaign SSD; no system install."""
import hashlib
import json
from pathlib import Path
import urllib.request
import zipfile

D=Path('/ssd/chenkeyi/qwen35-new-cf500-tmax500-20261029/controller17-r1/bootstrap')
D.mkdir(parents=True,exist_ok=True)
metadata_url='https://pypi.org/pypi/uv/0.9.7/json'
with urllib.request.urlopen(metadata_url,timeout=30) as response:info=json.load(response)
matches=[x for x in info['urls'] if 'manylinux' in x['filename'] and 'x86_64' in x['filename'] and x['filename'].endswith('.whl')]
if len(matches)!=1:raise ValueError('No unique pinned x86_64 manylinux wheel')
entry=matches[0];path=D/entry['filename']
if not path.exists():
    temporary=path.with_suffix('.partial')
    with urllib.request.urlopen(entry['url'],timeout=60) as response,temporary.open('wb') as stream:
        while True:
            chunk=response.read(1024*1024)
            if not chunk:break
            stream.write(chunk)
    temporary.replace(path)
digest=hashlib.sha256(path.read_bytes()).hexdigest()
if digest!=entry['digests']['sha256']:raise ValueError('Public wheel digest differs')
with zipfile.ZipFile(path) as archive:
    candidates=[x for x in archive.namelist() if x.endswith('/uv') and not x.endswith('/')]
    if len(candidates)!=1:raise ValueError('No unique public uv executable')
    binary=D/'uv';blob=archive.read(candidates[0])
    if binary.exists() and binary.read_bytes()!=blob:raise ValueError('Existing uv executable differs')
    binary.write_bytes(blob);binary.chmod(0o700)
value=dict(version='0.9.7',metadata_url=metadata_url,wheel_url=entry['url'],wheel_sha256=digest,executable=str(binary),
    executable_sha256=hashlib.sha256(binary.read_bytes()).hexdigest(),system_environment_modified=False,model_calls=0)
with (D/'UV_IDENTITY_R156.json').open('x') as stream:json.dump(value,stream,indent=2)
print(json.dumps(value))
