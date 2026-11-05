"""Export exactly the frozen 54 checkpoint evaluation trials into one ZIP64."""
import collections
import datetime
import hashlib
import json
import os
from pathlib import Path
import time
import zipfile

from package_rollouts import HashedReader, json_bytes, scrub

ROOT=Path('/ssd/chenkeyi/qwen35-checkpoint-54-rollouts-export-20261105')

def main():
    inventory=json.loads((ROOT/'INVENTORY.json').read_text())
    rows=inventory['trials']
    assert len(rows)==54 and len({r['trial_id'] for r in rows})==54
    final=ROOT/'Qwen35-SFT-checkpoint-54-rollouts-20261105.zip'
    temporary=final.with_suffix('.zip.partial')
    if temporary.exists() or final.exists(): raise RuntimeError('Existing package retained')
    manifests=[]; redactions=[]; index=[]; started=time.monotonic(); done=0; last=0
    total=sum(t['bytes'] for t in rows)
    state={'status':'PACKAGING','trials':54,'source_bytes':total}
    with zipfile.ZipFile(temporary,'x',compression=zipfile.ZIP_DEFLATED,compresslevel=1,allowZip64=True) as archive:
        for number,trial in enumerate(rows,1):
            frozen=trial['frozen_audit']; prefix=f'raw/{frozen["label"]}/{frozen["trial"]}'
            assert trial['result_sha256']==frozen['original_result_sha256']
            journal_verified=False
            for item in trial['files']:
                source=Path(trial['path'])/item['path']; stat=source.stat()
                assert stat.st_size==item['bytes'] and stat.st_mtime_ns==item['mtime_ns'],str(source)
                assert not source.is_symlink()
                name=prefix+'/'+item['path']
                with source.open('rb') as stream, archive.open(name,'w',force_zip64=True) as output:
                    reader=HashedReader(stream,stat.st_size)
                    while data:=reader.read(1024*1024):
                        output.write(data); done+=len(data)
                        if time.monotonic()-last>=15:
                            state={'status':'PACKAGING','observed_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'trial_number':number,'trial_count':54,'bytes_read':done,'source_bytes':total,'elapsed_seconds':round(time.monotonic()-started,1)}
                            (ROOT/'EXPORT_STATUS.json').write_bytes(json_bytes(state)); print(json.dumps(state),flush=True);last=time.monotonic()
                digest=reader.raw.hexdigest()
                if item['path']=='result.json': assert digest==frozen['original_result_sha256']
                if item['path'].endswith('openharness-rollout/events.jsonl'):
                    assert digest==frozen['original_journal_sha256']; journal_verified=True
                manifests.append({'path':name,'bytes':stat.st_size,'source_sha256':digest,'archive_sha256':reader.exported.hexdigest(),'credential_redactions':reader.redactions})
                if reader.redactions: redactions.append({'path':name,'count':reader.redactions})
            if trial['journal_files']: assert journal_verified
            index.append({**frozen,'archive_prefix':prefix,'journal_sha_verified':journal_verified,'file_count':len(trial['files']),'source_bytes':trial['bytes']})
        manifest={'trial_count':54,'groups':dict(collections.Counter(t['label'] for t in index)),'files':manifests,'credential_redactions':redactions,'all_source_results_match_frozen_audit':True,'all_available_journals_match_frozen_audit':True,'missing_recorder_is_preserved':True,'source_files_modified':False}
        for name,data in [('TRIAL_INDEX.json',index),('FILE_MANIFEST.json',manifest)]:
            raw,_=scrub(json_bytes(data)); archive.writestr(name,raw)
    temporary.rename(final)
    digest=hashlib.sha256()
    with final.open('rb') as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b''):digest.update(chunk)
    state={'status':'ARCHIVE_COMPLETE','observed_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'trial_count':54,'groups':manifest['groups'],'files':len(manifests),'source_bytes':done,'archive_bytes':final.stat().st_size,'archive_sha256':digest.hexdigest(),'archive':str(final),'credential_redactions':redactions,'elapsed_seconds':round(time.monotonic()-started,1)}
    (ROOT/'EXPORT_STATUS.json').write_bytes(json_bytes(state));(ROOT/'TRIAL_INDEX.json').write_bytes(json_bytes(index));print(json.dumps(state),flush=True)

if __name__=='__main__': main()
