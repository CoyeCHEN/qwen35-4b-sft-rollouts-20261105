"""Import an already verified native Task image; no build fallback on bad evidence."""
import hashlib,json,shlex,subprocess
from pathlib import Path
from prepare_cf_images import command,image_info
R=Path('/home/chenkeyi/.local/share/harbor-rsi/qwen35-new-cf500-tmax500-20261029')

def import_if_prepared(ident,context_sha,revision,tag):
 receipt=R/'checks/tmax-ssd17-archives-r2'/(ident+'.json')
 if not receipt.exists():return None
 value=json.loads(receipt.read_text());source=value['source_context']
 if value['status']!='ORIGINAL_NATIVE_OCI_ARCHIVE_BUILT_INITIAL_AND_VERIFIER_TESTS_PENDING' or not value['all_manifest_config_layer_hashes_verified']:
  raise ValueError('Native SSD cache receipt is not verified')
 if source['task_id']!=ident or source['build_context_sha256']!=context_sha or source['source_revision']!=revision:
  raise ValueError('Native SSD image belongs to another frozen source context')
 remote=Path(value['archive']);root=Path('/ssd/chenkeyi/qwen35-new-cf500-tmax500-20261029/buildkit-rootless-r2/archives')
 if not remote.is_relative_to(root/ident) or '..' in remote.parts:raise ValueError('Archive path escaped owned Task cache')
 transfers=R/'sources/ssd17-image-transfers';transfers.mkdir(exist_ok=True);archive=transfers/(ident+'.oci.tar')
 ssh=['ssh','-S','/home/chenkeyi/.ssh/cf17-20261028.sock','-oBatchMode=yes','-oProxyCommand=false']
 host='chenkeyi@180.163.192.17'
 with (transfers/(ident+'.transfer.log')).open('x') as log:
  subprocess.run(['rsync','-a','--bwlimit=8192','-e',shlex.join(ssh),host+':'+str(remote),str(archive)],check=True,stdout=log,stderr=subprocess.STDOUT,timeout=1800)
 h=hashlib.sha256()
 with archive.open('rb') as stream:
  for block in iter(lambda:stream.read(1024*1024),b''):h.update(block)
 if h.hexdigest()!=value['archive_sha256']:raise ValueError('Native archive transport SHA mismatch')
 with (transfers/(ident+'.load.log')).open('x') as log:
  subprocess.run(['docker','image','load','--input',str(archive)],check=True,stdout=log,stderr=subprocess.STDOUT,timeout=900)
 info=image_info(value['native_manifest_digest'])
 if info is None or info['Id']!=value['native_manifest_digest']:raise ValueError('Native Docker imported image identity differs')
 current=image_info(tag)
 if current and current['Id']!=info['Id']:raise ValueError('Existing native tag differs; never overwrite')
 if current is None:command(['docker','tag',info['Id'],tag]).check_returncode()
 archive.unlink() # Only transport duplicate; verified original stays on17 SSD.
 return info,dict(receipt=str(receipt),receipt_sha256=hashlib.sha256(receipt.read_bytes()).hexdigest(),archive_sha256=value['archive_sha256'],native_manifest_digest=value['native_manifest_digest'],source_context_sha256=context_sha)
