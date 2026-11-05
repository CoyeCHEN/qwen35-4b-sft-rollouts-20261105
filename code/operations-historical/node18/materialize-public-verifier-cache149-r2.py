"""Copy verified public dependencies into one fresh private Trial rootfs."""
import argparse,hashlib,json,pathlib,subprocess,time
A=pathlib.Path('/home/chenkeyi/.local/share/harbor-rsi/qwen35-new772-tb21-20261101');BASE=A/'public-verifier-cache/torch270-cp313-r1'
ENGINE='c6e16cdf-e878-4cc5-84c8-78a56c54b5c5';IMAGE='sha256:c50ac169e11465f41b49749fe87e4487f24d31a0c39c0906cd3242cc5499c690'
PROBE=r'''import hashlib,json,pathlib,sys
p=pathlib.Path(sys.argv[1]);m=json.loads(p.read_text());count=0;size=0
for row in m['files']:
 rel=pathlib.PurePosixPath(row['path']);prefix=rel.parts[0];assert prefix in ['uv-cache','managed-python']and'..'not in rel.parts
 root=pathlib.Path('/root/.cache/uv'if prefix=='uv-cache'else'/root/.local/share/uv/python');f=root.joinpath(*rel.parts[1:])
 if row['kind']=='file':
  assert f.is_file()and f.stat().st_size==row['bytes'];assert hashlib.file_digest(f.open('rb'),'sha256').hexdigest()==row['sha256'];count+=1;size+=row['bytes']
 elif row['kind']=='symlink':assert f.is_symlink()and str(f.readlink())==row['target']and f.exists()
 elif row['kind']=='directory':assert f.is_dir()
p.unlink();print(json.dumps(dict(passed=True,files=count,bytes=size,python_version=sys.version,actual_private_cache_sha_verified=True)))'''
def sha(p):
 with p.open('rb')as f:
  h=hashlib.sha256()
  for block in iter(lambda:f.read(4*1024*1024),b''):h.update(block)
 return h.hexdigest()
def docker(args,**kwargs):return subprocess.run(['docker','--host','unix:///var/run/docker.sock',*args],check=True,**kwargs)
def main():
 p=argparse.ArgumentParser();p.add_argument('--identity',required=True);p.add_argument('--receipt-sha256',required=True);p.add_argument('--workspace',required=True);args=p.parse_args();receipt=BASE/'PUBLIC_DEPENDENCY_ARCHIVE_READY_R1.json';assert sha(receipt)==args.receipt_sha256;r=json.loads(receipt.read_text());archive=pathlib.Path(r['archive']);assert archive.parent==BASE and sha(archive)==r['archive_sha256']
 workspace=pathlib.Path(args.workspace);assert workspace.is_absolute()and workspace.name.endswith('-'+args.identity)and workspace.is_relative_to(A/'staging');assert(workspace/'.identity').read_text()==args.identity
 assert docker(['info','--format','{{.ID}}'],capture_output=True,text=True).stdout.strip()==ENGINE
 ids=docker(['ps','-q','--filter','label=io.harbor.remote-docker.identity='+args.identity],capture_output=True,text=True).stdout.split();assert len(ids)==1
 info=json.loads(docker(['inspect',ids[0]],capture_output=True,text=True).stdout)[0];assert info['Image']==IMAGE and info['State']['Running'];labels=info['Config']['Labels'];assert labels['io.harbor.remote-docker.identity']==args.identity and labels['com.docker.compose.project']==workspace.name
 assert workspace.name.startswith(('q35envpreflight30','q35accepted30','q35selected267'))
 # Called by native AGENT_START after CLI setup, before Agent.run or hidden tests.
 docker(['exec','-u','root',ids[0],'test','!','-e','/tests/test.sh'],capture_output=True,text=True)
 started=time.time()
 with archive.open('rb')as stream:docker(['cp','-',ids[0]+':/'],stdin=stream,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,timeout=300)
 manifest=pathlib.Path(r['file_manifest_path']);assert sha(manifest)==r['file_manifest_sha256'];sealed_receipt=BASE/'SEALED_CACHE_CURRENT.json';assert sha(sealed_receipt)==r['public_cache_receipt_sha256'];python=json.loads(sealed_receipt.read_text())['python_executable'];assert python.startswith('/root/.local/share/uv/python/')
 remote='/tmp/rsi-public-cache-verification-'+args.identity+'.json';docker(['cp',str(manifest),ids[0]+':'+remote],capture_output=True,text=True,timeout=30)
 checked=docker(['exec','-u','root','-e','PYTHONDONTWRITEBYTECODE=1',ids[0],python,'-c',PROBE,remote],capture_output=True,text=True,timeout=300);probe=json.loads(checked.stdout);assert probe['passed']
 proof=dict(source_sha256=sha(pathlib.Path(__file__)),at=time.time(),seconds=time.time()-started,identity=args.identity,container_id=info['Id'],engine_id=ENGINE,image_id=IMAGE,archive_sha256=r['archive_sha256'],source_read_only_shared_cache=True,private_trial_rootfs_copy=True,shared_write_mount=False,actual_private_cache=probe,official_task_tests_reward_and_resources_unchanged=True,no_hidden_tests_present_at_copy=True,model_generation_calls=0)
 print(json.dumps(proof))
if __name__=='__main__':main()
