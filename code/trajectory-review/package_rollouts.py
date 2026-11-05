"""Package a frozen trial inventory, streaming files with hashes and secret removal."""
import collections
import datetime
import hashlib
import io
import json
import os
from pathlib import Path
import re
import sys
import tarfile
import time

PATTERN=re.compile(rb'\bsk-[A-Za-z0-9_-]{20,}\b|\bgh[pousr]_[A-Za-z0-9]{20,}\b|\bgithub_pat_[A-Za-z0-9_]{20,}\b')
SECRETS=[v.encode() for k,v in os.environ.items() if len(v)>=16 and re.search(r'(?:API_KEY|GH_TOKEN|ACCESS_TOKEN|SECRET|PASSWORD)$',k)]
PREFIXES=(b'sk-',b'ghp_',b'gho_',b'ghu_',b'ghs_',b'ghr_',b'github_pat_')

def scrub(data):
    count=0
    for value in SECRETS:
        count+=data.count(value); data=data.replace(value,b'*'*len(value))
    data,n=PATTERN.subn(lambda m:b'*'*len(m.group()),data) if any(p in data for p in PREFIXES) else (data,0)
    return data,count+n

class HashedReader:
    def __init__(self,stream,size):
        self.stream=stream; self.remaining=size; self.buffer=b''; self.tail=b''
        self.raw=hashlib.sha256(); self.exported=hashlib.sha256(); self.redactions=0
    def read(self,n):
        while len(self.buffer)<n and (self.remaining or self.tail):
            chunk=self.stream.read(min(1024*1024,self.remaining)) if self.remaining else b''
            if self.remaining and not chunk: raise EOFError('Source shortened during snapshot')
            self.remaining-=len(chunk); self.raw.update(chunk)
            combined=self.tail+chunk
            cutoff=max(0,len(combined)-1024) if self.remaining else len(combined)
            if any(p in combined for p in PREFIXES):
                for match in PATTERN.finditer(combined):
                    if match.start()<cutoff<match.end(): cutoff=match.start()
            for secret in SECRETS:
                index=combined.find(secret)
                if 0<=index<cutoff<index+len(secret): cutoff=index
            clean,count=scrub(combined[:cutoff]); self.redactions+=count
            self.buffer+=clean; self.tail=combined[cutoff:]
        data=self.buffer[:n]; self.buffer=self.buffer[n:]; self.exported.update(data)
        return data

def model_label(row):
    model=(row.get('model') or '').lower()
    if not model: return 'INFRASTRUCTURE_PREFLIGHT'
    if 'install-preflight' in row['job']: return 'INFRASTRUCTURE_PREFLIGHT'
    if '/hot/runs/m1-64k' in model: return 'OLD_M1'
    if '/hot/runs/m2-128k' in model: return 'OLD_M2'
    if 'm0' in model or '/data/models/' in model: return 'M0_BASELINE'
    if 'new-m1' in model:
        return 'NEW_M1_E3' if any(v in model for v in ['e3','epoch3']) else 'NEW_M1_E5'
    for epoch in ['1','3','5']:
        if 'm2-e'+epoch in model: return 'NEW_M2_E'+epoch
    return 'OTHER_STUDENT'

def json_bytes(value): return (json.dumps(value,ensure_ascii=False,indent=2)+'\n').encode()

