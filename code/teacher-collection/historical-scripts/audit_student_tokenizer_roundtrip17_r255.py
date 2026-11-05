"""CPU tokenizer/processor checkpoint round-trip; never instantiate a model."""
import os
os.environ.update(CUDA_VISIBLE_DEVICES='', HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1', TOKENIZERS_PARALLELISM='false')
import hashlib
import importlib.metadata
import inspect
import json
from pathlib import Path
import shutil
import subprocess
import sys
import datetime

E=Path('/home/chenkeyi/workspace/RSI/runtime-evidence/qwen35-new-cf500-tmax500-20261029')
S=Path('/ssd/chenkeyi/qwen35-new-cf500-tmax500-20261029')
D=S/'student-protocol-r255'
RESOURCE=S/'student-tokenizer-r155'
sys.path.insert(0,str(E/'sft-code-weight-audit-r3'))
from sft.qwen35 import digest,TEMPLATE_SHA
from llamafactory.hparams import ModelArguments,DataArguments
from llamafactory.model import load_tokenizer
from llamafactory.data import get_template_and_fix_tokenizer
import torch

EXPECTED='027a3f1c30acd5438805f34bb427a99772640beba2a4e5153ada9c90fc259281'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
PROBES=['<br><h3>tool result</h3>','{"path":"/home/user/x","command":"printf \\\"a\\\\nb\\\""}','用户下一轮\n<think>reasoning</think>\n<tool_call>\n{"name":"bash","arguments":{"command":"true"}}\n</tool_call>']


def identity(module):
    tokenizer=module['tokenizer']
    backend=json.loads(tokenizer.backend_tokenizer.to_str());backend.pop('padding',None);backend.pop('truncation',None)
    assert digest(backend)==EXPECTED
    assert digest(tokenizer.chat_template)==TEMPLATE_SHA
    return dict(tokenizer_class=type(tokenizer).__module__+'.'+type(tokenizer).__name__,
        backend_semantics_sha256=digest(backend),template_sha256=digest(tokenizer.chat_template),
        probe_input_ids=[tokenizer.encode(x,add_special_tokens=False) for x in PROBES],
        processor_class=type(module['processor']).__module__+'.'+type(module['processor']).__name__)


def main():
    D.mkdir(exist_ok=False)
    torch.set_num_threads(1)
    assert sha(RESOURCE/'tokenizer_config.json')=='3dd1cee8a0cb8f51800bcb47bd157eeef5bda2d39c85b7569892b9af95170071'
    first=load_tokenizer(ModelArguments(model_name_or_path=str(RESOURCE)))
    get_template_and_fix_tokenizer(first['tokenizer'],DataArguments(template='qwen3_5',enable_thinking=True,preserve_thinking=True))
    before=identity(first)
    checkpoint=D/'simulated-m1-checkpoint';checkpoint.mkdir()
    for name in ['config.json','generation_config.json']:
        if (RESOURCE/name).exists():shutil.copyfile(RESOURCE/name,checkpoint/name)
    first['tokenizer'].save_pretrained(checkpoint)
    first['processor'].save_pretrained(checkpoint)
    reloaded=load_tokenizer(ModelArguments(model_name_or_path=str(checkpoint)))
    get_template_and_fix_tokenizer(reloaded['tokenizer'],DataArguments(template='qwen3_5',enable_thinking=True,preserve_thinking=True))
    after=identity(reloaded)
    assert before['backend_semantics_sha256']==after['backend_semantics_sha256'] and before['probe_input_ids']==after['probe_input_ids'] and before['template_sha256']==after['template_sha256']
    serving='/ssd/chenkeyi/qwen35-m2-eval-20261026/serving-env/bin/python'
    code='''import json,sys,importlib.metadata,hashlib,ast
from pathlib import Path
from transformers import AutoTokenizer
sys.path.insert(0,sys.argv[2])
from sft.qwen35 import digest,TEMPLATE_SHA
t=AutoTokenizer.from_pretrained(sys.argv[1],local_files_only=True,trust_remote_code=True)
b=json.loads(t.backend_tokenizer.to_str());b.pop('padding',None);b.pop('truncation',None)
assert digest(b)==sys.argv[3] and digest(t.chat_template)==TEMPLATE_SHA
package=importlib.metadata.distribution('sglang')
p=next(Path(package.locate_file(x)) for x in package.files if str(x).endswith('/srt/server_args.py'))
source=p.read_text();tree=ast.parse(source)
flags={n.value for n in ast.walk(tree) if isinstance(n,ast.Constant) and isinstance(n.value,str)}
assert {'--tokenizer-path','--reasoning-parser','--tool-call-parser'}<=flags
print(json.dumps(dict(tokenizer_path=sys.argv[1],backend_semantics_sha256=digest(b),template_sha256=digest(t.chat_template),probe_input_ids=[t.encode(x,add_special_tokens=False) for x in json.loads(sys.argv[4])],sglang_version=package.version,native_server_args_source=str(p),native_server_args_source_sha256=hashlib.sha256(p.read_bytes()).hexdigest(),explicit_tokenizer_path_supported=True,server_or_model_started=False)))
'''
    env=dict(os.environ)
    for key in ['DEEPSEEK_API_KEY','OPENAI_API_KEY','GH_TOKEN']:env.pop(key,None)
    reply=subprocess.run([serving,'-c',code,str(RESOURCE),str(E/'sft-code-weight-audit-r3'),EXPECTED,json.dumps(PROBES)],env=env,capture_output=True,text=True,check=True,timeout=90)
    served=json.loads(reply.stdout.strip().splitlines()[-1]);assert served['probe_input_ids']==before['probe_input_ids']
    assert not torch.cuda.is_initialized()
    report=dict(passed=True,checked_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),resource=str(RESOURCE),
        source_manifest_sha256=sha(RESOURCE/'SOURCE_MANIFEST_R155.json'),m1_initial_tokenizer=before,m2_checkpoint_reload_tokenizer=after,
        serving=served,saved_tokenizer_class=json.loads((checkpoint/'tokenizer_config.json').read_text())['tokenizer_class'],
        original_weights_or_configs_modified=False,model_or_optimizer_loaded=False,cuda_initialized=False,training_started=False,
        scope='Tokenizer/processor serialization and installed Serving argument schema only; actual Qwen GPU/long-context acceptance remains required',
        source_sha256=sha(Path(__file__)))
    with (D/'TOKENIZER_CHECKPOINT_SERVING_ACCEPTANCE.json').open('x') as stream:json.dump(report,stream,indent=2)
    print(json.dumps(dict(proof=str(D/'TOKENIZER_CHECKPOINT_SERVING_ACCEPTANCE.json'),passed=True,saved_tokenizer_class=report['saved_tokenizer_class'],model_started=False)))


if __name__=='__main__':main()
