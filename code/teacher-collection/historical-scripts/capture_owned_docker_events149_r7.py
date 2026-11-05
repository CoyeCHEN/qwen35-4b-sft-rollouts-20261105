"""Native Docker event evidence for this campaign only; no mutation or dispatch."""
import datetime
import fcntl
import json
import subprocess
from pathlib import Path

R=Path('/home/chenkeyi/.local/share/harbor-rsi/qwen35-new-cf500-tmax500-20261029')
lock=(R/'checks/owned-docker-events149-r7.lock').open('a')
fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
engine=subprocess.run(['docker','info','--format','{{.ID}}'],check=True,text=True,capture_output=True).stdout.strip()
if engine!='c6e16cdf-e878-4cc5-84c8-78a56c54b5c5':raise ValueError('149 Engine identity changed')
started=datetime.datetime.now(datetime.timezone.utc).isoformat()
state=dict(status='READ_ONLY_NATIVE_OWNED_CONTAINER_EVENT_CAPTURE',started_at=started,engine_id=engine,
    historical_ring_buffer_is_not_complete_history=True,model_calls=0,task_dispatches=0)
(R/'checks/owned-docker-events149-r7.json').write_text(json.dumps(state,indent=2))
process=subprocess.Popen(['docker','events','--since',started,'--filter','type=container',
    '--filter','event=create','--filter','event=destroy','--format','{{json .}}'],stdout=subprocess.PIPE,text=True)
prefixes=('cftmaxstreamr420261030-','cftmaxresidentbufferr120261030-',
    'cftmaxinfraacceptancer720261030-','rsi-tmax-infra-recovery-r7-')
for line in process.stdout:
    event=json.loads(line);attributes=event.get('Actor',{}).get('Attributes',{});name=attributes.get('name','')
    if not name.startswith(prefixes):continue
    out=dict(observed_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),engine_id=engine,
        action=event.get('Action'),time=event.get('time'),time_nano=event.get('timeNano'),
        container_id=event.get('id') or event.get('Actor',{}).get('ID'),name=name,
        identity=attributes.get('io.harbor.remote-docker.identity'),
        native_role_hint='LEGACY_ZERO_MODEL_RESIDENT_PRECHECK' if name.startswith('cftmaxresidentbuffer') else
            'LEGACY_ZERO_MODEL_ORIGINAL_CONTEXT_ACCEPTANCE' if name.startswith(('cftmaxinfraacceptance','rsi-tmax-infra-recovery')) else
            'ORIGINAL_R5_NATIVE_SCOPE; classify with immutable native TrialConfig')
    with (R/'checks/owned-docker-events149-r7.jsonl').open('a') as stream:stream.write(json.dumps(out)+'\n')
raise RuntimeError('Native Docker event stream ended; inspect before restarting')