def main(host):
    root=Path('/home/chenkeyi/.local/share/harbor-rsi' if host=='149' else '/ssd/chenkeyi')/'qwen35-all-student-rollouts-export-20261105'
    inventory=json.loads((root/'INVENTORY.json').read_text())
    trials=inventory['trials']
    # Preserve unfinished attempts separately; their data is a bounded snapshot,
    # never a fabricated Result or completed rollout.
    for path in inventory['pending_without_result']:
        source=Path(path); cfg=json.loads((source/'config.json').read_text()); agent=cfg.get('agent',{})
        if not agent.get('model_name'): continue
        files=[]
        for p in source.rglob('*'):
            if p.is_file() and not p.is_symlink():
                s=p.stat(); files.append({'path':str(p.relative_to(source)),'bytes':s.st_size,'mtime_ns':s.st_mtime_ns})
        trials.append({'trial_id':'UNFINISHED-'+source.name,'task':source.name,'model':agent['model_name'],'job':source.parent.name,'path':path,'files':files,'result_sha256':None,'finished_at':None,'snapshot_only':True})
    final=root/f'host{host}-all-student-trials.tar.gz'
    temporary=final.with_suffix(final.suffix+'.partial')
    if final.exists() or temporary.exists(): raise RuntimeError('Existing export retained; no duplicate packaging')
    files_manifest=[]; redacted=[]; changes=[]; excluded=[]; started=time.monotonic()
    total=sum(f['bytes'] for t in trials for f in t['files']); done=0; last=0
    with tarfile.open(temporary,'w:gz',compresslevel=1,copybufsize=1024*1024) as archive:
        for index,trial in enumerate(trials,1):
            label=model_label(trial); trial['export_model_label']=label
            prefix=f'host{host}/{label}/{trial["job"]}/{trial["trial_id"]}'
            for row in trial['files']:
                source=Path(trial['path'])/row['path']; relative=Path(row['path'])
                if relative.is_absolute() or '..' in relative.parts: raise RuntimeError('Unsafe relative path')
                if source.is_symlink():
                    excluded.append({'source':str(source),'reason':'SYMLINK_NOT_DEREFERENCED'}); continue
                if source.name in {'.env','id_rsa','id_ed25519','credentials'}:
                    excluded.append({'source':str(source),'reason':'CREDENTIAL_FILE'}); continue
                before=source.stat()
                if before.st_size!=row['bytes'] or before.st_mtime_ns!=row['mtime_ns']:
                    changes.append({'source':str(source),'reason':'CHANGED_SINCE_INVENTORY','snapshot_bytes':before.st_size})
                if os.statvfs(root).f_bavail*os.statvfs(root).f_frsize<10*1024**3: raise RuntimeError('Archive disk reserve reached')
                info=archive.gettarinfo(str(source),arcname=prefix+'/'+row['path']); info.size=before.st_size
                with source.open('rb') as stream:
                    reader=HashedReader(stream,before.st_size); archive.addfile(info,reader)
                if row['path']=='result.json' and trial.get('result_sha256'):
                    assert reader.raw.hexdigest()==trial['result_sha256'],'Result changed: '+str(source)
                item={'path':info.name,'bytes':before.st_size,'source_sha256':reader.raw.hexdigest(),'archive_sha256':reader.exported.hexdigest(),'secret_redactions':reader.redactions}
                files_manifest.append(item)
                if reader.redactions: redacted.append({'path':info.name,'count':reader.redactions})
                after=source.stat()
                if after.st_size!=before.st_size or after.st_mtime_ns!=before.st_mtime_ns: changes.append({'source':str(source),'reason':'CHANGED_WHILE_READING','snapshot_bytes':before.st_size})
                done+=before.st_size
                if time.monotonic()-last>=15:
                    state={'observed_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'status':'PACKAGING','host':host,'trials_started':index,'trial_count':len(trials),'bytes_read':done,'inventory_bytes':total,'files_archived':len(files_manifest),'elapsed_seconds':round(time.monotonic()-started,1)}
                    (root/'EXPORT_STATUS.json').write_bytes(json_bytes(state)); print(json.dumps(state),flush=True); last=time.monotonic()
            trial['archive_prefix']=prefix
        manifest={'host':host,'created_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'source_inventory_observed_at':inventory['observed_at'],'scope':inventory['scope'],'trials':trials,'files':files_manifest,'credential_redactions':redacted,'source_changes':changes,'excluded':excluded,'excluded_non_model':inventory['excluded_non_model']}
        encoded,_=scrub(json_bytes(manifest)); header=tarfile.TarInfo(f'host{host}/MANIFEST.json'); header.size=len(encoded); archive.addfile(header,io.BytesIO(encoded))
    temporary.rename(final)
    h=hashlib.sha256()
    with final.open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''): h.update(block)
    state={'observed_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'status':'ARCHIVE_COMPLETE','host':host,'archive':str(final),'archive_bytes':final.stat().st_size,'archive_sha256':h.hexdigest(),'trial_count':len(trials),'terminal_trials':len(inventory['trials'])-sum(bool(t.get('snapshot_only')) for t in trials),'unfinished_snapshots':sum(bool(t.get('snapshot_only')) for t in trials),'by_label':dict(collections.Counter(t['export_model_label'] for t in trials)),'files_archived':len(files_manifest),'source_bytes':done,'credential_redactions':redacted,'source_changes':changes,'excluded':excluded,'elapsed_seconds':round(time.monotonic()-started,1)}
    (root/'EXPORT_STATUS.json').write_bytes(json_bytes(state)); print(json.dumps(state),flush=True)
    concise=[{k:v for k,v in t.items() if k not in {'files','symlinks','exception'}} for t in trials]
    (root/'TRIAL_INDEX.json').write_bytes(json_bytes(concise))

if __name__=='__main__': main(sys.argv[1])
