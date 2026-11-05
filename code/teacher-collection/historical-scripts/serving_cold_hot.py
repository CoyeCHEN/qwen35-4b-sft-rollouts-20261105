"""Bounded existing SGLang cold/hot comparison. No tasks, tools, or training.

Exactly three frozen text contexts; native disk-update API; one TP4 server at a
time. Own process group only. The shared project lock is held for this run.
"""
import contextlib
import argparse
import datetime
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import time
import urllib.request

ROOT = Path('/home/chenkeyi/workspace/RSI/runtime-evidence/qwen35-new-cf500-tmax500-20261029')
RUNS = Path('/ssd/chenkeyi/qwen35-sft-launch-prep-20261025/hot/runs')
MODELS = dict(m1=RUNS/'m1-64k', m2=RUNS/'m2-128k-tb21-10tools-20261026')
UUIDS = ['GPU-bb31693b-95f6-4416-ec41-dd75511c2c59', 'GPU-0db8aea7-b003-06fb-d197-d047c1d67bcb',
         'GPU-d2499600-e80e-4fb8-40ef-b6f0f919d2d8', 'GPU-00f3c3df-16e0-f31f-4066-bdee4c8cdff2']
URL = 'http://127.0.0.1:30130'
parser=argparse.ArgumentParser();parser.add_argument('--retry',action='store_true');parser.add_argument('--cold-m2-only',action='store_true');parser.add_argument('--paired-seeds',action='store_true');args=parser.parse_args()
SUFFIX='-r3' if args.paired_seeds else ('-r2' if args.cold_m2_only else ('-r1' if args.retry else ''))
PROOF = ROOT/f'checks/serving-cold-hot{SUFFIX}.json'
REPORT = dict(started_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
    scope='Three identical reconstructed textual prefixes, TP4/BF16, greedy + three finite sampled seeds; not benchmark Trials',
    historical_token_exact_replay=False, historical_7715_vs_7739='UNRESOLVED; no padding or invented tokens',
    full_raw_logits='NOT_EXPOSED; normalized top-5 logprobs and fixed continuation NLL are compared',
    phases=[], events=[], complete=False)
REPORT['condition']='INDEPENDENT_DETERMINISTIC_DIAGNOSTIC_NOT_HISTORICAL_DEFAULT' if args.paired_seeds else 'HISTORICAL_SERVING_FLAGS'


def save():
    tmp=PROOF.with_suffix('.tmp'); tmp.write_text(json.dumps(REPORT, indent=2)); os.replace(tmp, PROOF)


def query(route, payload=None, timeout=180):
    data=json.dumps(payload).encode() if payload is not None else None
    request=urllib.request.Request(URL+route, data=data, headers={'Content-Type':'application/json'})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.load(response)


def gpu_snapshot():
    result=subprocess.run(['nvidia-smi','--query-compute-apps=gpu_uuid,pid,used_gpu_memory','--format=csv,noheader'],
        check=True,capture_output=True,text=True,timeout=12)
    return result.stdout.strip()


def check_free():
    snapshot=gpu_snapshot()
    if any(line.split(',')[0].strip() in UUIDS for line in snapshot.splitlines()):
        raise RuntimeError('An authorized GPU is already occupied; no launch attempted')
    return snapshot


@contextlib.contextmanager
def server(stage):
    check_free()
    with socket.socket() as sock:
        sock.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
        sock.bind(('127.0.0.1',30130))
    command=[sys.executable,'-m','sglang.launch_server','--model-path',str(MODELS[stage]),
        '--host','127.0.0.1','--port','30130','--tp-size','4','--dp-size','1','--dtype','bfloat16',
        '--context-length','262144','--max-running-requests','4','--mem-fraction-static','0.85',
        '--reasoning-parser','qwen3','--tool-call-parser','qwen3_coder','--disable-custom-all-reduce','--enable-metrics']
    if args.paired_seeds:
        command+=['--enable-deterministic-inference','--sampling-backend','pytorch','--random-seed','42']
    log=(ROOT/f'logs/serving-cold-{stage}{SUFFIX}.log').open('x')
    process=subprocess.Popen(command,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
    REPORT['events'].append(dict(kind='SERVER_STARTED',model=stage,pid=process.pid,command=command));save()
    try:
        deadline=time.monotonic()+720
        while True:
            if process.poll() is not None:raise RuntimeError(f'Own server exited {process.returncode}; inspect its log')
            try:
                query('/get_model_info',timeout=4);break
            except (OSError,ValueError):
                if time.monotonic()>deadline:raise TimeoutError('Bounded own server startup expired')
                time.sleep(3)
        yield process
    finally:
        # Only this Popen-created process group is signalled, never GPU PIDs.
        with contextlib.suppress(ProcessLookupError):
            os.killpg(process.pid,signal.SIGTERM)
        if process.poll() is None:
            try:process.wait(timeout=100)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid,signal.SIGKILL);process.wait(timeout=20)
        log.close()
        REPORT['events'].append(dict(kind='OWN_SERVER_EXITED',pid=process.pid,returncode=process.returncode));save()
        deadline=time.monotonic()+40
        while time.monotonic()<deadline:
            if not any(line.split(',')[0].strip() in UUIDS for line in gpu_snapshot().splitlines()):break
            time.sleep(2)


