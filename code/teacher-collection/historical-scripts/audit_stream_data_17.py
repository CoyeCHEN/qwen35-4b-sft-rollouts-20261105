"""One immutable real-trial CPU projection/Loader/parser audit; no model service."""
import fcntl,hashlib,json,os,shutil,subprocess,sys
from pathlib import Path
from uuid import UUID
E=Path('/home/chenkeyi/workspace/RSI/runtime-evidence/qwen35-new-cf500-tmax500-20261029')
ident=str(UUID(sys.argv[1]));R=E/'validation/stream-r3'/ident
assert R.is_dir() and len(list((R/'sources/canary-calls-all').glob('*.jsonl.gz')))==1
lock=(R/'native-cpu-audit.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
for name in ['DEEPSEEK_API_KEY','GH_TOKEN']:os.environ.pop(name,None)
os.environ.update(CUDA_VISIBLE_DEVICES='',QWEN35_MODEL_PATH='/data/models/Qwen/Qwen3.5-4B',HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',
 PYTHONPATH=str(E/'sft-code-weight-audit-r3'),CF_TMAX_AUDIT_ROOT=str(R))
for name in ['checks','logs','derived']:(R/name).mkdir(exist_ok=True)
code=E/'sft-code-weight-audit-r3'
if not (R/'sft-code').exists():(R/'sft-code').symlink_to(code,target_is_directory=True)
identity=E/'checks/qwen-tokenizer-processor-identity.json'
if not (R/'checks/qwen-tokenizer-processor-identity.json').exists():shutil.copyfile(identity,R/'checks/qwen-tokenizer-processor-identity.json')
proof=R/'checks/STUDENT_AUDIT_TRIALS_ALL.json'
if proof.exists():print(proof);raise SystemExit
py='/home/chenkeyi/workspace/RSI/runtime-evidence/qwen35-length-lf-audit-20261023/.venv/bin/python'
serving='/ssd/chenkeyi/qwen35-m2-eval-20261026/serving-env/bin/python'
stages=[(py,'audit_canary_qwen_v4.py'),(py,'audit_canary_loader_v5.py'),(serving,'audit_qwen_serving_final.py'),(py,'package_first_student_evidence.py')]
for interpreter,name in stages:
 with (R/'logs'/(name+'.log')).open('a') as log:
  subprocess.run([interpreter,str(E/'scripts'/name),'--all-canaries'],stdout=log,stderr=subprocess.STDOUT,check=True,timeout=12000)
print(proof)
