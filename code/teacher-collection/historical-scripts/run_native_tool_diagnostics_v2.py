"""Two sequential, bounded native Harbor setup/exec/cleanup diagnostics, no agent run."""
import asyncio
import hashlib
import json
import os
from pathlib import Path
import shlex
from uuid import uuid4

from harbor.agents.installed.open_harness import OpenHarnessAgent
from harbor.models.task.task import Task
from harbor.models.trial.paths import TrialPaths
from harbor_remote_docker import RemoteDockerEnvironment

ROOT=Path('/home/chenkeyi/.local/share/harbor-rsi/qwen35-new-cf500-tmax500-20261029')


async def main():
    base=json.loads((ROOT/'configs/canary-first2.json').read_text())
    rows={r['task_id']:r for r in map(json.loads,(ROOT/'manifests/CALIBFORGE_500_TASKS.jsonl').open())}
    cases=[('calibforge',Path(rows['system-administration_20260430_081156_006']['source_path'])),
        ('tmax',ROOT/'prepared-tasks/tmax/task_001234_e40accec')]
    reports=[]
    for pool,path in cases:
        out=ROOT/'diagnostics/native-tools-v2'/pool;out.mkdir(parents=True,exist_ok=False)
        task=Task(path);paths=TrialPaths(out)
        for directory in [paths.agent_dir,paths.verifier_dir,paths.artifacts_dir]:directory.mkdir(parents=True,exist_ok=True)
        options=dict(base['environment']['kwargs']);options['project_namespace']='cftmaxnativeprobe220261030'
        environment=RemoteDockerEnvironment(environment_dir=task.paths.environment_dir,
            environment_name='native-tool-probe-'+pool,session_id=uuid4().hex,trial_paths=paths,
            task_env_config=task.config.environment,**options)
        environment.configure_agent_runtime(writable=True,executable=True)
        agent=OpenHarnessAgent(logs_dir=paths.agent_dir,model_name='deepseek/deepseek-flash',**base['agents'][0]['kwargs'])
        report=dict(pool=pool,task_id=path.name,status='PREPARING_NATIVE_TOOL_DIAGNOSTIC',
            model_calls=0,teacher_attempts=0,official_verifier_invoked=False,task_path=str(path),
            wheel_sha256=base['agents'][0]['kwargs']['wheel_sha256'],
            probe_source_sha256=hashlib.sha256((ROOT/'scripts/native_tool_functional_probe.py').read_bytes()).hexdigest(),
            source_task_toml_sha256=hashlib.sha256((path/'task.toml').read_bytes()).hexdigest(),
            scoped_ssh_config_sha256=hashlib.sha256((ROOT/'ssh/client.conf').read_bytes()).hexdigest())
        try:
            await asyncio.wait_for(environment.start(force_build=False),timeout=180)
            await asyncio.wait_for(agent.setup(environment),timeout=600)
            for source,target in [(ROOT/'scripts/native_tool_functional_probe.py','/tmp/rsi-native-tool-probe.py'),
                (ROOT/'configs/teacher-native-11tools.json','/tmp/rsi-teacher-contract.json'),
                (ROOT/'manifests/TEACHER_CONTRACT_CANDIDATE.json','/tmp/rsi-teacher-manifest.json')]:
                await environment.upload_file(source,target)
            command=shlex.join([agent.lifecycle_interpreter,'/tmp/rsi-native-tool-probe.py',
                '/tmp/rsi-teacher-contract.json','/tmp/rsi-teacher-manifest.json'])
            result=await environment.exec(command,cwd='/tmp',timeout_sec=120)
            (out/'functional-stdout.txt').write_text(result.stdout or '')
            (out/'functional-stderr.txt').write_text(result.stderr or '')
            report['functional_returncode']=result.return_code
            await environment.download_dir('/logs/agent',paths.agent_dir)
            if result.return_code:raise RuntimeError('Native functional probe failed; complete diagnostics retained')
            proof=paths.agent_dir/'native-capability/proof.json'
            report.update(status='NATIVE_SDK_FUNCTIONAL_CHECKS_PASSED',proof=str(proof),
                proof_sha256=hashlib.sha256(proof.read_bytes()).hexdigest(),functional_evidence=json.loads(proof.read_text()))
        except Exception as error:
            report.update(status='NATIVE_TOOL_DIAGNOSTIC_FAILED',error_type=type(error).__name__,error=str(error)[:800])
        finally:
            try:
                await environment.stop(delete=True);report['native_cleanup_confirmed']=True
            except Exception as error:
                report.update(native_cleanup_confirmed=False,cleanup_error_type=type(error).__name__)
        (out/'diagnostic.json').write_text(json.dumps(report,indent=2));reports.append(report)
        print(json.dumps({k:report.get(k) for k in ['pool','status','error','native_cleanup_confirmed']}),flush=True)
    (ROOT/'checks/native-tool-functional-diagnostics-v2.json').write_text(json.dumps(reports,indent=2))


if __name__=='__main__':
    os.environ['PATH']=str(ROOT/'client-bin')+':'+os.environ['PATH']
    os.environ['SSH_AUTH_SOCK']='/home/chenkeyi/.local/share/harbor-rsi/near-r3-20261015/auth.sock'
    asyncio.run(main())
