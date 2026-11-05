"""Finite SHA-verified archive of immutable final caches; no Recorder relocation."""
import fcntl
import hashlib
import json
from pathlib import Path
import os
import subprocess
import time

S=Path('/ssd/chenkeyi/qwen35-sft-772-20261101/frozen-data-772-r3')
B=Path('/data/chenkeyi/qwen35-sft-772-20261101')
T=B/'frozen-data-772-r3.partial'
D=B/'frozen-data-772-r3'


def sha(p):
    h=hashlib.sha256()
    with p.open('rb')as f:
        for block in iter(lambda:f.read(8*1024*1024),b''):h.update(block)
    return h.hexdigest()


def main():
    with (B/'control/frozen-data-archive.lock').open('a')as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if D.exists():raise FileExistsError('Existing sealed final archive preserved')
        T.mkdir(exist_ok=True)
        expected=[]
        for p in sorted(S.rglob('*')):
            if p.is_symlink():raise ValueError('Frozen final artifact is an external symlink')
            if p.is_file():expected.append(dict(path=str(p.relative_to(S)),bytes=p.stat().st_size,sha256=sha(p)))
        subprocess.run(['rsync','-a',str(S)+'/',str(T)+'/'],check=True)
        for row in expected:
            p=T/row['path'];assert p.stat().st_size==row['bytes']and sha(p)==row['sha256'],row['path']
        report=dict(complete=True,files=len(expected),bytes=sum(x['bytes']for x in expected),
            created_at=time.time(),source=str(S),source_preserved=True,records=expected)
        (T/'ARCHIVE_SHA_SEAL.json').write_text(json.dumps(report,indent=2)+'\n')
        os.rename(T,D)
        print(json.dumps(dict(complete=True,path=str(D),bytes=report['bytes'],files=report['files'],seal_sha256=sha(D/'ARCHIVE_SHA_SEAL.json'))),flush=True)


if __name__=='__main__':main()
