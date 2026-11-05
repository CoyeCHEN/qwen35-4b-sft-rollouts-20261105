"""Cold native SGLang + installed OpenHarness CLI acceptance, separate from Harbor scoring."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time
import urllib.request
import uuid

R=Path('/ssd/chenkeyi/qwen35-sft-772-20261101')
C=Path('/data/chenkeyi/qwen35-sft-772-20261101/control')
HARNESS=R/'env/harness-new11-r1/bin/open-harness'
SERVER_PY=R/'env/serve-new11-r1/bin/python'


def sha(p):
    h=hashlib.sha256()
    with Path(p).open('rb')as f:
        for b in iter(lambda:f.read(8*1024*1024),b''):h.update(b)
    return h.hexdigest()


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--gpu',default='0')
    parser.add_argument('--base-m0',action='store_true')
    parser.add_argument('--extended',action='store_true')
    parser.add_argument('model')
    args=parser.parse_args()
    model=Path(args.model).resolve()
    if args.base_m0:
        assert model==(R/'assets/source17-r1/student-tokenizer').resolve()
        export_sha=None
    else:
        export=model/'HF_EXPORT_COMPLETE.json'
        assert export.exists()and json.loads(export.read_text())['complete_final_hf']
        export_sha=sha(export)
    release=json.loads((R/'checks/NEW11_MODEL_TRANSPORT_RELEASE_R4.json').read_text())
    assert sha(release['wheel'])==release['wheel_sha256']=='3eaeafa4397d5a3284576b8b739a7f79f52311b724fdffc90e8b6f6ccc6e21b4'
    assert sha(SERVER_PY.parent.parent/'lib/python3.11/site-packages/sglang/srt/entrypoints/openai/serving_chat.py')=='b521132c6332a5a5796f2aad27e0837ebb376afcfddd1940415328f788821dfd'
    with (C/('native-protocol-smoke-gpu'+args.gpu+'.lock')).open('a')as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        gpu_rows=subprocess.check_output(['nvidia-smi','--query-gpu=index,uuid,memory.used','--format=csv,noheader,nounits'],text=True).splitlines()
        card=next([v.strip()for v in line.split(',')]for line in gpu_rows if line.split(',')[0].strip()==args.gpu)
        assert int(card[2])<100,'GPU occupied; never preempt an existing process'
        allowed=json.loads((C/'FORMAL_GPU_ALLOCATION.json').read_text())['gpu_uuids']
        if args.base_m0:allowed+=['GPU-9d89f519-51e1-68e2-b522-6e8c1bdc1130']
        assert card[1]in allowed
        identity=time.strftime('%Y%m%dT%H%M%SZ',time.gmtime())+'-'+uuid.uuid4().hex[:6]
        output=R/'smoke'/('native-cli-'+model.name+'-'+identity)
        output.mkdir(parents=True)
        config=json.loads((R/'checks/ORIGINAL_TEACHER_11TOOLS_CONFIG.json').read_text())
        config.update(model=dict(id=str(model),name='Qwen3.5-4B native local',api='openai-completions',
            provider='openai',baseUrl='http://127.0.0.1:18211/v1',reasoning=True,reasoningContent=True,
            input=['text','image'],thinkingLevelMap={'high':'high','max':'high'},
            contextWindow=262144,maxTokens=81920,cost=dict(input=0,output=0,cacheRead=0,cacheWrite=0)),
            thinkingLevel='high',sessionDir=str(output/'sessions'),
            recording=dict(enabled=True,directory=str(output/'recorder')),
            requestOptions=dict(maxTokens=81920,temperature=1.,timeout=120,topP=.95,topK=20,
                minP=0.,presencePenalty=1.5,repetitionPenalty=1.,chatTemplateKwargs={'enable_thinking':True}))
        for key in ['compaction','branchSummary']:config[key]['summaryThinkingLevel']='high'
        (output/'config.json').write_text(json.dumps(config,ensure_ascii=False,indent=2)+'\n')
        prompt='''This is a local protocol smoke. Complete the following small operations in the current directory, check your output, then call finish.\nWrite protocol-check.txt with exactly alpha followed by a newline using write. Use read to inspect the file. Use edit_patch to replace alpha with beta, then read it again to verify beta.\n'''
        if args.extended:
            prompt+='''Also run a short real background bash job which sleeps one second and writes bg-ok.txt containing ready, then use bash_job to inspect that exact job and verify the output. Call trajectory_read once to inspect your actual recorded history. Confirm both files with bash.\n'''
        (output/'instruction.txt').write_text(prompt)
        seed=json.loads((R/'checks/M0_NEW11_NATIVE_SERVING_COMMAND_R2.json').read_text())['command']
        index=seed.index(str(SERVER_PY));server_args=seed[index:]
        server_args[server_args.index('--model-path')+1]=str(model)
        unit='qwen35-native-protocol-'+identity+'.service'
        deployment=[x for x in seed[:index]if not x.startswith(('--unit=','--property=StandardOutput=','--property=StandardError=','--property=Environment=CUDA_VISIBLE_DEVICES='))]
        deployment+=['--unit='+unit,'--property=RuntimeMaxSec=1200',
            '--property=Environment=CUDA_VISIBLE_DEVICES='+card[1],
            '--property=StandardOutput=append:'+str(output/'server.log'),
            '--property=StandardError=append:'+str(output/'server.log')]+server_args
        (output/'SMOKE_SOURCE.json').write_text(json.dumps({name:sha(R/name) for name in ['cold-hf-native-cli-smoke-r2.py','audit-native-cli-smoke-r1.py','audit-native-cli-prefix-r1.py']},indent=2)+'\n')
        (output/'server-command.json').write_text(json.dumps(deployment,indent=2)+'\n')
        try:
            subprocess.run(deployment,check=True,capture_output=True,text=True)
            started=time.monotonic()
            while True:
                try:
                    with urllib.request.urlopen('http://127.0.0.1:18211/health',timeout=5)as response:
                        if response.status==200:break
                except OSError:
                    if time.monotonic()-started>300:raise TimeoutError('Native cold server did not become healthy')
                    time.sleep(2)
            with urllib.request.urlopen('http://127.0.0.1:18211/server_info',timeout=10)as response:
                (output/'server-info.json').write_bytes(response.read())
            env=os.environ|dict(OPENAI_API_KEY='local-node18',TMPDIR=str(R/'tmp'))
            argv=[str(HARNESS),'-p','--mode','json','--config',str(output/'config.json'),
                '--cwd',str(output),'--prompt-file',str(output/'instruction.txt')]
            (output/'cli-command.json').write_text(json.dumps(argv,indent=2)+'\n')
            with(output/'stdout.jsonl').open('x')as stdout,(output/'stderr.log').open('x')as stderr:
                run=subprocess.run(argv,cwd=output,env=env,stdout=stdout,stderr=stderr,timeout=600)
            assert run.returncode==0,'Native CLI returned '+str(run.returncode)
            assert (output/'protocol-check.txt').read_text()=='beta\n'
            if args.extended:assert (output/'bg-ok.txt').read_text().strip()=='ready'
            # The independent audit uses the installed Recorder reader, never stdout claims.
            audit=[str(R/'env/harness-new11-r1/bin/python'),str(R/'audit-native-cli-smoke-r1.py'),str(output)]
            subprocess.run(audit,check=True,cwd=output,env=env,timeout=60)
            verified=json.loads((output/'NATIVE_CLI_AUDIT.json').read_text())
            assert verified['passed']
            proof=dict(passed=True,model=str(model),export_manifest_sha256=export_sha,
                wheel_sha256=release['wheel_sha256'],gpu_uuid=card[1],evidence=str(output),
                audit_sha256=sha(output/'NATIVE_CLI_AUDIT.json'),
                actual_native_agent_closure=True,full_eleven_tool_payload_verified=True,
                scope='HF cold loading and native CLI/Recorder tool protocol; separate from official Harbor Verifier scoring')
            (output/'TOOL_PROTOCOL_SMOKE.json').write_text(json.dumps(proof,indent=2)+'\n')
            if not args.base_m0:
                assert sha(model/'HF_EXPORT_COMPLETE.json')==export_sha
                destination=model/'TOOL_PROTOCOL_SMOKE.json'
                assert not destination.exists()
                destination.write_text(json.dumps(proof,indent=2)+'\n')
            print(json.dumps(proof),flush=True)
        finally:
            subprocess.run(['systemctl','--user','stop',unit],check=True,timeout=60)


if __name__=='__main__':main()
