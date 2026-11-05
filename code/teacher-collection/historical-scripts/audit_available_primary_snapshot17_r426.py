"""Finite CPU audit of a new partial snapshot, never a final corpus release."""
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

S=Path('/ssd/chenkeyi/qwen35-new-cf500-tmax500-20261029')
E=Path('/home/chenkeyi/workspace/RSI/runtime-evidence/qwen35-new-cf500-tmax500-20261029')
PY='/home/chenkeyi/workspace/RSI/runtime-evidence/qwen35-length-lf-audit-20261023/.venv/bin/python'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
 lock=(S/'metadata-snapshots/partial-primary-cache-audit-r426.lock').open('a')
 fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 inputs=S/'data-primary-snapshots/r425'
 output=S/'data-corpus-snapshots/r426'
 assert not output.exists(), 'Observe the existing finite partial audit; never replay'
 contract=json.loads((inputs/'INPUTS.json').read_text())
 assert contract['full_campaign_complete'] is False and contract['training_started'] is False
 for name,value in contract['files'].items():assert sha(inputs/name)==value['sha256']
 for key in ['DEEPSEEK_API_KEY','OPENAI_API_KEY','GH_TOKEN']:os.environ.pop(key,None)
 os.environ.update(CUDA_VISIBLE_DEVICES='',QWEN35_MODEL_PATH=str(S/'student-tokenizer-r155'),
  HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',TOKENIZERS_PARALLELISM='false',OMP_NUM_THREADS='1',
  TMPDIR=str(S/'tmp'),HF_DATASETS_CACHE=str(S/'data-corpus-snapshots/r426-hf-cache'),
  PYTHONPATH=str(E/'sft-code-nfc-prefix-r4'))
 sys.path.insert(0,str(E/'sft-code-nfc-prefix-r4'))
 token=E/'scripts/audit_primary_cache_nfc17_r371.py'
 native=E/'scripts/assemble_primary_native_cache_nfc17_r372.py'
 assert sha(token)=='a11544cedda4d4fa800ba0e2f6d31d864fd1f03e81ce3a2b612f423fb06f57bd'
 assert sha(native)=='b5a4e2b778b5408aae0b2c3b76ab29bd3bec9e55c6d24637a7ed176ed5b0de47'
 policy=S/'metadata-snapshots/ENCODER_NFC_INPUT_POLICY_R364.json'
 assert sha(policy)=='e22f1e718464adc9b7a1f04323f8901ec1a03235641b31d5e0b64d4346530900'
 spec=importlib.util.spec_from_file_location('nfc_primary_token_audit',token)
 module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
 module.D=inputs;module.audit()
 subprocess.run([PY,str(native),'--input-snapshot',str(inputs),'--output',str(output)],check=True,timeout=37000)
 report=json.loads((output/'DATA_AUDIT_PARTIAL.json').read_text())
 assert report['full_campaign_complete'] is False and report['formal_corpus_release'] is False
 print(json.dumps(dict(passed=True,report=str(output/'DATA_AUDIT_PARTIAL.json'),sha256=sha(output/'DATA_AUDIT_PARTIAL.json'),
  qualified_primary_tasks={pool:value['qualified_independent_tasks'] for pool,value in report['pools'].items()},
  formal_release=False,model_calls=0,training_started=False)))


if __name__=='__main__':main()
