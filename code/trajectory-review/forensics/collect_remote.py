"""Stream derived, credential-filtered evidence into this independent local audit only."""
import base64,gzip,hashlib,json,subprocess,sys,time
from pathlib import Path
A=Path(__file__).resolve().parents[1];mode=sys.argv[1];host={'current':'ruc-a800-17','old':'aibox-149'}[mode]
code=(A/'scripts/export_closed_trajectories.py').read_bytes()
proc=subprocess.Popen(['ssh','-o','BatchMode=yes','-o','ConnectTimeout=10',host,'python3 - '+mode],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=(A/'private'/('collector-'+mode+'.log')).open('wb'))
proc.stdin.write(code);proc.stdin.close();manifest=[]
for line in proc.stdout:
    obj=json.loads(line);packed=base64.b64decode(obj.pop('gzip_base64'));assert hashlib.sha256(packed).hexdigest()==obj['compressed_sha256']
    data=gzip.decompress(packed);assert hashlib.sha256(data).hexdigest()==obj['sha256']
    path=A/'private'/(obj['id']+'.json.gz');assert not path.exists();path.write_bytes(packed)
    report=json.loads(data);obj.update(file=path.name,task=report['meta']['task'],summary=report['summary'],journal_sha256=report['meta'].get('journal_sha256'))
    manifest.append(obj);print(json.dumps(dict(saved=path.name,task=obj['task'],label=obj['label'],calls=report['summary']['calls'],tools=report['summary']['tools'])),flush=True)
status=proc.wait();assert status==0,status
p=A/'private'/('MANIFEST_'+mode+'.json');assert not p.exists();p.write_text(json.dumps(dict(at=time.time(),host=host,entries=manifest,mode=mode,remote_files_modified=False),ensure_ascii=False,indent=2)+'\n')
print(json.dumps(dict(done=True,mode=mode,count=len(manifest))),flush=True)
