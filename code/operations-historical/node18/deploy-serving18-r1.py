"""Rebuild a local serving venv from hashed existing packages; never download weights."""
import hashlib
import json
from pathlib import Path
import os
import subprocess
import time

R=Path('/ssd/chenkeyi/qwen35-sft-772-20261101')
S=Path('/data/chenkeyi/qwen35-sft-772-20261101/staging/serving17-r1')
P=Path('/data/chenkeyi/qwen35-sft-772-20261101/provenance')
T=R/'env/serve-new11-r1.staging'
D=R/'env/serve-new11-r1'


def sha(path):
    h=hashlib.sha256()
    with path.open('rb')as stream:
        for block in iter(lambda:stream.read(8*1024*1024),b''):h.update(block)
    return h.hexdigest()


def main():
    if D.exists():raise FileExistsError('Existing serving runtime preserved')
    while not (S/'TRANSFER_MANIFEST.json').exists():time.sleep(15)
    manifest=json.loads((S/'TRANSFER_MANIFEST.json').read_text())
    base=R/'assets/source17-r1/python/bin/python3.11'
    if not T.exists():subprocess.run([str(base),'-m','venv','--without-pip',str(T)],check=True)
    target=T/'lib/python3.11/site-packages'
    subprocess.run(['rsync','-a',str(S/'site-packages')+'/',str(target)+'/'],check=True)
    for row in manifest['files']:
        path=target/row['path']
        if 'link'in row:
            assert path.is_symlink()and str(path.readlink())==row['link']
            assert path.resolve().is_relative_to(T.resolve()),'Serving link escapes local deployment'
        else:
            assert path.stat().st_size==row['bytes']and sha(path)==row['sha256'],row['path']
    original=target/'sglang/srt/entrypoints/openai/serving_chat.py'
    assert sha(original)=='082921f16a712e2a01518756f692f16d514067dec10c893c59831c12fa831a55'
    patched=P/'SERVING_CHAT_CANONICAL_SCHEMA.py'
    assert sha(patched)=='b521132c6332a5a5796f2aad27e0837ebb376afcfddd1940415328f788821dfd'
    original.write_bytes(patched.read_bytes())
    compile(original.read_text(),str(original),'exec')
    os.rename(T,D)
    # The Python binary points to the local standalone interpreter, not node17's venv.
    code='''import json,importlib.metadata as m,sys,torch
from transformers import AutoTokenizer,AutoProcessor
import sglang
print(json.dumps(dict(python=sys.executable,torch=torch.__version__,cuda=torch.version.cuda,sglang=m.version('sglang'),transformers=m.version('transformers'),cuda_context_created=torch.cuda.is_initialized())))
'''
    result=subprocess.run([str(D/'bin/python'),'-c',code],capture_output=True,text=True,check=True)
    proof=dict(passed=True,package_records=len(manifest['files']),package_bytes=manifest['regular_bytes'],
        source_manifest_sha256=sha(S/'TRANSFER_MANIFEST.json'),
        patched_native_serving_chat_sha256=sha(D/'lib/python3.11/site-packages/sglang/srt/entrypoints/openai/serving_chat.py'),
        runtime_import=json.loads(result.stdout.strip().splitlines()[-1]),
        actual_gpu_cold_load_and_tool_protocol_acceptance_pending=True,
        original17_environment_unchanged=True)
    p=R/'checks/ISOLATED_SERVING18_DEPLOYMENT_R1.json';p.write_text(json.dumps(proof,indent=2)+'\n')
    print(json.dumps(proof),flush=True)


if __name__=='__main__':main()
