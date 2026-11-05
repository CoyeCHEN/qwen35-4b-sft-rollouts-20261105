"""Build native TMax environments using unique, hashed actual contexts.

Only generated external task copies gain the prepared image identity. Official
task.json, container.def, instruction and verifier bytes are preserved. Original
initial-state tests run in a trusted preparation container, never the teacher.
"""
from collections import Counter
import argparse
import datetime
import hashlib
import json
from pathlib import Path
import shutil
import re
import shlex
import stat
import subprocess
import time
import tomllib
import warnings

import toml
import yaml
from tmax_runtime_adapter import runtime_compose_override, runtime_environment_files
from harbor.models.task.config import TaskConfig
from prepare_cf_images import command, image_info, DISK_RESERVE
from import_tmax_ssd17_archive import import_if_prepared

ROOT = Path('/home/chenkeyi/.local/share/harbor-rsi/qwen35-new-cf500-tmax500-20261029')


def tree_identity(root):
    return [dict(path=str(p.relative_to(root)), mode=stat.S_IMODE(p.stat().st_mode),
        sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in sorted(root.rglob('*')) if p.is_file()]


def cleanup_preparation_container(record, name):
    """Always retain the check outcome, including a failed cleanup acknowledgement."""
    record['preparation_cleanup_timeout_sec']=180
    try:
        removed=command(['docker','rm','-f',name],timeout=180)
        record['preparation_container_cleanup_confirmed']=(removed.returncode==0 or 'No such container' in removed.stderr)
        if not record['preparation_container_cleanup_confirmed']:
            record['preparation_cleanup_error']=dict(returncode=removed.returncode,stderr=removed.stderr[-4000:])
    except (OSError,subprocess.SubprocessError) as error:
        record['preparation_container_cleanup_confirmed']=False
        record['preparation_cleanup_error']=dict(error_type=type(error).__name__,error=str(error))
    if not record['preparation_container_cleanup_confirmed']:
        record['status_before_cleanup_failure']=record['status']
        record['status']='ENVIRONMENT_CLEANUP_UNCONFIRMED'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--task-id', help='Prepare one preregistered task without changing the full worker')
    parser.add_argument('--startup-recheck', action='store_true', help='Preserve first preparation receipts and test corrected original startup')
    parser.add_argument('--manifest', type=Path, default=ROOT/'manifests/TMAX_RUNTIME_CANDIDATES_V2.jsonl', help='Explicit preregistered candidates; source membership is checked before preparation')
    parser.add_argument('--evidence-tag', help='New immutable preparation evidence/runtime namespace, preserving prior checks')
    parser.add_argument('--public-input-boundary',type=Path,help='Reviewed immutable inventory of published inputs under an otherwise reserved directory')
    parser.add_argument('--context-only',action='store_true',help='Freeze the same native public build context for remote SSD preparation; no image/runtime/teacher claims')
    args = parser.parse_args()
    if args.context_only and not args.task_id:
        raise ValueError('Context-only preparation requires one explicit frozen task')
    if args.evidence_tag and not re.fullmatch(r'[a-z][a-z0-9-]{1,60}',args.evidence_tag):
        raise ValueError('Invalid preparation evidence namespace')
    if args.startup_recheck and not args.task_id:
        raise ValueError('Startup recheck requires an explicit source task identity')
    out = ROOT / 'checks' / ('tmax-environments-'+args.evidence_tag if args.evidence_tag else 'tmax-environments-runtime-r4' if args.startup_recheck else 'tmax-environments-v2'); out.mkdir(exist_ok=True)
    rows = list(map(json.loads, args.manifest.open()))
    canary = json.loads((ROOT / 'checks/tmax-preparation-v2.json').read_text())['canary_task_ids']
    rows.sort(key=lambda r: (canary.index(r['task_id']) if r['task_id'] in canary else 8, r['task_id']))
    if args.task_id:
        rows = [r for r in rows if r['task_id'] == args.task_id]
        if len(rows) != 1:
            raise ValueError('Single-task preparation must use exactly one preregistered source task')
    report_file = ROOT / 'checks' / ('tmax-single-preparation-' + args.task_id + ('-'+args.evidence_tag if args.evidence_tag else '-runtime-r4' if args.startup_recheck else '') + '.json'
                                    if args.task_id else 'tmax-image-preparation-v2.json')
    counts = Counter()
    report = dict(status='PREPARING', planned_tasks=len(rows), model_attempts=0, final_verifier_acceptance=False)
    for row in rows:
        ident = row['task_id']; receipt_file = out / (ident + '.json')
        if receipt_file.exists():
            counts[json.loads(receipt_file.read_text())['status']] += 1
            continue
        if row['task_path'] is None:
            raise ValueError('Source preparation is incomplete; no implicit candidate fallback')
        if not args.context_only and shutil.disk_usage(ROOT).free < DISK_RESERVE:
            report_file.write_text(json.dumps(dict(
                status='PREPARATION_WAITING_FOR_DISK_HEADROOM', actual_free_bytes=shutil.disk_usage(ROOT).free,
                required_free_bytes=DISK_RESERVE, counts=dict(counts), next_task_id=ident), indent=2))
            return
        started = time.monotonic(); source = Path(row['task_path'])
        raw_config = tomllib.loads((source / 'task.toml').read_text())
        with warnings.catch_warnings():
            warnings.simplefilter('ignore', DeprecationWarning)
            config = TaskConfig.model_validate(raw_config)
        original_tree = tree_identity(source / 'environment')
        original_source = ROOT / 'sources/tmax/original-tasks' / ident
        runtime_files = runtime_environment_files(original_source)
        expected_tree = json.loads(json.dumps(original_tree))
        dockerfile = (source / 'environment/Dockerfile').read_text()
        for target, body in runtime_files.items():
            filename=Path(target).name
            if (source/'environment'/filename).exists():raise ValueError('Runtime extension collides with an original converter output')
            dockerfile += '\nCOPY '+json.dumps([filename,target])+'\n'
            expected_tree.append(dict(path=filename,mode=0o644,sha256=hashlib.sha256(body.encode()).hexdigest()))
        if '/usr/local/lib/tmax-original-environment.sh' in runtime_files:
            dockerfile += '\nENV BASH_ENV=/usr/local/lib/tmax-original-environment.sh\n'
        if runtime_files:
            next(x for x in expected_tree if x['path']=='Dockerfile')['sha256']=hashlib.sha256(dockerfile.encode()).hexdigest()
        expected_tree.sort(key=lambda x:x['path'])
        context_sha = hashlib.sha256(json.dumps(expected_tree, sort_keys=True).encode()).hexdigest()
        context = ROOT / 'build-contexts' / (ident + '-' + context_sha[:16])
        if not context.exists():
            shutil.copytree(source / 'environment', context)
            if runtime_files:
                (context/'Dockerfile').write_text(dockerfile)
                for target, body in runtime_files.items():
                    script=context/Path(target).name;script.write_text(body);script.chmod(0o644)
        if tree_identity(context) != expected_tree:
            raise ValueError('Unique actual build context differs from the recorded native conversion and original runtime scripts')
        if args.context_only:
            target=ROOT/'checks/tmax-native-contexts-ssd17-r2'/(ident+'.json')
            target.parent.mkdir(exist_ok=True)
            value=dict(task_id=ident,source_revision=row['revision'],source_manifest_sha256=hashlib.sha256(args.manifest.read_bytes()).hexdigest(),
                source_task_path=str(source),source_task_toml_sha256=hashlib.sha256((source/'task.toml').read_bytes()).hexdigest(),
                actual_build_context=str(context),build_context_sha256=context_sha,build_context_files=expected_tree,
                status='NATIVE_PUBLIC_CONTEXT_FROZEN_RUNTIME_ACCEPTANCE_PENDING',model_calls=0,environment_ready=False)
            if target.exists():
                if json.loads(target.read_text())!=value:raise ValueError('Frozen native public context changed')
            else:
                with target.open('x') as stream:stream.write(json.dumps(value,indent=2))
            print(json.dumps(value),flush=True)
            return
        tag = ('rsi-stage2-tmax-runtime-r3:'+ident+'-'+context_sha[:12] if runtime_files else 'rsi-stage2-tmax-20261029:'+ident)
        preparation_scope=args.evidence_tag or ('runtime-r4' if args.startup_recheck else 'v2')
        name = 'tmax500-preflight-' + preparation_scope + '-' + context_sha[:16]
        record = dict(source_candidate_manifest=str(args.manifest),
            source_candidate_manifest_sha256=hashlib.sha256(args.manifest.read_bytes()).hexdigest(),
            preparer_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),task_id=ident, checked_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
            status='PREPARING', preparation_scope=preparation_scope,preparation_container_name=name,source_task_path=str(source), actual_build_context=str(context),
            build_context_sha256=context_sha, build_context_files=expected_tree,
            original_converter_build_context_files=original_tree,
            runtime_script_destinations=list(runtime_files),
            generated_original_task_toml_sha256=hashlib.sha256((source / 'task.toml').read_bytes()).hexdigest(),
            model_attempts=0, official_final_verifier_executed=False,
            original_build_timeout_sec=config.environment.build_timeout_sec, preparation_build_budget_sec=3600,
            preparation_budget_reason='External preparation may finish/cache public dependencies before native runtime; original task/config and verifier deadlines unchanged')
        try:
            info = image_info(tag)
            if info is None:
                cached=import_if_prepared(ident,context_sha,row['revision'],tag)
                if cached is not None:
                    info,record['native_ssd_archive_import']=cached
            if info is None:
                with (out / (ident + '.build.log')).open('x') as stream:
                    built = subprocess.run(['docker', 'build', '--progress=plain', '--label',
                        'rsi.campaign=' + ROOT.name, '--tag', tag, str(context)],
                        stdout=stream, stderr=subprocess.STDOUT, timeout=3600)
                if built.returncode:
                    raise RuntimeError('Native environment build failed; original log preserved')
                info = image_info(tag)
            record.update(image_id=info['Id'], image_tag=tag, image_size_bytes=info['Size'])
            initial = ROOT / 'sources/tmax/original-tasks' / ident / 'test_initial_state.py'
            startup = runtime_compose_override(ROOT / 'sources/tmax/original-tasks' / ident)
            launch = ['docker', 'run', '--rm', '--name', name,
                '--label', 'rsi.campaign=' + ROOT.name, '--cpus', str(config.environment.cpus or 1),
                '--memory', str((config.environment.memory_mb or 2048) * 1024**2),
                '--workdir', '/home/user', '--env', 'HOME=/home/user',
                '--mount', 'type=bind,src=' + str(initial) + ',dst=/trusted-preparation/test_initial_state.py,readonly',
                '--entrypoint', '/bin/bash']
            public_guard='test ! -e /tests'
            if args.public_input_boundary:
                boundary=json.loads(args.public_input_boundary.read_text())
                if boundary['task_id']!=ident or boundary['source_container_def_sha256']!=hashlib.sha256((original_source/'container.def').read_bytes()).hexdigest():
                    raise ValueError('Public input boundary does not match the original task')
                if boundary['root']!='/tests' or not boundary['files']:
                    raise ValueError('Invalid reviewed public input root')
                for item in boundary['files']:
                    path=Path(item['path'])
                    if not path.is_absolute() or not path.is_relative_to('/tests') or '..' in path.parts:
                        raise ValueError('Reviewed input escaped the reserved root')
                    if path.name in ['test.sh','test_final_state.py','test_initial_state.py']:
                        raise ValueError('Official verifier code is never a public task input')
                expected={item['path']:item['sha256'] for item in boundary['files']}
                program=('from pathlib import Path; import json,hashlib; '
                    'root=Path("/tests"); files=list(root.rglob("*")); '
                    'assert not any(p.is_symlink() for p in files); '
                    'actual={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in files if p.is_file()}; '
                    'assert actual=='+repr(expected)+'; print("Published input inventory exactly matched; no verifier code exposed")')
                public_guard='python3 -c '+shlex.quote(program)
                record['reviewed_public_input_boundary']=dict(path=str(args.public_input_boundary),sha256=hashlib.sha256(args.public_input_boundary.read_bytes()).hexdigest())
            probe = ('set -eu; pwd -P; id; test "$HOME" = /home/user; test "$(pwd -P)" = /home/user; test -w .; '+public_guard+'; '
                     'python3 -m pytest -q /trusted-preparation/test_initial_state.py')
            if startup:
                original_command = startup['services']['main']['command']
                original_command = [*original_command[:-1], original_command[-1].replace('$$', '$')]
                started_container = command([*launch[:2], '-d', *launch[2:], info['Id'], *original_command[1:]], timeout=180)
                started_container.check_returncode()
                record['native_compose_startup_override'] = startup
                if 'healthcheck' in startup['services']['main']:
                    # The actual native runtime uses compose up --wait. This
                    # trusted preparation container observes the same boundary.
                    ready = command(['docker', 'exec', name, 'bash', '-c',
                        'for ((i=0; i<120; i++)); do '
                        'read -r task_process < /proc/1/comm; '
                        'if test "$task_process" = sleep; then exit 0; fi; sleep 1; done; exit 1'], timeout=150)
                    record['original_startup_ready_returncode'] = ready.returncode
                    ready.check_returncode()
                checked = command(['docker', 'exec', '--workdir', '/home/user', '--env', 'HOME=/home/user', name, 'bash', '-lc', probe], timeout=180)
            else:
                checked = command([*launch, info['Id'], '-lc', probe], timeout=180)
            record.update(initial_state_returncode=checked.returncode, initial_state_stdout=checked.stdout[:24000],
                initial_state_stderr=checked.stderr[:4000])
            if checked.returncode:
                record['status'] = 'ORIGINAL_INITIAL_STATE_TEST_FAILED'
            else:
                runtime = ROOT / 'prepared-tasks' / ('tmax-'+args.evidence_tag if args.evidence_tag else 'tmax-runtime-r4') / ident
                runtime.parent.mkdir(parents=True, exist_ok=True)
                if not runtime.exists():
                    shutil.copytree(source, runtime)
                prepared = json.loads(json.dumps(raw_config))
                prepared['environment']['docker_image'] = info['Id']
                prepared['environment']['workdir'] = '/home/user'
                prepared['environment'].setdefault('env',{})['HOME'] = '/home/user'
                runtime_config=runtime / 'task.toml'
                if 'docker_image' not in tomllib.loads(runtime_config.read_text())['environment']:
                    runtime_config.write_text(toml.dumps(prepared))
                elif tomllib.loads(runtime_config.read_text()) != prepared:
                    raise ValueError('Existing prepared runtime identity differs; no overwrite')
                if startup:
                    compose=runtime / 'environment/docker-compose.yaml'
                    if compose.exists() and yaml.safe_load(compose.read_text()) != startup:
                        raise ValueError('Existing startup identity differs; no overwrite')
                    if not compose.exists():compose.write_text(yaml.safe_dump(startup,sort_keys=False))
                    record['native_compose_startup_override']=startup
                for relative in ['instruction.md', 'tests/test_final_state.py', 'tests/test.sh']:
                    if (runtime / relative).read_bytes() != (source / relative).read_bytes():
                        raise ValueError('Prepared task copy changed official instruction/verifier bytes')
                record.update(status='IMAGE_AND_ORIGINAL_INITIAL_STATE_PASSED_FINAL_VERIFIER_PENDING',
                    prepared_task_path=str(runtime), prepared_task_toml_sha256=hashlib.sha256((runtime / 'task.toml').read_bytes()).hexdigest(),
                    generated_config_delta={'environment.docker_image': info['Id'], 'environment.workdir':'/home/user','environment.env.HOME':'/home/user'},
                    directory_contract_source='Pinned upstream env.py _start_shell --pwd and exported HOME; SHA256 22ff11632c3dc090920cea4315c6e1e2da3e755c90b5752f9dc3766ce2d12919',
                    agent_timeout_policy_sec=max(config.agent.timeout_sec or 0, 10800),
                    original_verifier_timeout_sec=config.verifier.timeout_sec,
                    original_resources=config.environment.model_dump(mode='json'))
            if tree_identity(context) != expected_tree or tree_identity(source/'environment') != original_tree:
                raise ValueError('Actual build context changed during preparation')
        except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
            if isinstance(error,subprocess.CalledProcessError):
                record['failed_command_returncode']=error.returncode
                record['failed_command_stdout']=(error.stdout or '')[-12000:]
                record['failed_command_stderr']=(error.stderr or '')[-12000:]
            record.update(status='ENVIRONMENT_PREPARATION_FAILED', error_type=type(error).__name__, error=str(error)[:600])
        finally:
            if record.get('status')!='IMAGE_AND_ORIGINAL_INITIAL_STATE_PASSED_FINAL_VERIFIER_PENDING':
                diagnostic=command(['docker','logs',name],timeout=15)
                record['failed_startup_log_returncode']=diagnostic.returncode
                record['failed_startup_stdout']=diagnostic.stdout[-12000:]
                record['failed_startup_stderr']=diagnostic.stderr[-12000:]
            cleanup_preparation_container(record,name)
        record.update(seconds=time.monotonic()-started, disk_free_bytes=shutil.disk_usage(ROOT).free)
        receipt_file.write_text(json.dumps(record, indent=2)); counts[record['status']] += 1
        report = dict(status='PREPARING', planned_tasks=len(rows), observed_tasks=sum(counts.values()),
            counts=dict(counts), model_attempts=0, final_verifier_acceptance=False)
        report_file.write_text(json.dumps(report, indent=2))
        print(json.dumps(dict(task_id=ident, status=record['status'], seconds=record['seconds'])), flush=True)
    report.update(status='IMAGE_AND_INITIAL_STATE_PREPARATION_FINISHED_FINAL_VERIFIER_PENDING')
    report_file.write_text(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
