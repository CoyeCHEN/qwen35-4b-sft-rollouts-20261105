"""Measure real uncompressed native SSH artifact transfer on the frozen Engine route."""
from pathlib import Path
import hashlib,json,subprocess,time
R=Path('/ssd/chenkeyi/qwen35-sft-772-20261101');REMOTE='/home/chenkeyi/.local/share/harbor-rsi/qwen35-new772-tb21-20261101/controller18-network-probe-r1/random32m.bin'
def main():
 ssh=['/usr/bin/ssh','-F',str(R/'control-ssh/formal-engine149-r1.conf'),'-oCompression=no','127.0.0.1']
 program="from pathlib import Path;import os,json,hashlib;p=Path("+repr(REMOTE)+");p.parent.mkdir(exist_ok=True);assert not p.exists();p.write_bytes(os.urandom(33554432));p.chmod(0o600);print(json.dumps(dict(bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest())))"
 made=subprocess.run(ssh+['python3 -'],input=program,capture_output=True,text=True,check=True,timeout=30)
 expected=json.loads(made.stdout);out=R/'formal-controller18-network-probe-r1';out.mkdir();target=out/'random32m.bin'
 begin=time.monotonic()
 with target.open('xb')as stream:subprocess.run(ssh+['cat '+REMOTE],stdout=stream,stderr=subprocess.PIPE,check=True,timeout=120)
 elapsed=time.monotonic()-begin
 assert target.stat().st_size==expected['bytes']and hashlib.sha256(target.read_bytes()).hexdigest()==expected['sha256']
 value=dict(passed=True,at=time.time(),scope='Uncompressed32MiB transport measurement, no model/Task dispatch',bytes=expected['bytes'],sha256=expected['sha256'],seconds=elapsed,mebibytes_per_second=32/elapsed,source_node='149',destination_node='18',source_path=REMOTE,destination_path=str(target),engine_id='c6e16cdf-e878-4cc5-84c8-78a56c54b5c5',native_ssh_reverse_route_unchanged=True,workload_timeout_guarantee_claimed=False,source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
 p=R/'checks/FORMAL_CONTROLLER18_NATIVE_TRANSFER_ACCEPTANCE_R1.json';assert not p.exists();p.write_text(json.dumps(value,indent=2)+'\n');print(json.dumps(value))
if __name__=='__main__':main()
