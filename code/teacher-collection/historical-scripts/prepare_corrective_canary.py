"""Prepare the preregistered corrective canary; never dispatch a teacher."""
import json
from pathlib import Path
import subprocess
import sys

ROOT=Path('/home/chenkeyi/.local/share/harbor-rsi/qwen35-new-cf500-tmax500-20261029')
plan=json.loads((ROOT/'manifests/ORIGINAL_ENVIRONMENT_CORRECTIVE_CANARY_PLAN.json').read_text())
rows=[]
for ident in plan['tmax_second_attempts']+plan['tmax_first_attempts']:
    result=subprocess.run([sys.executable,str(ROOT/'scripts/prepare_tmax_images_v2.py'),
        '--task-id',ident,'--startup-recheck'],check=False)
    file=ROOT/'checks/tmax-environments-runtime-r4'/(ident+'.json')
    receipt=json.loads(file.read_text()) if file.exists() else {}
    item=dict(task_id=ident,preparation_exit_code=result.returncode,status=receipt.get('status','NO_PREPARATION_RECEIPT'),
        receipt=str(file),teacher_attempts=0)
    rows.append(item)
    (ROOT/'checks/corrective-canary-environment-preparation.json').write_text(json.dumps(rows,indent=2))
    print(json.dumps(item),flush=True)
