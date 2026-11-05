"""One finite preparation handoff, then exec the accepted native preparer."""
import datetime
import fcntl
import hashlib
import json
import os
from pathlib import Path
import sys
import time

R=Path('/home/chenkeyi/.local/share/harbor-rsi/qwen35-new-cf500-tmax500-20261029')
S=R/'stream/direct17-native-source-r17'


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    S.mkdir(parents=True,exist_ok=True)
    lock=(S/'launcher.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    handoff=R/'checks/direct17-build-preparation-handoff-r17.json'
    progress=R/'checks/direct17-private-builder-r17-launcher.json'
    started=time.monotonic()
    while not handoff.exists():
        value=dict(status='WAITING_FOR_NATIVE_PREPARATION_HANDOFF_ONLY',checked_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),pid=os.getpid(),
            alive_old_preparer_pids=[p for p in [35765,1182007] if Path('/proc/'+str(p)).exists()],teacher_or_verifier_signals=0,model_calls=0)
        temp=progress.with_suffix('.tmp');temp.write_text(json.dumps(value,indent=2));temp.replace(progress)
        if time.monotonic()-started>7200:raise TimeoutError('Keep current native work; no second preparer starts')
        time.sleep(2)
    proof=json.loads(handoff.read_text())
    if proof['status']!='OLD_PREPARERS_NATIVE_WORK_FINISHED_NEW_PRIVATE_BUILDER_AUTHORIZED':raise ValueError('Unaccepted preparation handoff')
    if any(Path('/proc/'+str(p)).exists() for p in proof['retired_preparer_pids']):raise ValueError('Old native preparer still alive')
    script=R/'scripts/prepare_unstarted_direct17_r17.py'
    if sha(script)!=proof['new_preparer_source_sha256'] or sha(R/'scripts/build_tmax_native_oci_ssd17_r17.py')!=proof['new_builder_source_sha256']:
        raise ValueError('Accepted private preparation source changed')
    value=dict(status='EXEC_ACCEPTED_PRIVATE17_NATIVE_PREPARER',checked_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),pid=os.getpid(),
        handoff=str(handoff),handoff_sha256=sha(handoff),preparer_sha256=sha(script),build_config_sha256=sha(R/'configs/campaign-build17-r17.json'),
        teacher_controller_unchanged=True,model_calls=0)
    progress.write_text(json.dumps(value,indent=2));print(json.dumps(value),flush=True)
    os.execve(sys.executable,[sys.executable,str(script)],dict(os.environ))


if __name__=='__main__':
    for key in ['DEEPSEEK_API_KEY','GH_TOKEN','OPENAI_API_KEY']:os.environ.pop(key,None)
    main()
