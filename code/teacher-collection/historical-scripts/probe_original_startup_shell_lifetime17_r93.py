"""Trusted original-test failure-cleanup diagnostic; no teacher or Reward script."""
import asyncio
import datetime
import fcntl
import ipaddress
import json
import os
from pathlib import Path
import shlex
import subprocess
import time
import re
import ast
import hashlib
import tomllib
from uuid import uuid4

from harbor.environments.factory import EnvironmentFactory
from harbor.models.task.config import TaskConfig
from harbor.models.trial.paths import TrialPaths
import collection_readiness_r12 as n
from collection_attempts_r8 import attempt_counts
from collection_selection_r7 import active_rows

S = n.R / 'stream/original-startup-shell-lifetime17-r93'
IDS = ['task_004361_0d2c270d']
STEPS = {}


def save(value):
    value.update(pid=os.getpid(), checked_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        model_calls=0, teacher_dispatches=0, official_verifier_runs=0, native_environment_concurrency=1)
    temporary = S / 'state.pending'
    temporary.write_text(json.dumps(value, indent=2))
    temporary.replace(S / 'state.json')


async def main():
    S.mkdir(parents=True, exist_ok=True)
    lock = (S / 'worker.lock').open('a')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    if (S / 'PLAN.json').exists():
        raise FileExistsError('Observe the existing finite diagnostic; no automatic replay')
    prior = n.R / 'stream/original-runtime-process-native17-r71/TERMINAL.json'
    previous = json.loads(prior.read_bytes())
    if Path('/proc/' + str(previous['pid'])).exists():
        raise ValueError('The existing finite preparation slot has not finished')
    rows = {row['task_id']: row for row in active_rows(attempt_counts())}
    tasks = []
    for ident in IDS:
        if attempt_counts().get(ident, 0):
            raise ValueError('This public diagnostic is restricted to unattempted Tasks')
        failure=n.R/'stream/original-initial-failure-build17-r58/environment-outcomes'/(ident+'.json')
        original=n.R/'sources/tmax/original-tasks'/ident/'container.def'
        match=re.search(r"cat << .*INNEREOF.* > /home/user/report.py\n(.*?)\nINNEREOF",original.read_text(),re.S)
        if not match:raise ValueError('Original report source heredoc changed')
        program=match.group(1)
        tree=ast.parse(program)
        if any(isinstance(x,ast.Name) and x.id in ['__file__','argv'] for x in ast.walk(tree)):
            raise ValueError('Original program depends on its diagnostic file path')
        native_program=S/'original-report.py';native_program.write_text(program)
        digest=hashlib.sha256(program.encode()).hexdigest()
        verify="from pathlib import Path;import re,hashlib,json;s=Path('/home/user/start_bg.sh').read_text();m=re.search(r\"cat << .*INNEREOF.* > /home/user/report.py\\n(.*?)\\nINNEREOF\",s,re.S);print(json.dumps({'original_program_matches_image':bool(m) and hashlib.sha256(m.group(1).encode()).hexdigest()=="+repr(digest)+",'program_present':bool(m)}))"
        STEPS[ident]=[('original_generated_script_identity',shlex.join(['python3','-c',verify]),20),
            ('original_initial_state_in_live_parent_shell','python3 -m pytest -q /trusted-preparation/test_initial_state.py',40),
            ('no_reward_written','test ! -e /logs/verifier/reward.txt',10)]
        result=n.R/'stream/original-initial-failure-build17-r58/build-receipts'/ident/'build.json'
        tasks.append(dict(task_id=ident, failure=str(failure), failure_sha256=n.sha(failure),
            result=str(result), result_sha256=n.sha(result)))
    n.freeze(S / 'PLAN.json', dict(tasks=tasks, steps=STEPS, source_sha256=n.sha(Path(__file__)),
        deployment_config_sha256=n.CONFIG_SHA, engine_id=n.NODE['engine_id'],
        previous_released_preparation_slot=str(prior), previous_slot_sha256=n.sha(prior),
        model_calls=0, teacher_dispatches=0, official_verifier_runs=0, native_environment_concurrency=1,
        scope='Observe the original declared startup in a disposable native environment and execute unchanged initial tests. Do not repair the report program. No Goal code or official tests are modified, no official tests or Reward wrapper run, no Teacher runs, and no Ready is published.'))
    terminal = {}
    for index, item in enumerate(tasks):
        ident = item['task_id']
        directory = S / 'probes' / ident
        directory.mkdir(parents=True)
        environment = None
        admitted = None
        outcome = dict(task_id=ident, steps=[], official_verifier_runs=0, qualified_success_not_implied=True)
        try:
            if attempt_counts().get(ident, 0):
                raise ValueError('Task has started since diagnostic registration; preserve it')
            import accept_original_runtime_processes17_r71 as previous
            admitted = n.choose(previous.prepare(rows[ident]))
            save(dict(stage='EXACT_IMAGE_ON17', current_task_id=ident, terminal=len(terminal), planned=len(tasks)))
            n.freeze(directory / 'image.json', await asyncio.to_thread(n.ensure_resident, admitted))
            actual_verifier=n.native_config(admitted,'nop')
            verifier_env=dict(actual_verifier.verifier.env)
            n.freeze(directory/'effective-verifier-env.json',verifier_env)
            cfg = n.native_config(admitted, 'install')
            subnet = str(ipaddress.ip_network((int(ipaddress.ip_address('10.248.0.32')) + index * 16, 28)))
            network = directory / 'network.json'
            n.freeze(network, dict(networks=dict(default=dict(ipam=dict(config=[dict(subnet=subnet)])))))
            cfg.environment.extra_docker_compose = [network, *cfg.environment.extra_docker_compose[1:]]
            startup=directory/'original-shell-lifetime.json'
            n.freeze(startup,dict(services=dict(main=dict(command=['bash','-lc','cd /home/user\nrm -f /home/user/.report_started\nsource /home/user/start_bg.sh\nsleep infinity'],
                healthcheck=dict(test=['CMD','pgrep','-f','^python3 report.py$'],interval='1s',timeout='2s',retries=120)))))
            cfg.environment.extra_docker_compose.append(startup)
            cfg.environment.kwargs['project_namespace'] = 'cftmaxnativeenvr93'
            task = Path(admitted['prepared_task_path'])
            task_config = TaskConfig.model_validate(tomllib.loads((task / 'task.toml').read_text()))
            paths = TrialPaths(trial_dir=directory)
            environment = EnvironmentFactory.create_environment_from_config(config=cfg.environment,
                environment_dir=task / 'environment', environment_name=ident, session_id=uuid4().hex,
                trial_paths=paths, task_env_config=task_config.environment)
            n.freeze(directory / 'environment.json', dict(image_id=admitted['image_id'],
                task_env_config=task_config.environment.model_dump(mode='json'),
                native_environment_config=cfg.environment.model_dump(mode='json'), identity=environment.identity))
            await environment.start(force_build=False)
            for artifact in admitted['verifier_files']:
                if n.sha(task/artifact['path'])!=artifact['sha256']:
                    raise ValueError('Official private test bytes changed')
            await environment.upload_file(n.R/'sources/tmax/original-tasks'/ident/'test_initial_state.py','/trusted-preparation/test_initial_state.py')
            for name, command, timeout in STEPS[ident]:
                save(dict(stage=name, current_task_id=ident, terminal=len(terminal), planned=len(tasks)))
                begin = time.monotonic()
                result = await environment.exec(command, user='root', timeout_sec=timeout,env=verifier_env)
                for channel in ['stdout', 'stderr']:
                    (directory / (name + '-' + channel + '.txt')).write_text(getattr(result, channel) or '')
                outcome['steps'].append(dict(name=name, return_code=result.return_code,
                    seconds=time.monotonic() - begin))
            outcome['status'] = 'ORIGINAL_STARTUP_RUNTIME_AND_INITIAL_DIAGNOSTIC_NOT_REWARD'
            outcome['official_test_bodies_executed']=False
        except Exception as error:
            outcome.update(status='PUBLIC_DIAGNOSTIC_FAILED', error_type=type(error).__name__, reason=str(error)[-1200:])
        finally:
            if environment is not None:
                try:
                    await environment.stop(delete=True)
                    outcome['native_cleanup_completed'] = True
                except Exception as error:
                    outcome.update(native_cleanup_completed=False, cleanup_error=str(error)[-1200:])
            n.freeze(directory / 'PROBE.json', outcome)
            terminal[ident] = outcome['status']
            if admitted is not None:
                try:
                    n.freeze(directory / 'release.json', await asyncio.to_thread(n.release_cold_cache, admitted))
                except Exception as error:
                    n.freeze(directory / 'release-error.json', dict(error_type=type(error).__name__, reason=str(error)[-600:]))
            save(dict(stage='PUBLIC_DIAGNOSTIC_TERMINAL', current_task_id=ident,
                terminal=len(terminal), planned=len(tasks), outcomes=terminal))
            print(json.dumps(outcome), flush=True)
    target = n.NODE['ssd_root'] + '/original-startup-shell-lifetime-r93'
    subprocess.run([*n.DEPLOYMENT['ssh'], n.DEPLOYMENT['host'], 'mkdir -p ' + shlex.quote(target)], check=True, timeout=30)
    subprocess.run(['rsync', '-a', '-e', shlex.join(n.DEPLOYMENT['ssh']), str(S) + '/',
        n.DEPLOYMENT['host'] + ':' + target + '/'], check=True, timeout=180)
    n.freeze(S / 'TERMINAL.json', dict(outcomes=terminal, pid=os.getpid(), ssd_log_root=target,
        official_verifier_runs=0, teacher_dispatches=0, model_calls=0))


if __name__ == '__main__':
    os.environ['PATH'] = str(n.R / 'client-bin-v2') + ':' + os.environ['PATH']
    for name in ['DEEPSEEK_API_KEY', 'OPENAI_API_KEY', 'GH_TOKEN']:
        os.environ.pop(name, None)
    asyncio.run(main())
