"""Capture the actually imported Harbor/plugin code for SSD-only installation17."""
import datetime
import hashlib
import importlib.metadata as metadata
import io
import json
from pathlib import Path
import sys
import tarfile

import harbor
import harbor_remote_docker

R=Path('/home/chenkeyi/.local/share/harbor-rsi/qwen35-new-cf500-tmax500-20261029')
D=R/'checks/controller17-runtime-source-r156';D.mkdir(exist_ok=False)
files={};modules=[]
for module,name in [(harbor,'harbor'),(harbor_remote_docker,'harbor-remote-docker')]:
    root=Path(module.__file__).resolve().parent
    distribution=metadata.distribution(name)
    destination=name.replace('-','_')
    for path in sorted(root.rglob('*')):
        if not path.is_file() or '__pycache__' in path.parts or path.suffix=='.pyc':continue
        files[destination+'/'+root.name+'/'+str(path.relative_to(root))]=path.read_bytes()
    for path in sorted(Path(distribution._path).iterdir()):
        if path.is_file() and path.name not in ['RECORD','direct_url.json']:
            files[destination+'/'+Path(distribution._path).name+'/'+path.name]=path.read_bytes()
    modules.append(dict(name=name,version=distribution.version,actual_import_root=str(root),
        bundle_root=destination,original_dist_info=str(distribution._path)))
seen=set();requirements=[]
for distribution in metadata.distributions():
    name=distribution.metadata.get('Name');version=distribution.version
    if not name or name.lower() in seen:continue
    seen.add(name.lower())
    if name.lower() in ['harbor','harbor-remote-docker','open-harness-ai']:continue
    requirements.append(name+'=='+version)
files['requirements-exact.txt']=('\n'.join(sorted(requirements,key=str.lower))+'\n').encode()
manifest=dict(created_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
    source_interpreter=sys.version,source_executable=sys.executable,modules=modules,
    files=[dict(path=name,sha256=hashlib.sha256(blob).hexdigest(),bytes=len(blob)) for name,blob in sorted(files.items())],
    purpose='Repack/install exact resolved Harbor/plugin code on17SSD; no source edits, Task edits or model calls',
    teacher_wheel_sha256='c686ba3f429d8257a060cf6b6a6e4c5aa7d740f33b2d59180d9a2717b55d0db8',
    environments_built_on149=0,raw_trajectories_included=0)
files['SOURCE_MANIFEST_R156.json']=json.dumps(manifest,indent=2).encode()
archive=R/'checks/controller17-runtime-source-r156.tar.gz'
with tarfile.open(archive,'x:gz') as tar:
    for name,blob in sorted(files.items()):
        item=tarfile.TarInfo(name);item.size=len(blob);item.mode=0o600;tar.addfile(item,io.BytesIO(blob))
identity=dict(path=str(archive),sha256=hashlib.sha256(archive.read_bytes()).hexdigest(),bytes=archive.stat().st_size,files=len(files))
with (D/'IDENTITY.json').open('x') as stream:json.dump(identity,stream,indent=2)
print(json.dumps(identity))
