"""Finalize verified SSD public assets after copy; keep original six Compose links."""
import hashlib,importlib,json,shlex,subprocess,time
from pathlib import Path
R=Path('/ssd/chenkeyi/qwen35-sft-772-20261101');mirror=R/'controller-public-source-mirrors'
roots=['/home/chenkeyi/.local/share/harbor-rsi/tb21-completion-20261015','/home/chenkeyi/.local/share/harbor-rsi/remote-preparation-20261015/asset-overlays']
assets=[roots[0]+'/'+s for s in ['public-ca','apt-bullseye','curl-network','public-sam-git','git-safe']]+[roots[1]+'/huggingface/hub']
proof=R/'checks/PUBLIC_BIND_ASSET_MIRROR_AND_ROOT_ACCEPTANCE_R1.json';assert not proof.exists()
code="import pathlib,json,hashlib; roots="+repr(assets)+"; print(json.dumps([dict(path=str(f),bytes=f.stat().st_size,sha256=hashlib.sha256(f.read_bytes()).hexdigest())for p in roots for f in sorted(pathlib.Path(p).rglob('*'))if f.is_file()]))"
manifest=json.loads(subprocess.check_output(['/usr/bin/ssh','-F',str(R/'control-ssh/formal-engine149-r1.conf'),'127.0.0.1','python3 -c '+shlex.quote(code)],text=True,timeout=90))
for row in manifest:
 p=mirror/row['path'].lstrip('/');assert p.stat().st_size==row['bytes']and hashlib.sha256(p.read_bytes()).hexdigest()==row['sha256']
changes=[]
for raw in roots:
 p=Path(raw);dest=mirror/raw.lstrip('/');entries=list(p.iterdir());assert entries and all(x.is_symlink()and x.resolve().is_relative_to(dest)for x in entries)
 before={x.name:hashlib.sha256(x.read_bytes()).hexdigest()for x in entries};backup=p.with_name(p.name+'.before-ssd-public-r1');assert not backup.exists()
 temporary=p.with_name(p.name+'.ssd-public-r1')
 if temporary.is_symlink():assert temporary.resolve()==dest
 else:temporary.symlink_to(dest,target_is_directory=True)
 p.rename(backup);temporary.rename(p);assert p.resolve()==dest
 for name,digest in before.items():assert hashlib.sha256((p/name).read_bytes()).hexdigest()==digest
 changes.append(dict(path=raw,ssd_target=str(dest),original_directory_preserved=str(backup),compose_hashes_unchanged=before))
for row in manifest:
 p=Path(row['path']);assert p.resolve().is_relative_to(R)and p.stat().st_size==row['bytes']and hashlib.sha256(p.read_bytes()).hexdigest()==row['sha256']
v=dict(passed=True,at=time.time(),public_assets_only=True,files=len(manifest),bytes=sum(x['bytes']for x in manifest),manifest=manifest,parents=changes,original_task_tests_verifier_unchanged=True,transfer='rsync -aLR --copy-links; exact staging; no --delete; bounded single transfer',earlier_prepare_failures_preserved=['r1 rsync wall limit240s','r2 EXDEV before parent publication; no original files changed'],source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
proof.write_text(json.dumps(v,indent=2)+'\n');print(json.dumps({k:v[k]for k in ['passed','files','bytes','parents']}))
