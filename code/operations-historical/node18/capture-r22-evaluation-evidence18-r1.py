"""Snapshot selected metadata only; never rewrite live Results/Recorder/checkpoints."""
from pathlib import Path
import hashlib,json,shutil,tarfile,time
R=Path('/ssd/chenkeyi/qwen35-sft-772-20261101');E=R/'formal-native-eval-r1';C=Path('/data/chenkeyi/qwen35-sft-772-20261101/control');name='r22-five30-winner267-live-20261102-r1';root=R/'evidence-snapshots'/name;root.mkdir()
paths=set(p for p in(R/'checks').glob('*.json')if p.stat().st_mtime>=1793588224)
paths.update(p for p in R.glob('*.py')if p.stat().st_mtime>=1793588224)
paths.update([R/'configs/diagnostic150-five-model-r1.json'])
paths.update(p for p in(E/'manifests').glob('DIAGNOSTIC*')if p.is_file())
paths.update([E/'manifests/EVALUATION417_EXPLICIT_IPAM_R1.json'])
paths.update(p for p in(E/'configs/evaluation-ipam-r1').glob('*.json'))
paths.update(p for p in(E/'checks').glob('DIAGNOSTIC*')if p.is_file())
paths.update(p for p in(E/'reports').glob('DIAGNOSTIC150*')if p.is_file())
paths.update(p for p in(R/'nll-audits').glob('*/NLL_AUDIT_COMPLETE.json'))
for model in ['new-m1-cf416-128k-e5','new-m2-tmax356-128k-e5']:
 for n in ['HF_EXPORT_COMPLETE.json','FINAL_HF_ADMISSION.json','TOOL_PROTOCOL_SMOKE.json','HF_LOAD_SMOKE.json']:paths.add(R/'runs'/model/n)
for p in (R/'runtime-snapshots').glob('active-diagnostics-*/ACTUAL_DIAGNOSTIC_CONCURRENCY.json'):
 if p.stat().st_mtime>=1793595000:paths.update(x for x in p.parent.iterdir()if x.is_file())
records=[]
for p in sorted(paths):
 if not p.is_file():continue
 relative=p.relative_to(R);dest=root/'node18'/relative;dest.parent.mkdir(parents=True,exist_ok=True);raw=p.read_bytes();dest.write_bytes(raw);records.append(dict(path=str(dest.relative_to(root)),bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest(),source=str(p)))
for n in ['NATIVE_ADVANCE_OWNER.json','NATIVE_ADVANCE_STATUS.json','NATIVE_ADVANCE_R20_CONTROLLED_HANDOFF.json','NATIVE_ADVANCE_R21_CONTROLLED_HANDOFF.json','NATIVE_ADVANCE_R22_CONTROLLED_HANDOFF.json','USER_EVALUATION_SCOPE_OVERRIDE_R1.json','CURRENT_EXECUTION_STATUS.json']:
 p=C/n
 if not p.exists():continue
 dest=root/'control'/n;dest.parent.mkdir(exist_ok=True);raw=p.read_bytes();dest.write_bytes(raw);records.append(dict(path=str(dest.relative_to(root)),bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest(),source=str(p)))
manifest=root/'SNAPSHOT_MANIFEST.json';manifest.write_text(json.dumps(dict(at=time.time(),name=name,files=records,bytes=sum(x['bytes']for x in records),live_originals_unmodified=True),indent=2)+'\n')
archive=root.with_suffix('.tar.gz')
with tarfile.open(archive,'w:gz')as tar:tar.add(root,arcname=name)
seal=dict(name=name,files=len(records),bytes=sum(x['bytes']for x in records),snapshot_manifest_sha256=hashlib.sha256(manifest.read_bytes()).hexdigest(),archive_bytes=archive.stat().st_size,archive_sha256=hashlib.sha256(archive.read_bytes()).hexdigest(),archive=str(archive),snapshot=str(root))
root.with_suffix('.seal.json').write_text(json.dumps(seal,indent=2)+'\n');print(json.dumps(seal))
