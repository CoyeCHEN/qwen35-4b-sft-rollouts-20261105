"""Evidence-only review of four NOP false positives; no Task or Trial replay."""
from pathlib import Path
import datetime
import hashlib
import json
import re

R = Path('/home/chenkeyi/.local/share/harbor-rsi/qwen35-new-cf500-tmax500-20261029')
S = R / 'stream/collection-r3'
REVIEWS = {
    'mathematics_20260604_194036_001': ({'lll', 'attack'}, 'Public instruction requires creating attack.py and an LLL implementation.'),
    'mathematics_20260513_204536_001': ({'attack'}, 'Public instruction requires creating attack.py.'),
    'scientific-computing_20260507_093408_005': ({'savgol_corrected'}, 'Public instruction requires creating savgol_corrected.py.'),
    'scientific-computing_20260419_023954_006': ({'numpy'}, 'The official verifier itself imports only json/os/subprocess; numpy fails inside the original task simulation.py subprocess, whose repair and execution are the public assignment.'),
}


def read(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    destination = R / 'checks/native-environment-reviews-r10'
    destination.mkdir(exist_ok=False)
    rows = {x['task_id']: x for x in map(json.loads, (R / 'manifests/CALIBFORGE_500_TASKS.jsonl').open())}
    dispatches = [read(p) for p in (S / 'dispatches').glob('*/dispatch.json')]
    result = []
    for ident, (expected_modules, reason) in REVIEWS.items():
        original = S / 'environment-outcomes' / (ident + '.json')
        prior = read(original)
        if prior['status'] != 'ENV_FAILED' or prior['reason'] != 'Official verifier dependency/startup error in raw logs':
            raise ValueError('Original false-positive identity changed')
        install, nop = [], []
        for item in dispatches:
            if item['task_id'] != ident:
                continue
            if item['kind'] == 'teacher':
                raise ValueError('Review is limited to tasks with no teacher dispatch')
            if item['kind'] in ['install', 'nop']:
                (install if item['kind'] == 'install' else nop).append(item)
        if len(install) != 1 or len(nop) != 1:
            raise ValueError('Need exactly the original install and NOP evidence')
        native = {}
        for kind, item in [('install', install[0]), ('nop', nop[0])]:
            path = S / 'trials' / item['trial_name'] / 'result.json'
            raw = read(path)
            if raw.get('exception_info') or raw.get('infrastructure_errors') or not raw.get('finished_at'):
                raise ValueError('Native lifecycle failure cannot be reclassified')
            native[kind] = dict(trial=str(path.parent), result_sha256=sha(path))
            if kind == 'nop' and (not (raw.get('verifier') or {}).get('finished_at') or
                    (raw.get('verifier_result') or {}).get('rewards', {}).get('reward') != 0):
                raise ValueError('Original NOP verifier did not finish with genuine zero')
        trial = Path(native['nop']['trial'])
        logs = list((trial / 'verifier').glob('test-*.txt'))
        text = '\n'.join(p.read_text(errors='replace') for p in logs)
        missing = set(re.findall(r"ModuleNotFoundError: No module named ['\"]([^'\"]+)['\"]", text))
        if missing != expected_modules or not re.search(r'\d+ failed in ', text):
            raise ValueError('Raw log no longer matches reviewed executed-test failure')
        if any(value in text for value in ['ERROR collecting', 'ImportError while importing test module', 'No module named pytest']):
            raise ValueError('Verifier collection/dependency failure must remain failed')
        row = rows[ident]
        source = Path(row['source_path'])
        if sha(source / 'instruction.md') != row['instruction_sha256']:
            raise ValueError('Public assignment identity differs')
        admitted = nop[0]['admitted_task']
        for artifact in admitted['verifier_files']:
            if sha(Path(admitted['prepared_task_path']) / artifact['path']) != artifact['sha256']:
                raise ValueError('Original verifier bytes changed')
        item = dict(task_id=ident, pool='calibforge', status='ENV_READY', admitted_task=admitted,
            native_install_trial=native['install']['trial'], native_nop_trial=native['nop']['trial'], nop_reward=0,
            reviewed_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
            review_reason=reason, missing_modules=sorted(missing), prior_outcome=str(original), prior_outcome_sha256=sha(original),
            native_results=native, original_verifier_logs=[dict(path=str(p), sha256=sha(p)) for p in logs],
            teacher_success_not_implied=True, paid_attempts=0, task_modifications=0, raw_artifact_modifications=0,
            controller_admission='Pending explicit idle controller handoff; live r3 outcomes remain cached and unchanged')
        (destination / (ident + '.json')).write_text(json.dumps(item, indent=2))
        result.append(dict(task_id=ident, status='ENV_READY', nop_reward=0, reason=reason))
    (R / 'checks/native-nop-module-error-review-r10.json').write_text(json.dumps(dict(
        passed=True, reviews=result, reviewed_tasks=len(result), model_calls=0, original_result_modifications=0,
        controller_changes=0, original_task_modifications=0), indent=2))
    print(json.dumps(result))


if __name__ == '__main__':
    main()
