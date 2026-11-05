"""Review two completed native NOPs against their original public assignments.

No package installation, Task edits, teacher calls, or verifier reruns.
"""
import datetime
import hashlib
import json
from pathlib import Path
import re
import sys

import collection_readiness_r7 as n
from collection_attempts_r8 import attempt_counts
from collection_selection_r7 import active_rows


CASES = {
    'debugging_20260507_170244_001': dict(
        scope='native-verifier-timeout-recheck17-r24', missing='ringbuf', tests=20,
        public=['/app/ringbuf_src/', 'fix them', 'installed system-wide', 'import ringbuf'],
        log=['test_extension_imports', "ModuleNotFoundError: No module named 'ringbuf'"],
        reason='The public assignment requires repairing and installing the ringbuf C extension system-wide. '
        'All20 official tests executed and failed inside test bodies because that assigned extension is absent. '
        'The official system-Python pytest runner was available and completed. No extension was installed by this review.'),
    'task_000315_295b6f71': dict(
        scope='native-exact-archive-recheck17-r29', missing='patoolib', tests=2,
        public=['/app/patool-1.12', 'fix it, and install the package', '/home/user/safe_converter.py'],
        log=['test_patool_fixed_and_installed', "ModuleNotFoundError: No module named 'patoolib'", 'test_adversarial_corpus'],
        reason='The public assignment explicitly requires repairing the corrupted vendored patool library and installing it, '
        'then writing safe_converter.py. Both original final-state tests executed and failed in the unsolved workspace. '
        'The missing patoolib import is tested as solver output, not an unavailable verifier dependency. No library or converter was repaired by this review.'),
}


