"""Prepare all current frozen TMax tasks under the original runtime contract.

Calls the established single-task environment preparer, with no model calls.
Original receipts and every attempted task identity remain intact.
"""
from collections import Counter
import json
from pathlib import Path
import shutil
import subprocess
import sys

ROOT=Path('/home/chenkeyi/.local/share/harbor-rsi/qwen35-new-cf500-tmax500-20261029')
rows=list(map(json.loads,(ROOT/'manifests/TMAX_RUNTIME_CANDIDATES_V2.jsonl').open()))
assert len(rows)==500 and len({r['task_id'] for r in rows})==500
counts=Counter();observed=[]
for row in sorted(rows,key=lambda x:x['task_id']):
    if shutil.disk_usage(ROOT).free<100*1024**3:
        (ROOT/'checks/tmax-original-runtime-pool-preparation.json').write_text(json.dumps(dict(
            status='WAITING_FOR_DISK_HEADROOM',planned_tasks=500,counts=dict(counts),observed=observed,
            next_task_id=row['task_id'],model_calls=0),indent=2))
        break
    result=subprocess.run([sys.executable,str(ROOT/'scripts/prepare_tmax_images_v2.py'),
        '--task-id',row['task_id'],'--startup-recheck'],check=False)
    file=ROOT/'checks/tmax-environments-runtime-r4'/(row['task_id']+'.json')
    item=json.loads(file.read_text()) if file.exists() else {}
    status=item.get('status','NO_PREPARATION_RECEIPT');counts[status]+=1
    observed.append(dict(task_id=row['task_id'],status=status,preparation_returncode=result.returncode,receipt=str(file)))
    (ROOT/'checks/tmax-original-runtime-pool-preparation.json').write_text(json.dumps(dict(
        status='PREPARING_ORIGINAL_RUNTIME',planned_tasks=500,counts=dict(counts),observed_tasks=len(observed),observed=observed,
        model_calls=0,teacher_attempts=0,original_agent_and_verifier_deadlines_unchanged=True),indent=2))
    print(json.dumps(observed[-1]),flush=True)
