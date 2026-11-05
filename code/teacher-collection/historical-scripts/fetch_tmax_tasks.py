"""Fetch one pinned public task archive on the authorized controller, no API key."""
import datetime
import hashlib
import json
import os
from pathlib import Path
import time
import urllib.request

ROOT=Path('/home/chenkeyi/.local/share/harbor-rsi/qwen35-new-cf500-tmax500-20261029')
DEST=ROOT/'sources/tmax';DEST.mkdir(parents=True,exist_ok=True)
EXPECTED='59e2efd8785d68214f4f8f61c383ef806dff9778d965af5d13cf45f02e3dc106'
SIZE=452939754
REV='e3ded940596cc611c9815684ba51a7e8ee0cffc9'
URL='https://hf-mirror.com/datasets/allenai/TMax-15K/resolve/'+REV+'/tasks.zip?download=true'
target=DEST/'tasks.zip';partial=DEST/'tasks.zip.partial'


def digest(path):
    with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()


def record(**kwargs):
    result=dict(checked_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),dataset='allenai/TMax-15K',
        revision=REV,expected_sha256=EXPECTED,expected_bytes=SIZE,source='Pinned official LFS content through mirror',
        original_official_resolve='Network/SSL unavailable in bounded probes',local_large_copy=False,**kwargs)
    out=ROOT/'checks/tmax-download.json';tmp=out.with_suffix('.tmp');tmp.write_text(json.dumps(result,indent=2));os.replace(tmp,out)
    print(json.dumps(result),flush=True)


if target.exists():
    assert target.stat().st_size==SIZE and digest(target)==EXPECTED
    record(status='COMPLETE_VERIFIED_CACHE_REUSED',path=str(target),bytes=SIZE)
else:
    offset=partial.stat().st_size if partial.exists() else 0
    assert 0<=offset<=SIZE
    if offset<SIZE:
        request=urllib.request.Request(URL,headers={'Range':'bytes='+str(offset)+'-'} if offset else {})
        with urllib.request.urlopen(request,timeout=60) as response:
            if offset:
                assert response.status==206 and response.headers.get('Content-Range','').startswith('bytes '+str(offset)+'-')
            with partial.open('ab' if offset else 'xb') as stream:
                last=time.monotonic()
                while chunk:=response.read(1024*1024):
                    stream.write(chunk);offset+=len(chunk);assert offset<=SIZE
                    if time.monotonic()-last>10:
                        stream.flush();record(status='DOWNLOADING',bytes=offset,path=str(partial));last=time.monotonic()
                stream.flush();os.fsync(stream.fileno())
    assert partial.stat().st_size==SIZE, 'Incomplete download preserved for bounded explicit resume'
    assert digest(partial)==EXPECTED, 'Content SHA mismatch; preserve source, never use'
    os.replace(partial,target)
    record(status='COMPLETE_VERIFIED',bytes=SIZE,path=str(target))
