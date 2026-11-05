"""Native Docker8-way /28 public-NAT probe, exact owned cleanup, no model keys."""
from concurrent.futures import ThreadPoolExecutor
import ipaddress,json,os,subprocess,time
from pathlib import Path
R=Path('/home/chenkeyi/.local/share/harbor-rsi/qwen35-new-cf500-tmax500-20261029')
for key in ['DEEPSEEK_API_KEY','GH_TOKEN']:os.environ.pop(key,None)
def run(args,**kw):return subprocess.run(args,capture_output=True,text=True,check=True,**kw)
assert run(['docker','info','--format','{{.ID}}']).stdout.strip()=='c6e16cdf-e878-4cc5-84c8-78a56c54b5c5'
routes=json.loads(run(['ip','-j','route','show']).stdout)
for row in routes:
 if row['dst']=='default':continue
 existing=ipaddress.ip_network(row['dst'],strict=False)
 if existing.version==4 and existing.overlaps(ipaddress.ip_network('10.241.0.0/16')):raise ValueError('Scoped probe range overlaps existing route')
receipt=next(json.loads(p.read_text()) for p in (R/'checks/tmax-environments-runtime-r4').glob('*.json') if json.loads(p.read_text())['status']=='IMAGE_AND_ORIGINAL_INITIAL_STATE_PASSED_FINAL_VERIFIER_PENDING')
image=receipt['image_id'];owner='cf-tmax-network-capacity-r4-20261030';nets=[];records=[]
code='import urllib.request,urllib.error\ntry:\n urllib.request.urlopen("https://api.deepseek.com/v1/models",timeout=15)\nexcept urllib.error.HTTPError as e:\n assert e.code==401,e.code\n print("OFFICIAL_API_TLS_HTTP401_WITHOUT_CREDENTIAL",flush=True);__import__("time").sleep(10)'
try:
 for i in range(8):
  name=owner+'-'+str(i);subnet=str(ipaddress.ip_network((int(ipaddress.ip_address('10.241.241.0'))+16*i,28)))
  reply=run(['docker','network','create','--label','rsi.campaign='+R.name,'--label','rsi.probe='+owner,'--subnet',subnet,name],timeout=20)
  nets.append(dict(name=name,id=reply.stdout.strip(),subnet=subnet))
 def probe(item):
  name=item['name']+'-container'
  try:
   reply=run(['docker','run','--rm','--name',name,'--label','rsi.probe='+owner,'--network',item['name'],'--cpus','1','--memory','2048m','--entrypoint','python3',image,'-c',code],timeout=180)
   return item|dict(returncode=reply.returncode,stdout=reply.stdout,passed=True)
  except subprocess.SubprocessError as e:return item|dict(passed=False,error=str(e))
 with ThreadPoolExecutor(max_workers=8) as pool:records=list(pool.map(probe,nets))
finally:
 cleanup=[]
 for item in nets:
  subprocess.run(['docker','rm','-f',item['name']+'-container'],capture_output=True,text=True,timeout=20)
  reply=subprocess.run(['docker','network','rm',item['id']],capture_output=True,text=True,timeout=20)
  cleanup.append(dict(network_id=item['id'],removed=reply.returncode==0,stderr=reply.stderr))
 value=dict(passed=len(records)==8 and all(x['passed'] for x in records) and all(x['removed'] for x in cleanup),native_concurrent_containers=8,records=records,cleanup=cleanup,
  network_policy='Dedicated perTask native Compose /28; public NAT; no daemon changes',source_image_id=image,teacher_model_calls=0,official_api_calls='Eight unauthenticated /v1/models requests; expected401; no generation',existing_routes_checked=routes)
 (R/'checks/isolated-network-capacity-r4.json').write_text(json.dumps(value,indent=2));print(json.dumps(value))
