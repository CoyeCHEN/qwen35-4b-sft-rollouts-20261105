"""Build native TMax environments using unique, hashed actual contexts.

Only generated external task copies gain the prepared image identity. Official
task.json, container.def, instruction and verifier bytes are preserved. Original
initial-state tests run in a trusted preparation container, never the teacher.
"""
from collections import Counter
import datetime
import hashlib
import json
from pathlib import Path
import shutil
import stat
import subprocess
import time
import tomllib
import warnings

import toml
from harbor.models.task.config import TaskConfig
from prepare_cf_images import command, image_info, DISK_RESERVE

ROOT = Path('/home/chenkeyi/.local/share/harbor-rsi/qwen35-new-cf500-tmax500-20261029')


def tree_identity(root):
    return [dict(path=str(p.relative_to(root)), mode=stat.S_IMODE(p.stat().st_mode),
        sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in sorted(root.rglob('*')) if p.is_file()]


def main():
    out = ROOT / 'checks/tmax-environments'; out.mkdir(exist_ok=True)
    rows = list(map(json.loads, (ROOT / 'manifests/TMAX_PREPARED_TASKS.jsonl').open()))
    canary = json.loads((ROOT / 'checks/tmax-preparation-v2.json').read_text())['canary_task_ids']
    rows.sort(key=lambda r: (canary.index(r['task_id']) if r['task_id'] in canary else 8, r['task_id']))
    counts = Counter()
    for row in rows:
        ident = row['task_id']; receipt_file = out / (ident + '.json')
        if receipt_file.exists():
            counts[json.loads(receipt_file.read_text())['status']] += 1
            continue
        if row['task_path'] is None:
            raise ValueError('Source preparation is incomplete; no implicit candidate fallback')
        if shutil.disk_usage(ROOT).free < DISK_RESERVE:
            (ROOT / 'checks/tmax-image-preparation.json').write_text(json.dumps(dict(
                status='PREPARATION_WAITING_FOR_DISK_HEADROOM', actual_free_bytes=shutil.disk_usage(ROOT).free,
                required_free_bytes=DISK_RESERVE, counts=dict(counts), next_task_id=ident), indent=2))
            return
        started = time.monotonic(); source = Path(row['task_path'])
        raw_config = tomllib.loads((source / 'task.toml').read_text())
        with warnings.catch_warnings():
            warnings.simplefilter('ignore', DeprecationWarning)
            config = TaskConfig.model_validate(raw_config)
        original_tree = tree_identity(source / 'environment')
        context_sha = hashlib.sha256(json.dumps(original_tree, sort_keys=True).encode()).hexdigest()
        context = ROOT / 'build-contexts' / (ident + '-' + context_sha[:16])
        if not context.exists():
            shutil.copytree(source / 'environment', context)
        if tree_identity(context) != original_tree:
            raise ValueError('Unique actual build context differs from official conversion')
        tag = 'rsi-stage2-tmax-20261029:' + ident
        name = 'tmax500-preflight-' + context_sha[:16]
        record = dict(task_id=ident, checked_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
            status='PREPARING', source_task_path=str(source), actual_build_context=str(context),
            build_context_sha256=context_sha, build_context_files=original_tree,
            generated_original_task_toml_sha256=hashlib.sha256((source / 'task.toml').read_bytes()).hexdigest(),
            model_attempts=0, official_final_verifier_executed=False)
        try:
            info = image_info(tag)
            if info is None:
                with (out / (ident + '.build.log')).open('x') as stream:
                    built = subprocess.run(['docker', 'build', '--progress=plain', '--label',
                        'rsi.campaign=' + ROOT.name, '--tag', tag, str(context)],
                        stdout=stream, stderr=subprocess.STDOUT, timeout=config.environment.build_timeout_sec)
                if built.returncode:
                    raise RuntimeError('Native environment build failed; original log preserved')
                info = image_info(tag)
            record.update(image_id=info['Id'], image_tag=tag, image_size_bytes=info['Size'])
            initial = ROOT / 'sources/tmax/original-tasks' / ident / 'test_initial_state.py'
            checked = command(['docker', 'run', '--rm', '--name', name,
                '--label', 'rsi.campaign=' + ROOT.name, '--cpus', str(config.environment.cpus or 1),
                '--memory', str((config.environment.memory_mb or 2048) * 1024**2),
                '--mount', 'type=bind,src=' + str(initial) + ',dst=/trusted-preparation/test_initial_state.py,readonly',
                '--entrypoint', '/bin/bash', info['Id'], '-lc',
                'set -eu; pwd -P; id; test -w .; test ! -e /tests; '
                'python3 -m pytest -q /trusted-preparation/test_initial_state.py'], timeout=180)
            record.update(initial_state_returncode=checked.returncode, initial_state_stdout=checked.stdout[:24000],
                initial_state_stderr=checked.stderr[:4000])
            if checked.returncode:
                record['status'] = 'ORIGINAL_INITIAL_STATE_TEST_FAILED'
            else:
                runtime = ROOT / 'prepared-tasks/tmax' / ident
                runtime.parent.mkdir(parents=True, exist_ok=True)
                shutil.copytree(source, runtime)
                prepared = json.loads(json.dumps(raw_config))
                prepared['environment']['docker_image'] = info['Id']
                (runtime / 'task.toml').write_text(toml.dumps(prepared))
                for relative in ['instruction.md', 'tests/test_final_state.py', 'tests/test.sh']:
                    if (runtime / relative).read_bytes() != (source / relative).read_bytes():
                        raise ValueError('Prepared task copy changed official instruction/verifier bytes')
                record.update(status='IMAGE_AND_ORIGINAL_INITIAL_STATE_PASSED_FINAL_VERIFIER_PENDING',
                    prepared_task_path=str(runtime), prepared_task_toml_sha256=hashlib.sha256((runtime / 'task.toml').read_bytes()).hexdigest(),
                    generated_config_delta={'environment.docker_image': info['Id']},
                    agent_timeout_policy_sec=max(config.agent.timeout_sec or 0, 10800),
                    original_verifier_timeout_sec=config.verifier.timeout_sec,
                    original_resources=config.environment.model_dump(mode='json'))
            if tree_identity(context) != original_tree:
                raise ValueError('Actual build context changed during preparation')
        except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
            record.update(status='ENVIRONMENT_PREPARATION_FAILED', error_type=type(error).__name__, error=str(error)[:600])
        finally:
            removed = command(['docker', 'rm', '-f', name])
            record['preparation_container_cleanup_confirmed'] = removed.returncode == 0 or 'No such container' in removed.stderr
        record.update(seconds=time.monotonic()-started, disk_free_bytes=shutil.disk_usage(ROOT).free)
        receipt_file.write_text(json.dumps(record, indent=2)); counts[record['status']] += 1
        report = dict(status='PREPARING', planned_tasks=500, observed_tasks=sum(counts.values()),
            counts=dict(counts), model_attempts=0, final_verifier_acceptance=False)
        (ROOT / 'checks/tmax-image-preparation.json').write_text(json.dumps(report, indent=2))
        print(json.dumps(dict(task_id=ident, status=record['status'], seconds=record['seconds'])), flush=True)
    report.update(status='IMAGE_AND_INITIAL_STATE_PREPARATION_FINISHED_FINAL_VERIFIER_PENDING')
    (ROOT / 'checks/tmax-image-preparation.json').write_text(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
