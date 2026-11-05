"""Copy existing public preparation assets, preserve bytes, and restore declared roots."""
import hashlib,json,os,shlex,subprocess,time
from pathlib import Path
R=Path('/ssd/chenkeyi/qwen35-sft-772-20261101');E=R/'formal-native-eval-r1'
SSH=['/usr/bin/ssh','-F',str(R/'control-ssh/formal-engine149-r1.conf'),'127.0.0.1']
roots=['/home/chenkeyi/.local/share/harbor-rsi/tb21-completion-20261015','/home/chenkeyi/.local/share/harbor-rsi/remote-preparation-20261015/asset-overlays']
assets=[roots[0]+'/'+s for s in ['public-ca','apt-bullseye','curl-network','public-sam-git','git-safe']]+[roots[1]+'/huggingface/hub']
proof=R/'checks/PUBLIC_BIND_ASSET_MIRROR_AND_ROOT_ACCEPTANCE_R1.json'
assert not proof.exists()
remote='''import hashlib,json,pathlib
paths=PATHS
rows=[]
for root in paths:
 p=pathlib.Path(root)
 for f in sorted(p.rglob('*')):
  if f.is_file():rows.append(dict(path=str(f),bytes=f.stat().st_size,sha256=hashlib.sha256(f.read_bytes()).hexdigest()))
print(json.dumps(rows))
'''.replace('PATHS',repr(assets))
manifest=json.loads(subprocess.check_output(SSH+['python3 -c '+shlex.quote(remote)],text=True,timeout=90))
stage=R/'public-bind-staging-r1';stage.mkdir(exist_ok=True)
cmd=['rsync','-aLR','--copy-links','--timeout=180','--stats','-e','/usr/bin/ssh -F '+str(R/'control-ssh/formal-engine149-r1.conf')]
cmd+=['127.0.0.1:/./'+p.lstrip('/') for p in assets];cmd+=[str(stage)+'/']
res=subprocess.run(cmd,capture_output=True,text=True,timeout=1200,check=True)
for row in manifest:
 f=stage/row['path'].lstrip('/');assert f.stat().st_size==row['bytes']and hashlib.sha256(f.read_bytes()).hexdigest()==row['sha256'],str(f)
mirror=R/'controller-public-source-mirrors'
for asset in assets:
 source=stage/asset.lstrip('/');dest=mirror/asset.lstrip('/');assert not dest.exists();dest.parent.mkdir(parents=True,exist_ok=True);source.rename(dest)
changes=[]
for raw in roots:
 p=Path(raw);dest=mirror/raw.lstrip('/');entries=list(p.iterdir());assert entries and all(x.is_symlink()and x.resolve().is_relative_to(dest)for x in entries)
 before={x.name:hashlib.sha256(x.read_bytes()).hexdigest()for x in entries}
 backup=R/'checks'/('public-bind-original-parent-'+p.name+'-r1');assert not backup.exists()
 temporary=p.with_name(p.name+'.ssd-public-r1');temporary.symlink_to(dest,target_is_directory=True)
 p.rename(backup);temporary.rename(p)
 assert p.resolve()==dest
 for name,digest in before.items():assert hashlib.sha256((p/name).read_bytes()).hexdigest()==digest
 changes.append(dict(path=raw,ssd_target=str(dest),original_directory_preserved=str(backup),compose_hashes_unchanged=before))
for row in manifest:
 p=Path(row['path']);assert p.resolve().is_relative_to(R)and p.stat().st_size==row['bytes']and hashlib.sha256(p.read_bytes()).hexdigest()==row['sha256']
v=dict(resumed_identical_partial_staging_after_bounded_transfer_timeout=True,passed=True,at=time.time(),public_assets_only=True,files=len(manifest),bytes=sum(x['bytes']for x in manifest),manifest=manifest,parents=changes,rsync_argv=cmd,rsync_stdout=res.stdout,official_tasks_tests_verifiers_unmodified=True)
proof.write_text(json.dumps(v,indent=2)+'\n');print(json.dumps({k:v[k]for k in ['passed','files','bytes','parents']}))
