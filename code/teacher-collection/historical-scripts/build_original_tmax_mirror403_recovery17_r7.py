"""Finite unchanged-context builds for the two registered registry403 failures."""
import datetime
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

R = Path('/home/chenkeyi/workspace/RSI/runtime-evidence/qwen35-new-cf500-tmax500-20261029')
S = Path('/ssd/chenkeyi/qwen35-new-cf500-tmax500-20261029')


def main():
    plan = R / 'manifests/TMAX_ORIGINAL_MIRROR403_RECOVERY_R7.json'
    registered = json.loads(plan.read_text())
    results = []
    statefile = R / 'checks/tmax-original-mirror403-build-r7.json'
    if statefile.exists():raise FileExistsError('Inspect the existing finite build pass')
    for item in registered['tasks']:
        ident = item['task_id']
        if not ident.startswith('task_') or not ident.replace('_', '').isalnum():raise ValueError('Invalid original task ID')
        result = dict(task_id=ident, status='BUILDING_ORIGINAL_TASK')
        value = dict(status='BUILDING_ORIGINAL_MIRROR403_RECOVERIES', pid=os.getpid(),
            checked_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
            source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            plan_sha256=hashlib.sha256(plan.read_bytes()).hexdigest(), planned_tasks=len(registered['tasks']),
            observed_tasks=len(results), current_task_id=ident, records=results, model_calls=0)
        statefile.write_text(json.dumps(value, indent=2))
        try:
            built = S / 'buildkit-rootless-r2/archives' / ident / 'client-proxy-r3/build.json'
            if built.exists():raise FileExistsError('A prior native build already exists; preserve and inspect')
            with (R / 'checks' / (ident + '-mirror403-build-r7.log')).open('x') as stream:
                subprocess.run([sys.executable, str(R / 'scripts/build_tmax_native_oci_ssd17_r3.py'),
                    ident, registered['source_candidate_manifest_sha256']], stdout=stream, stderr=subprocess.STDOUT,
                    check=True, timeout=3800)
            data = json.loads(built.read_text())
            if data['status'] != 'ORIGINAL_NATIVE_OCI_ARCHIVE_BUILT_INITIAL_AND_VERIFIER_TESTS_PENDING':raise ValueError('Native original build failed')
            result.update(status='ORIGINAL_NATIVE_ARCHIVE_READY_INITIAL_AND_VERIFIER_PENDING',
                native_build_receipt=str(built), native_build_receipt_sha256=hashlib.sha256(built.read_bytes()).hexdigest())
        except (OSError, ValueError, subprocess.SubprocessError) as error:
            result.update(status='ORIGINAL_NATIVE_BUILD_RECOVERY_FAILED', error_type=type(error).__name__, reason=str(error)[:1000])
        results.append(result)
    value.update(status='FINITE_ORIGINAL_MIRROR403_BUILD_PASS_TERMINAL',
        checked_at=datetime.datetime.now(datetime.timezone.utc).isoformat(), observed_tasks=len(results),
        records=results, current_task_id=None)
    statefile.write_text(json.dumps(value, indent=2))


if __name__ == '__main__':
    for key in ['DEEPSEEK_API_KEY', 'GH_TOKEN', 'OPENAI_API_KEY']:os.environ.pop(key, None)
    main()
