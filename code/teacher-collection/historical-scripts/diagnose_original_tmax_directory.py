"""Native installed-wheel setup and actual execution-directory check; no model calls."""
import asyncio
import argparse
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
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--environment-export-check',action='store_true')
    args=parser.parse_args()
    label='tmax-original-environment-r4-v3' if args.environment_export_check else 'tmax-original-directory-r4-v2'
    out=ROOT/'diagnostics'/label;out.mkdir(exist_ok=False)
    task_path=ROOT/'prepared-tasks/tmax-runtime-r4'/('task_000180_a74736b1' if args.environment_export_check else 'task_000949_ba30eec9')
    task=Task(task_path);paths=TrialPaths(out)
    for p in [paths.agent_dir,paths.verifier_dir,paths.artifacts_dir]:p.mkdir(parents=True,exist_ok=True)
    base=json.loads((ROOT/'configs/canary-summary-cf.json').read_text())
    opts=dict(base['environment']['kwargs']);opts['project_namespace']='tmaxcwdnativer4v220261030'
    env=RemoteDockerEnvironment(environment_dir=task.paths.environment_dir,
        environment_name='tmax-cwd-original',session_id=uuid4().hex,trial_paths=paths,
        task_env_config=task.config.environment,**opts)
    env.configure_agent_runtime(writable=True,executable=True)
    agent=OpenHarnessAgent(logs_dir=paths.agent_dir,model_name='deepseek/deepseek-flash',**base['agents'][0]['kwargs'])
    report=dict(model_calls=0,teacher_attempts=0,task_id=task_path.name,passed=False,
        source_task_toml_sha256=hashlib.sha256((task_path/'task.toml').read_bytes()).hexdigest())
    try:
        await asyncio.wait_for(env.start(force_build=False),timeout=180)
        await asyncio.wait_for(agent.setup(env),timeout=600)
        code='import os,json,importlib.metadata;print(json.dumps(dict(cwd=os.getcwd(),HOME=os.environ.get("HOME"),BASH_ENV=os.environ.get("BASH_ENV"),environment_loaded=os.environ.get("TMAX_ORIGINAL_ENV_LOADED"),wheel_version=importlib.metadata.version("open-harness-ai"))))'
        got=await env.exec(shlex.join([agent.lifecycle_interpreter,'-c',code]),timeout_sec=60)
        report.update(exec_returncode=got.return_code,stdout=got.stdout,stderr=got.stderr)
        value=json.loads(got.stdout)
        assert got.return_code==0 and value['cwd']=='/home/user' and value['HOME']=='/home/user'
        assert value['wheel_version']=='0.3.0+rsi.summary.20261030'
        if args.environment_export_check:
            assert value['environment_loaded']=='1' and value['BASH_ENV']=='/usr/local/lib/tmax-original-environment.sh'
        report['passed']=True
    except Exception as error:
        report.update(error_type=type(error).__name__,error=str(error))
    finally:
        try:
            await env.stop(delete=True);report['native_cleanup_confirmed']=True
        except Exception as error:
            report.update(native_cleanup_confirmed=False,cleanup_error_type=type(error).__name__)
        file='tmax-original-environment-native-agent-r4-v3.json' if args.environment_export_check else 'tmax-original-directory-native-agent-r4-v2.json'
        (ROOT/'checks'/file).write_text(json.dumps(report,indent=2))
        print(json.dumps(report))


if __name__=='__main__':
    os.environ['PATH']=str(ROOT/'client-bin')+':'+os.environ['PATH']
    os.environ['SSH_AUTH_SOCK']='/home/chenkeyi/.local/share/harbor-rsi/near-r3-20261015/auth.sock'
    asyncio.run(main())
