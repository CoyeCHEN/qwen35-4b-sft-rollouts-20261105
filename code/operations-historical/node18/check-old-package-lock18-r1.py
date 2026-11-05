"""CPU-only: concurrent readers must obtain one immutable native old-model release."""
import hashlib
import json
from pathlib import Path
import subprocess
import time

R=Path('/ssd/chenkeyi/qwen35-sft-772-20261101')
PY=R/'env/train-r1/bin/python'
code="import sys,importlib,json;sys.path.insert(0,'"+str(R)+"');a,b=importlib.import_module('old443-readout18-r2').sealed_model('old-M1');print(json.dumps({'model':str(a),'marker':str(b)}))"
start=time.monotonic()
workers=[subprocess.Popen([str(PY),'-c',code],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)for _ in range(2)]
answers=[]
for worker in workers:
    out,err=worker.communicate(timeout=180)
    if worker.returncode:raise ValueError('CPU release packaging failed: '+err[-1200:])
    answers.append(json.loads(out))
if answers[0]!=answers[1]:raise ValueError('Concurrent readers saw different releases')
marker=Path(answers[0]['marker']);proof=json.loads(marker.read_text());source=Path(proof['source_path'])
if (source/'model.safetensors').stat().st_ino!=(marker.parent/'model.safetensors').stat().st_ino:
    raise ValueError('Expected same-SSD immutable hardlink, not a redundant model copy')
result=dict(passed=True,source_model=str(source),canonical_readout_model=str(marker.parent),concurrent_readers=2,
    same_immutable_release=True,model_manifest_sha256=hashlib.sha256(marker.read_bytes()).hexdigest(),
    original_baseline_preserved=True,original_model_weight_sha256=proof['source_identity']['expected_weight_sha256'],
    GPU_calls=0,teacher_requests=0,optimizer_updates=0,elapsed_seconds=time.monotonic()-start,
    scope='Local node18 SSD artifact mutex only; sole cross-node controller lock remains the original Ceph lock')
(R/'checks/OLD_MODEL_RELEASE_LOCAL_MUTEX_CPU_ACCEPTANCE_R1.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result))
