"""Snapshot growing indexes for a bounded CPU cache audit, without data release."""
import datetime
import hashlib
import io
import json
from pathlib import Path
import shlex
import subprocess
import tarfile

R=Path('/home/chenkeyi/.local/share/harbor-rsi/qwen35-new-cf500-tmax500-20261029')
D=R/'checks/partial-primary-target-audit-r425'
destination='/ssd/chenkeyi/qwen35-new-cf500-tmax500-20261029/data-primary-snapshots/r425'
authority=json.loads((R/'checks/CURRENT_DISPATCH_AUTHORITY_R21.json').read_text())
campaign=json.loads(Path(authority['manifest']).read_text())
deployment_path=Path(campaign['deployment_config'])
assert hashlib.sha256(deployment_path.read_bytes()).hexdigest()==campaign['deployment_config_sha256']
deployment=json.loads(deployment_path.read_text())
D.mkdir(exist_ok=False)
files={}
qualification=(R/'checks/collection-qualification.json').read_bytes()
for pool in ['CALIBFORGE','TMAX']:
    for suffix in ['SUCCESS_INDEX.jsonl','FAILURE_OR_PENDING_INDEX.jsonl']:
        name=pool+'_'+suffix;source=R/'indexes'/name
        # One read descriptor sees either complete generation after atomic rename.
        blob=source.read_bytes();rows=[json.loads(line) for line in blob.splitlines()]
        if suffix=='SUCCESS_INDEX.jsonl' and any(not row['qualified_success'] for row in rows):
            raise ValueError('Non-primary or unqualified row in primary index')
        (D/name).write_bytes(blob)
        files[name]=dict(sha256=hashlib.sha256(blob).hexdigest(),bytes=len(blob),rows=len(rows),source=str(source))
if (R/'checks/collection-qualification.json').read_bytes()!=qualification or any(hashlib.sha256((R/'indexes'/name).read_bytes()).hexdigest()!=row['sha256'] for name,row in files.items()):
    raise ValueError('Indexes changed during snapshot; leave partial candidate for review, do not run audit')
inputs=dict(qualification_snapshot_sha256=hashlib.sha256(qualification).hexdigest(), checked_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),files=files,
    purpose='Immutable partial primary cache token/label/mapping audit; collection continues',
    full_campaign_complete=False,formal_corpus_release=False,training_started=False,
    source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
(D/'INPUTS.json').write_text(json.dumps(inputs,indent=2))
archive=io.BytesIO()
with tarfile.open(fileobj=archive,mode='w:gz') as tar:
    for path in sorted(D.iterdir()):tar.add(path,arcname=path.name)
extract='''import pathlib,sys,tarfile
p=pathlib.Path(sys.argv[1]); p.mkdir(parents=True,exist_ok=False)
with tarfile.open(fileobj=sys.stdin.buffer,mode="r|gz") as archive:
 for member in archive:
  if not member.isfile() or pathlib.Path(member.name).name!=member.name:
   raise ValueError("Unexpected input archive member")
  with (p/member.name).open("xb") as target:target.write(archive.extractfile(member).read())
'''
command=shlex.join(['python3','-c',extract,destination])
subprocess.run([*deployment['ssh'],deployment['host'],command],input=archive.getvalue(),check=True,capture_output=True,timeout=120)
print(json.dumps(dict(destination=destination,files=files,model_calls=0)))
