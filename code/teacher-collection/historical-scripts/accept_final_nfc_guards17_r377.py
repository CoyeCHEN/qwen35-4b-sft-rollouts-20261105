"""Prove that the final assembler rejects incomplete or altered metadata."""
import datetime
import hashlib
import json
import os
from pathlib import Path
import subprocess

S=Path('/ssd/chenkeyi/qwen35-new-cf500-tmax500-20261029')
E=Path('/home/chenkeyi/workspace/RSI/runtime-evidence/qwen35-new-cf500-tmax500-20261029')
PY='/home/chenkeyi/workspace/RSI/runtime-evidence/qwen35-length-lf-audit-20261023/.venv/bin/python'
EXPECTED={
 'audit_primary_cache_nfc17_r371.py':'a11544cedda4d4fa800ba0e2f6d31d864fd1f03e81ce3a2b612f423fb06f57bd',
 'assemble_primary_native_cache_nfc17_r372.py':'b5a4e2b778b5408aae0b2c3b76ab29bd3bec9e55c6d24637a7ed176ed5b0de47',
 'assemble_final_corpus_nfc17_r374.py':'ea72d6a0d180992cc2c98450db20959f71bbd57cf0a8fc30a591574dc35e02e3'}


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
 for name,digest in EXPECTED.items():
  path=E/'scripts'/name
  assert sha(path)==digest
  compile(path.read_text(),str(path),'exec')
 env=dict(os.environ,CUDA_VISIBLE_DEVICES='')
 for key in ['DEEPSEEK_API_KEY','OPENAI_API_KEY','GH_TOKEN']:env.pop(key,None)
 cases=[]
 for name,reason in [('partial','A partial snapshot cannot be released as final'),
                     ('changed-member','Frozen final input changed'),
                     ('pending-gate','Final full-campaign gate is incomplete')]:
  inputs=S/'data-final-inputs'/('negative-r377-'+name)
  output=S/'data-frozen'/('negative-r377-'+name)
  inputs.mkdir(parents=True,exist_ok=False)
  assert not output.exists()
  contract=dict(full_campaign_complete=name!='partial',training_started=False,all_files={})
  if name=='changed-member':
   (inputs/'changed.txt').write_text('Explicit negative metadata fixture; no Task or Trial data.\n')
   contract['all_files']['changed.txt']=dict(sha256='intentionally-incorrect')
  if name=='pending-gate':
   p=inputs/'metadata/checks/data-finalization-readiness-r370.json'
   p.parent.mkdir(parents=True)
   p.write_text(json.dumps(dict(status='NOT_READY_COLLECTION_OR_AUDIT_INCOMPLETE',blockers=dict(pending=1))))
   contract['all_files'][str(p.relative_to(inputs))]=dict(sha256=sha(p))
   contract['final_gate_sha256']=sha(p)
  (inputs/'INPUTS.json').write_text(json.dumps(contract))
  result=subprocess.run([PY,str(E/'scripts/assemble_final_corpus_nfc17_r374.py'),'--input-snapshot',str(inputs),'--output',str(output)],env=env,capture_output=True,text=True,timeout=30)
  assert result.returncode!=0 and reason in result.stderr and not output.exists(), name
  (inputs/'EXPECTED_REJECTION.log').write_text(result.stderr)
  cases.append(dict(name=name,input=str(inputs),output_absent=True,returncode=result.returncode,
                    expected_rejection=reason,log_sha256=sha(inputs/'EXPECTED_REJECTION.log')))
 report=dict(passed=True,checked_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
             sources=EXPECTED,negative_cases=cases,teacher_calls=0,new_gpu_processes=0,
             final_positive_full_loader_audit_still_required=True,formal_training_started=False,
             source_sha256=sha(Path(__file__)))
 path=S/'metadata-snapshots/FINAL_NFC_ASSEMBLY_GUARDS_R377.json'
 with path.open('x') as stream:json.dump(report,stream,indent=2)
 print(json.dumps(report))


if __name__=='__main__':main()