def prepare_cases():
    from sglang.srt.entrypoints.openai.protocol import ChatCompletionRequest
    from sglang.srt.parser.jinja_template_utils import detect_jinja_template_content_format,process_content_for_template_format
    from transformers import AutoTokenizer
    tokenizer=AutoTokenizer.from_pretrained(MODELS['m1'],local_files_only=True)
    other=AutoTokenizer.from_pretrained(MODELS['m2'],local_files_only=True)
    assert tokenizer.chat_template==other.chat_template
    fmt=detect_jinja_template_content_format(tokenizer.chat_template)
    cases=[]
    for original in json.loads((ROOT/'stage1/serving-frozen-cases.private.json').read_text()):
        request=ChatCompletionRequest.model_validate(original['payload']);messages=[]
        for m in request.messages:
            if m.content is None:m.content=''
            value=process_content_for_template_format(m.model_dump(),fmt,[],[],[],[])
            for call in value.get('tool_calls') or []:
                if isinstance(call['function'].get('arguments'),str):
                    call['function']['arguments']=json.loads(call['function']['arguments'])
            messages.append(value)
        ids=tokenizer.apply_chat_template(messages,tools=[t.model_dump() for t in request.tools],
            add_generation_prompt=True,reasoning_effort=request.reasoning_effort,tokenize=True,return_dict=False)
        assert ids==other.apply_chat_template(messages,tools=[t.model_dump() for t in request.tools],
            add_generation_prompt=True,reasoning_effort=request.reasoning_effort,tokenize=True,return_dict=False)
        thinking=''.join(x.get('thinking','') for x in original['response'].get('content',[]) if x.get('type')=='thinking')
        continuation=tokenizer.encode(thinking,add_special_tokens=False)[:64]
        assert len(continuation)==64
        cases.append(dict(task=original['task'],call_id=original['call_id'],input_ids=ids,continuation=continuation,
            input_sha256=hashlib.sha256(json.dumps(ids).encode()).hexdigest(),historical_input_tokens=original['historical_input_tokens']))
    snapshot=ROOT/'stage1/serving-token-inputs.private.json'
    if snapshot.exists():assert json.loads(snapshot.read_text())==cases
    else:snapshot.write_text(json.dumps(cases))
    REPORT['tokenizer_template_sha256']=hashlib.sha256(tokenizer.chat_template.encode()).hexdigest()
    return cases


def phase(name,cases,process):
    begin=time.monotonic();output=dict(name=name,server_pid=process.pid,server_identity=query('/get_model_info'),
        gpu_processes_before=gpu_snapshot(),cases=[])
    REPORT['phases'].append(output);save()
    for case in cases:
        ids=case['input_ids'];record={k:v for k,v in case.items() if k not in ('input_ids','continuation')}
        record['input_tokens']=len(ids);record['runs']=[];output['cases'].append(record)
        for seed in (None,17,42,73):
            sampling=dict(temperature=0 if seed is None else 1,top_p=1 if seed is None else .95,
                top_k=-1,min_p=0,frequency_penalty=0,presence_penalty=0,repetition_penalty=1,
                ignore_eos=False,max_new_tokens=256 if seed is None else 192)
            if seed is not None:sampling['sampling_seed']=seed
            started=time.monotonic()
            result=query('/generate',dict(input_ids=ids,sampling_params=sampling,return_logprob=True,
                top_logprobs_num=5,return_text_in_logprobs=True,stream=False))
            record['runs'].append(dict(seed=seed,sampling_params=sampling,response=result,seconds=time.monotonic()-started));save()
        result=query('/generate',dict(input_ids=ids+case['continuation'],sampling_params=dict(temperature=0,max_new_tokens=1),
            return_logprob=True,logprob_start_len=len(ids)-1,top_logprobs_num=5,return_text_in_logprobs=True,stream=False))
        probabilities=result['meta_info']['input_token_logprobs'][-64:]
        assert [p[1] for p in probabilities]==case['continuation']
        assert all(p[0] is not None and math.isfinite(p[0]) for p in probabilities)
        record['fixed_continuation']=dict(tokens=case['continuation'],mean_nll=-sum(p[0] for p in probabilities)/64,response=result)
        save()
    output.update(seconds=time.monotonic()-begin,gpu_processes_after=gpu_snapshot());save()


def main():
    with open('/home/chenkeyi/workspace/RSI/runtime-evidence/qwen35-sft-preflight-20261023/runs/training.lock','a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        assert not PROOF.exists(), 'Do not replay an existing diagnostic identity'
        REPORT['gpu_check_before']=check_free();save()
        cases=prepare_cases()
        if args.cold_m2_only:
            previous=ROOT/'checks/serving-cold-hot-r1.json'
            old=json.loads(previous.read_text())
            assert [p['name'] for p in old['phases']]==['m1-cold','m2-hot-from-m1']
            assert all('fixed_continuation' in c and len(c['runs'])==4 for p in old['phases'] for c in p['cases'])
            REPORT['reused_evidence']=dict(path=str(previous),sha256=hashlib.sha256(previous.read_bytes()).hexdigest(),
                phases=['m1-cold','m2-hot-from-m1'],reason='Both completed; only cold M2 was blocked by own port precheck TIME_WAIT')
            with server('m2') as process:phase('m2-cold',cases,process)
            REPORT.update(complete=True,finished_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),gpu_check_after=gpu_snapshot());save()
            return
        with server('m1') as process:
            phase('m1-cold',cases,process)
            result=query('/update_weights_from_disk',dict(model_path=str(MODELS['m2']),load_format='auto',flush_cache=True,
                weight_version='3af1b3821d28b30a90d89c3c29bb086f8fa823d7942567e2758e1d4771a39664'),timeout=360)
            REPORT['native_weight_update_ack']=result;save()
            assert result.get('success') is True
            phase('m2-hot-from-m1',cases,process)
        with server('m2') as process:phase('m2-cold',cases,process)
        REPORT.update(complete=True,finished_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),gpu_check_after=gpu_snapshot());save()


if __name__=='__main__':
    try:main()
    except BaseException as error:
        REPORT.update(error_type=type(error).__name__,error=str(error),complete=False);save();raise
