"""Export only metadata/code for a completed partial combined-cache audit."""
import datetime
import hashlib
import io
import json
from pathlib import Path
import tarfile

SSD=Path('/ssd/chenkeyi/qwen35-new-cf500-tmax500-20261029')
E=Path('/home/chenkeyi/workspace/RSI/runtime-evidence/qwen35-new-cf500-tmax500-20261029')
D=SSD/'data-corpus-snapshots/r139'
sha=lambda path:hashlib.sha256(path.read_bytes()).hexdigest()
report=json.loads((D/'DATA_AUDIT_PARTIAL.json').read_text())
if report['full_campaign_complete'] or report['formal_corpus_release'] or report['training_started']:
    raise ValueError('Partial cache evidence is not a final release')
paths={name:D/name for name in ['PLAN.json','DATA_AUDIT_PARTIAL.json']}
for pool,stats in report['pools'].items():
    manifest=D/pool/'DATA_MANIFEST.json';audit=D/pool/'NATIVE_CACHE_AUDIT.json'
    if sha(manifest)!=stats['manifest_sha256'] or sha(audit)!=stats['formal_loader_audit_sha256']:
        raise ValueError('Audited corpus identity changed')
    proof=json.loads(audit.read_text())
    if not proof['passed'] or not proof['all_row_labels_checked'] or not proof['numerical_reference']['passed']:
        raise ValueError('Native full cache audit did not pass')
    paths[pool+'/DATA_MANIFEST.json']=manifest;paths[pool+'/NATIVE_CACHE_AUDIT.json']=audit
for name in ['assemble_primary_native_cache17_r139.py','package_combined_cache_metadata17_r141.py']:
    paths['scripts/'+name]=E/'scripts'/name
for name in ['public_corpus.py','public_corpus_audit.py','teacher_segments.py','qwen35.py']:
    paths['native-sft-source/'+name]=E/'sft-code-weight-audit-r3/sft'/name
paths['INPUTS_R136.json']=SSD/'data-primary-snapshots/r136/INPUTS.json'
paths['runtime-clock-offset-r140.json']=E/'checks/runtime-clock-offset-r140.json'
files={name:path.read_bytes() for name,path in paths.items()}
if any(len(blob)>10*1024**2 for blob in files.values()):raise ValueError('Unexpected large metadata member')
manifest=dict(created_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
    files=[dict(path=name,sha256=hashlib.sha256(blob).hexdigest(),bytes=len(blob)) for name,blob in sorted(files.items())],
    copied_raw_model_content=False,copied_token_caches=False,copied_images_or_environments=False,
    data_cache_location=str(D),full_campaign_complete=False,formal_corpus_release=False)
files['COMBINED_CACHE_METADATA_R141.json']=json.dumps(manifest,indent=2).encode()
path=D/'METADATA_EVIDENCE_R141.tar.gz'
with tarfile.open(path,'x:gz') as archive:
    for name,blob in sorted(files.items()):
        item=tarfile.TarInfo(name);item.size=len(blob);item.mode=0o600;archive.addfile(item,io.BytesIO(blob))
value=dict(path=str(path),sha256=sha(path),bytes=path.stat().st_size,files=len(files))
with (D/'METADATA_EVIDENCE_R141_IDENTITY.json').open('x') as stream:json.dump(value,stream,indent=2)
print(json.dumps(value))