def main():
    rows = {row['task_id']: row for row in active_rows(attempt_counts())}
    reports = []
    for ident, case in CASES.items():
        if attempt_counts().get(ident, 0):
            raise ValueError('Never reclassify an already attempted Task: ' + ident)
        if n.blocking_review(ident):
            raise ValueError('Explicit negative source review remains: ' + ident)
        scope = n.R / 'stream' / case['scope']
        plan_path = scope / 'PLAN.json'
        plan = json.loads(plan_path.read_text())
        if plan['engine_id'] != n.NODE['engine_id'] or plan['model_calls'] != 0:
            raise ValueError('Native recheck belongs to another deployment')
        worker = n.R / 'scripts' / ('recheck_native_verifier_timeouts17_r24.py'
            if case['scope'].endswith('r24') else 'recheck_exact_original_archives17_r29.py')
        if n.sha(worker) != plan['source_sha256']:
            raise ValueError('Frozen native recheck worker changed')
        prior = scope / 'environment-outcomes' / (ident + '.json')
        rejection = json.loads(prior.read_text())
        if rejection['status'] != 'ENV_FAILED' or rejection['reason'] != 'Verifier dependency/import origin requires trusted review; no teacher dispatch':
            raise ValueError('Unexpected original native outcome')
        admitted = n.prepare_identity(rows[ident])
        prepared = Path(admitted['prepared_task_path'])
        public = prepared / 'instruction.md'
        instruction = public.read_text()
        if n.sha(public) != rows[ident]['instruction_sha256'] or any(x not in instruction for x in case['public']):
            raise ValueError('Public assignment identity/boundary changed')
        native = {}
        logs = []
        for kind in ['install', 'nop']:
            trial = Path(rejection['native_' + kind + '_trial'])
            if trial.parent != scope / 'trials':
                raise ValueError('Native Trial is outside the frozen recheck')
            result_path = trial / 'result.json'
            if n.sha(result_path) != rejection[kind + '_result_sha256']:
                raise ValueError('Preserved original native Result changed')
            result = json.loads(result_path.read_text())
            if result.get('exception_info') or result.get('infrastructure_errors') or not result.get('finished_at'):
                raise ValueError('Infrastructure failure cannot become an accepted NOP')
            dispatches = []
            for path in (scope / 'dispatches').glob('*/dispatch.json'):
                dispatch = json.loads(path.read_text())
                if dispatch['trial_name'] == trial.name and dispatch['task_id'] == ident and dispatch['kind'] == kind:
                    dispatches.append((path, dispatch))
            if len(dispatches) != 1:
                raise ValueError('Native dispatch identity is ambiguous')
            dispatch_path, dispatch = dispatches[0]
            config_path = dispatch_path.parent / 'trial-config.json'
            cfg = json.loads(config_path.read_text())
            if n.sha(config_path) != dispatch['config_sha256'] or dispatch['model_calls'] != 0:
                raise ValueError('Frozen zero-model dispatch changed')
            if cfg['environment']['kwargs'] != n.native_config(admitted, kind).environment.kwargs:
                raise ValueError('Native endpoint, socket or resources changed')
            if Path(cfg['task']['path']) != prepared:
                raise ValueError('Native recheck used another prepared Task')
            if kind == 'nop':
                reward = (result.get('verifier_result') or {}).get('rewards', {}).get('reward')
                if reward != 0 or not (result.get('verifier') or {}).get('finished_at'):
                    raise ValueError('Official NOP verifier must complete with original zero')
                logs = sorted((trial / 'verifier').glob('test-*.txt'))
                text = '\n'.join(p.read_text(errors='replace') for p in logs)
                missing = set(re.findall(r"ModuleNotFoundError: No module named ['\"]([^'\"]+)['\"]", text))
                if missing != {case['missing']} or any(x not in text for x in case['log']):
                    raise ValueError('Observed missing-module boundary changed')
                summary = r'^=+ ' + str(case['tests']) + r' failed in [\d.]+s =+$'
                if not re.search(summary, text, re.M):
                    raise ValueError('Original outer tests did not all execute')
                if any(x in text for x in ['ERROR collecting', 'ImportError while importing', 'command not found', 'No module named pytest']):
                    raise ValueError('An outer verifier/bootstrap failure remains')
            native[kind] = dict(trial=str(trial), result_sha256=n.sha(result_path),
                config=str(config_path), config_sha256=n.sha(config_path),
                dispatch=str(dispatch_path), dispatch_sha256=n.sha(dispatch_path))
        for artifact in admitted['verifier_files']:
            if n.sha(prepared / artifact['path']) != artifact['sha256']:
                raise ValueError('Official verifier changed')
        if attempt_counts().get(ident, 0):
            raise ValueError('Actual teacher admission happened during review')
        if '--validate-only' in sys.argv:
            reports.append(dict(task_id=ident, status='VALIDATED_NO_READY_PUBLICATION', tests=case['tests']))
            continue
        review_path = n.R / 'checks/native-environment-reviews-r10' / (ident + '.json')
        review = dict(task_id=ident, pool=rows[ident]['pool'], status='ENV_READY',
            reviewed_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
            review_source=str(Path(__file__)), review_source_sha256=n.sha(Path(__file__)),
            prior_outcome=str(prior), prior_outcome_sha256=n.sha(prior),
            native_recheck_plan=str(plan_path), native_recheck_plan_sha256=n.sha(plan_path),
            missing_modules=[case['missing']], native_results=native,
            public_instruction=str(public), public_instruction_sha256=n.sha(public),
            original_verifier_logs=[dict(path=str(p), sha256=n.sha(p)) for p in logs],
            review_reason=case['reason'], official_outer_tests_executed=case['tests'],
            model_calls=0, teacher_attempts_at_review=0, raw_failure_preserved=True,
            task_or_test_modifications=0, teacher_success_not_implied=True)
        n.freeze(review_path, review)
        ready = dict(task_id=ident, pool=rows[ident]['pool'], status='ENV_READY', admitted_task=admitted,
            engine_id=n.NODE['engine_id'], deployment_config_sha256=n.CONFIG_SHA,
            placement=admitted['deployment_assignment'], placement_sha256=admitted['deployment_assignment_sha256'],
            nop_reward=0, teacher_success_not_implied=True,
            raw_outcome=str(review_path), raw_outcome_sha256=n.sha(review_path))
        for kind in native:
            ready['native_' + kind + '_trial'] = native[kind]['trial']
            ready[kind + '_result_sha256'] = native[kind]['result_sha256']
        digest = hashlib.sha256(json.dumps(ready, sort_keys=True).encode()).hexdigest()
        destination = n.D / 'ready-revisions' / ident / (digest + '.json')
        n.freeze(destination, ready)
        reports.append(dict(task_id=ident, status='ENV_READY', review=str(review_path), ready=str(destination)))
    if '--validate-only' not in sys.argv:
        n.freeze(n.R / 'checks/public-native-recheck-boundary-reviews-r30.json', dict(
            status='PUBLIC_ASSIGNED_LIBRARY_IMPORTS_REVIEWED', tasks=reports,
            source_sha256=n.sha(Path(__file__)), model_calls=0,
            original_failures_preserved=True, task_or_test_modifications=0))
    print(json.dumps(reports))


if __name__ == '__main__':
    main()
