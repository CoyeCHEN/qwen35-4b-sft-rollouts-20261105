"""Native lossless pack/unpack and full SHA validation on an already closed Recorder."""
from pathlib import Path
import hashlib,json,subprocess,time
from harbor_remote_docker.transport import unpack
from foundation.rollouts.export import RolloutView
R=Path('/ssd/chenkeyi/qwen35-sft-772-20261101')
REMOTE='/home/chenkeyi/.local/share/harbor-rsi/qwen35-new772-tb21-20261101'
def sha(p):
 h=hashlib.sha256()
 with p.open('rb')as f:
  for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
 return h.hexdigest()
def main():
 ssh=['/usr/bin/ssh','-F',str(R/'control-ssh/formal-engine149-r1.conf'),'127.0.0.1']
 program="""from pathlib import Path
import json,hashlib,time
from harbor_remote_docker.transport import pack
r=Path(REMOTE)
source=r/'recovery/e3-controller-oom-20261102-r1/chess-best-move'
closed=source/'ORIGINAL_ORPHAN_AGENT_CLOSED_AND_ARCHIVED.json';assert closed.exists()
target=r/'controller18-network-probe-r1/closed-chess-native.tar';assert not target.exists()
begin=time.monotonic();pack(source/'raw-agent',target,contents=True)
h=hashlib.sha256()
with target.open('rb')as f:
 for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
print(json.dumps(dict(tar=str(target),bytes=target.stat().st_size,sha256=h.hexdigest(),pack_seconds=time.monotonic()-begin,closure_manifest=json.loads(closed.read_text()),closure_manifest_sha256=hashlib.sha256(closed.read_bytes()).hexdigest())))
""".replace('REMOTE',repr(REMOTE))
 x=subprocess.run(ssh+['/home/chenkeyi/.local/share/harbor-rsi/qwen35-m1-m2-tb21-20261026/venv/bin/python -'],input=program,capture_output=True,text=True,check=True,timeout=180)
 expected=json.loads(x.stdout);out=R/'formal-controller18-native-recorder-probe-r1';out.mkdir();archive=out/'closed-chess-native.tar'
 start=time.monotonic()
 with archive.open('xb')as f:subprocess.run(ssh+['cat '+expected['tar']],stdout=f,stderr=subprocess.PIPE,check=True,timeout=600)
 transfer_seconds=time.monotonic()-start;assert archive.stat().st_size==expected['bytes']and sha(archive)==expected['sha256']
 raw=out/'raw-agent';begin=time.monotonic();unpack(archive,raw);unpack_seconds=time.monotonic()-begin
 files=expected['closure_manifest']['files']
 for v in files:assert (raw/v['path']).stat().st_size==v['bytes']and sha(raw/v['path'])==v['sha256'],v['path']
 root=raw/'openharness-rollout';validation=RolloutView.open(root).validate();assert validation['complete']
 value=dict(passed=True,at=time.time(),kind='REAL_CLOSED_RECORDER_NATIVE_SSH_COMPRESSION_PACK_UNPACK_SHA_ACCEPTANCE',
  source_node='149',destination_node='18',bytes=expected['bytes'],raw_content_bytes=sum(x['bytes']for x in files),files=len(files),
  sha256=expected['sha256'],pack_seconds=expected['pack_seconds'],transfer_seconds=transfer_seconds,unpack_seconds=unpack_seconds,
  native_recorder_validation=validation,source_closure_manifest_sha256=expected['closure_manifest_sha256'],
  original_event_sha256=next(x['sha256']for x in files if x['path']=='openharness-rollout/events.jsonl'),
  old_original_files_kept=True,no_new_model_or_task_attempt=True,aborted_original_not_counted_as_success=True,
  ssh_compression='yes',source_sha256=sha(Path(__file__)),actual_eight_way_timeout_guarantee_claimed=False)
 p=R/'checks/FORMAL_CONTROLLER18_REAL_RECORDER_TRANSFER_ACCEPTANCE_R1.json';assert not p.exists();p.write_text(json.dumps(value,indent=2)+'\n');print(json.dumps(value))
if __name__=='__main__':main()
