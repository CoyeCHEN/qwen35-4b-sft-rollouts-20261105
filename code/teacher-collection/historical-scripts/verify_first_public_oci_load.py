"""Observe one native OCI import; pin its original tag without changing existing tags."""
import hashlib,json,os,subprocess
from pathlib import Path
r=Path('/home/chenkeyi/.local/share/harbor-rsi/qwen35-new-cf500-tmax500-20261029');task='mathematics_20260509_111805_003'
os.environ.update(DOCKER_HOST='ssh://chenkeyi@127.0.0.1:5102',SSH_AUTH_SOCK='/home/chenkeyi/.local/share/harbor-rsi/near-r3-20261015/auth.sock')
os.environ['PATH']=str(r/'client-bin-v2')+':'+os.environ['PATH']
def command(args):return subprocess.run(args,capture_output=True,text=True,timeout=30)
source=json.loads((r/'checks/cf-public-image-identities'/(task+'.json')).read_text());expected=source['top_manifest_digest']
p=r/'sources/public-image-transfers'/(task+'.oci.tar')
with p.open('rb') as stream:archive_sha=hashlib.file_digest(stream,'sha256').hexdigest()
assert archive_sha=='dd5fc7fd58d533604d87f19559ea97e383da2918685ff520eed10027acab3d10'
info=command(['docker','image','inspect',expected]);info.check_returncode();image=json.loads(info.stdout)[0];assert image['Id']==expected
old=command(['docker','image','inspect',source['image']])
if old.returncode==0:assert json.loads(old.stdout)[0]['Id']==expected
else:
 assert 'No such image' in old.stderr
 command(['docker','tag',expected,source['image']]).check_returncode()
engine=command(['docker','info','--format','{{.ID}}']);engine.check_returncode();assert engine.stdout.strip()=='c6e16cdf-e878-4cc5-84c8-78a56c54b5c5'
report=dict(passed=True,task_id=task,original_registry_manifest=expected,actual_image_id=image['Id'],
 source_manifest_config_digest=source['config_digest'],archive_sha256=archive_sha,
 original_tag_pinned_without_overwrite=True,daemon_id=engine.stdout.strip(),
 source_archive_retained_on_17=True,model_calls=0,teacher_attempts=0,
 scope='Public image transport proof only; basic setup and official verifier admission remain separate')
target=r/'checks/cf-public-oci-native-import-proof.json';assert not target.exists();target.write_text(json.dumps(report,indent=2));print(json.dumps(report))
