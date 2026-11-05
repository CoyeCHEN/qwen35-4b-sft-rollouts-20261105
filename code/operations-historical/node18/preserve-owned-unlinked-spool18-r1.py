"""Finite lossless archival of one paused, owned anonymous tool-output spool."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

R = Path('/ssd/chenkeyi/qwen35-sft-772-20261101')
D = R / 'reliability-repair/raw-spool-preservation-r1'
SIZE = 731008204800
REMOTE = r'''
import hashlib,json,os,subprocess,sys,time
CID='fa00a2197ab79dc7f8de3c52b64392aa3b34698f8bbc7a26b9dfd2a82fa56c2c'
EXPECTED=731008204800
NAME='q35rel-raw-preserve-023a8e38-r1'
def event(kind,**data):
    print(json.dumps(dict(kind=kind,at=time.time(),**data)),file=sys.stderr,flush=True)
engine=subprocess.check_output(['docker','info','--format','{{.ID}}'],text=True,timeout=10).strip()
if engine!='c6e16cdf-e878-4cc5-84c8-78a56c54b5c5':raise RuntimeError('Wrong Engine')
row=json.loads(subprocess.check_output(['docker','inspect',CID],text=True,timeout=10))[0]
if row['Config']['Labels'].get('io.harbor.remote-docker.identity')!='17910598c1e446788f30dd0a982fe80e' or not row['State']['Paused']:
    raise RuntimeError('Only the explicitly paused owned abnormal Trial is in scope')
pid=2572058
stat=open('/proc/'+str(pid)+'/stat').read().rsplit(')',1)[1].split()
if stat[19]!='232720914':raise RuntimeError('Source CLI PID changed')
if row['Image']!='sha256:389b9c8247610c2c5be080b1ac00429007c2c69bf57f7f26c79f0f75ba2d5c74':
    raise RuntimeError('Source cached image differs')
# A separate read-only helper holds the file after opening. It is not an Agent,
# does not share the source PID namespace/cgroup, and cannot change its data.
command=['docker','run','--rm','--pull=never','--network=none','--read-only',
 '--log-driver=none','--cpus=2','--memory=128m','--blkio-weight=100',
 '--name',NAME,'--label','rsi.operation=owned-raw-preservation',
 '--label','rsi.source-trial=023a8e38-79db-4b06-87e3-e29f84303650',
 '--mount','type=bind,src=/proc/2572058/fd,dst=/source-fds,readonly',
 '--user=0','--entrypoint=/bin/sh',row['Image'],'-c',
 'set -eu; test "$(stat -Lc %i /source-fds/10)" = 129210020; '
 'test "$(stat -Lc %s /source-fds/10)" = 731008204800; exec cat /source-fds/10']
event('ARCHIVE_SOURCE_ADMITTED',engine_id=engine,container_id=CID,image_id=row['Image'],
 inode=129210020,raw_size=EXPECTED,source_paused=True,helper_name=NAME,
 source_process_or_task_resources_changed=False,raw_data_written_on149=False)
producer=subprocess.Popen(command,stdout=subprocess.PIPE,stderr=sys.stderr)
compressor=subprocess.Popen(['/usr/bin/zstd','-q','--fast=5','-T4','--check','-c'],
 stdin=subprocess.PIPE,stdout=sys.stdout.buffer,stderr=sys.stderr)
digest=hashlib.sha256();count=0;last=time.monotonic();started=last
try:
    while True:
        chunk=producer.stdout.read(4*1024*1024)
        if not chunk:break
        count+=len(chunk)
        if count>EXPECTED:raise RuntimeError('Source grew during frozen archival')
        digest.update(chunk);compressor.stdin.write(chunk)
        if time.monotonic()-last>=15:
            event('ARCHIVE_PROGRESS',raw_bytes=count,expected_raw_bytes=EXPECTED,
                  elapsed_seconds=time.monotonic()-started)
            last=time.monotonic()
    producer.stdout.close();pcode=producer.wait(timeout=60)
    compressor.stdin.close();zcode=compressor.wait(timeout=60)
    if pcode or zcode or count!=EXPECTED:raise RuntimeError(dict(producer=pcode,compressor=zcode,raw_bytes=count))
    event('ARCHIVE_SOURCE_COMPLETE',raw_bytes=count,raw_sha256=digest.hexdigest(),
          elapsed_seconds=time.monotonic()-started,producer_returncode=pcode,
          compressor_returncode=zcode)
finally:
    for process in [producer,compressor]:
        if process.poll()is None:process.terminate()
'''


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def main():
    os.umask(0o077)
    D.mkdir(mode=0o700, parents=True, exist_ok=False)
    space = os.statvfs(D)
    if space.f_bavail*space.f_frsize < SIZE+100*1024**3:
        raise RuntimeError('Independent SSD headroom is insufficient')
    part, errors = D/'owned-tool-stdout.raw.zst.part', D/'source-control.jsonl'
    command = ['/usr/bin/ssh','-F',str(R/'control-ssh/formal-engine149-mux-r2.conf'),
               '-o','ControlMaster=no','-o','ControlPath=none','-o','ControlPersist=no',
               '-o','ConnectTimeout=10','-o','ServerAliveInterval=15',
               '-o','ServerAliveCountMax=3','-p','18449','chenkeyi@127.0.0.1','python3','-u','-']
    with part.open('xb') as output, errors.open('x') as diagnostic:
        result=subprocess.run(command,input=REMOTE.encode(),stdout=output,stderr=diagnostic,timeout=7200)
    events=[]
    for line in errors.read_text().splitlines():
        try:events.append(json.loads(line))
        except json.JSONDecodeError:pass
    complete=[e for e in events if e.get('kind')=='ARCHIVE_SOURCE_COMPLETE']
    if result.returncode or len(complete)!=1:
        raise RuntimeError('Raw archival failed; preserve partial and paused source without claiming completeness')
    original=complete[0]
    decoder=subprocess.Popen(['/usr/bin/zstd','-q','-d','-c',str(part)],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    digest=hashlib.sha256();count=0
    while chunk:=decoder.stdout.read(8*1024*1024):
        count+=len(chunk);digest.update(chunk)
    decoder.stdout.close();dcode=decoder.wait(timeout=60)
    if dcode or count!=SIZE or digest.hexdigest()!=original['raw_sha256']:
        raise RuntimeError('Independent SSD decompression/SHA verification failed; no sealing/unpause')
    target=D/'owned-tool-stdout.raw.zst';part.rename(target)
    value=dict(passed=True,at=time.time(),source_sha256=sha(Path(__file__)),
        source_trial_uuid='023a8e38-79db-4b06-87e3-e29f84303650',
        source_container_id='fa00a2197ab79dc7f8de3c52b64392aa3b34698f8bbc7a26b9dfd2a82fa56c2c',
        source_engine_id='c6e16cdf-e878-4cc5-84c8-78a56c54b5c5',
        source_inode=129210020,source_raw_bytes=count,source_raw_sha256=digest.hexdigest(),
        compressed_path=str(target),compressed_bytes=target.stat().st_size,
        compressed_sha256=sha(target),independent_full_decode_sha_verified=True,
        archived_on_node18_SSD=True,source_raw_or_Recorder_modified=False,
        model_or_Verifier_calls=0,normal_success=False,
        source_unpause_or_native_abort_continuation_still_required=True)
    (D/'RAW_SPOOL_ARCHIVE_ACCEPTANCE_R1.json').write_text(json.dumps(value,indent=2)+'\n')
    print(json.dumps(value),flush=True)


if __name__=='__main__':
    main()
