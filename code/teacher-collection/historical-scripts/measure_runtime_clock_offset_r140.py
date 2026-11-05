"""Record cross-node wall-clock bounds; never adjust clocks or raw timestamps."""
import datetime
import hashlib
import json
from pathlib import Path
import shlex
import subprocess
import time

R=Path('/home/chenkeyi/.local/share/harbor-rsi/qwen35-new-cf500-tmax500-20261029')
p=R/'configs/campaign-deployment17-r15.json';config=json.loads(p.read_text())
code='''import json,time,socket
from pathlib import Path
print(json.dumps(dict(wall_time_ns=time.time_ns(),monotonic_ns=time.monotonic_ns(),hostname=socket.gethostname(),boot_id=Path("/proc/sys/kernel/random/boot_id").read_text().strip())))
'''
rows=[]
for _ in range(3):
    before=time.time_ns();monotonic_before=time.monotonic_ns()
    reply=subprocess.run([*config['ssh'],config['host'],shlex.join([config['python17'],'-c',code])],capture_output=True,text=True,check=True,timeout=15)
    after=time.time_ns();elapsed=time.monotonic_ns()-monotonic_before
    remote=json.loads(reply.stdout)
    rows.append(dict(local149_before_ns=before,local149_after_ns=after,round_trip_seconds=elapsed/1e9,remote17=remote,
        remote_minus149_lower_seconds=(remote['wall_time_ns']-after)/1e9,
        remote_minus149_upper_seconds=(remote['wall_time_ns']-before)/1e9))
lower=max(x['remote_minus149_lower_seconds'] for x in rows);upper=min(x['remote_minus149_upper_seconds'] for x in rows)
value=dict(checked_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),samples=rows,
    consistent_offset_interval_seconds=[lower,upper] if lower<=upper else None,
    interpretation='Remote17 wall time minus controller149 wall time, bounded by local request and response; no external UTC accuracy claim',
    ordering_policy='Native Trial started_at for chronological primary selection; Recorder causal/sequence order within each Trial. Preserve all original node timestamps; do not infer cross-node latency from unadjusted clocks.',
    deployment_config_sha256=hashlib.sha256(p.read_bytes()).hexdigest(),source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    clocks_changed=False,raw_timestamps_rewritten=False,model_calls=0,teacher_or_verifier_signals=0)
with (R/'checks/runtime-clock-offset-r140.json').open('x') as f:json.dump(value,f,indent=2)
print(json.dumps(dict(offset_interval_seconds=value['consistent_offset_interval_seconds'],round_trips=[x['round_trip_seconds'] for x in rows],clocks_changed=False)))
