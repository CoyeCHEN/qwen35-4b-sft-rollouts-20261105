"""Runs inside the actual sandbox with the installed CLI interpreter; GET only."""
import hashlib,json,os,socket,sys,time,urllib.request
from pathlib import Path
spec=json.loads(Path(sys.argv[1]).read_text());cwd=Path.cwd();probe=cwd/('.rsi-env-preflight-write-'+str(os.getpid()));probe.write_bytes(b'permissions-only');probe.unlink()
assets=[]
for item in spec['public_files']:
 p=Path(item['target']);assert p.is_file(),str(p)
 with p.open('rb')as f:digest=hashlib.file_digest(f,'sha256').hexdigest()
 assert digest==item['sha256'],str(p);assets.append(dict(path=str(p),sha256=digest,bytes=p.stat().st_size,readable=True))
wheel=Path(spec['remote_wheel'])
with wheel.open('rb')as f:actual_wheel=hashlib.file_digest(f,'sha256').hexdigest()
assert actual_wheel==spec['wheel_sha256']
assert not Path('/tests/test.sh').exists(),'Private tests visible in agent setup phase'
services=[];opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
for item in spec['model_endpoints']:
 req=urllib.request.Request(item['url'],method='GET')
 with opener.open(req,timeout=8)as r:info=json.load(r)
 assert info['weight_version']==item['weight_version']and info['model_path']==item['model_path']
 services.append(dict(url=item['url'],model_path=info['model_path'],weight_version=info['weight_version'],http_get=True,generation_calls=0))
stat=os.statvfs(cwd);cgroup={}
for n in ['cpu.max','memory.max']:
 p=Path('/sys/fs/cgroup')/n;cgroup[n]=p.read_text().strip()if p.exists()else None
print(json.dumps(dict(passed=True,at=time.time(),hostname=socket.gethostname(),uid=os.getuid(),gid=os.getgid(),cwd=str(cwd),cwd_write_removed=True,available_bytes=stat.f_bavail*stat.f_frsize,available_inodes=stat.f_favail,cgroup=cgroup,public_assets=assets,wheel_sha256=actual_wheel,model_services=services,hidden_tests_not_present_during_agent_phase=True,model_generation_calls=0)))
