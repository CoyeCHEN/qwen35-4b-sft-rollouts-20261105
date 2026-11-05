"""Classify four remaining completed native17 NOPs against their public assignments.

This finite review changes no task, image, verifier, Result or teacher contract.
The official outer verifier executed all its tests; nested application failures
and the vendored dependency are the work explicitly assigned to the solver.
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


CASES = {'software-engineering_20260414_091921_009': {'public': ['/app/datatool',
                                                         'datatool',
                                                         'dt-inspect',
                                                         'dt-transform',
                                                         'Fix the packaging configuration'],
                                              'log': ['datatool command not found in PATH',
                                                      'dt-inspect command not found in PATH',
                                                      'dt-transform command not found in PATH'],
                                              'missing': [],
                                              'commands': ['datatool', 'dt-inspect', 'dt-transform'],
                                              'outer': '7 failed',
                                              'reason': 'The public datatool assignment explicitly requires '
                                                        'repairing dynamically registered datatool, '
                                                        'dt-inspect and dt-transform entry points. Their '
                                                        'absence is the starting task state. All seven '
                                                        'official tests executed with assertion failures; '
                                                        'the official verifier and its dependencies ran. No '
                                                        'CLI is installed and no task or official resource '
                                                        'is changed by this review.'},
 'software-engineering_20260413_174325_009': {'public': ['/app/datatools',
                                                         'datatools-csv-process',
                                                         'datatools-json-format',
                                                         'datatools-xml-validate',
                                                         'Fix the package'],
                                              'log': ['datatools-csv-process command not found',
                                                      'datatools-json-format command not found',
                                                      'datatools-xml-validate command not found'],
                                              'missing': [],
                                              'commands': ['datatools-csv-process',
                                                           'datatools-json-format',
                                                           'datatools-xml-validate'],
                                              'outer': '6 failed',
                                              'reason': 'The public datatools task explicitly assigns fixing '
                                                        'three missing package CLI entry points. All six '
                                                        'official verifier tests executed and failed on this '
                                                        'unchanged unsolved package state. The missing '
                                                        'commands are public task outputs, not verifier '
                                                        'executables. No task, package, image, test or '
                                                        'reward is changed.'},
 'software-engineering_20260413_173854_019': {'public': ['datacli-process-data',
                                                         'datacli-validate',
                                                         'datacli-inspect',
                                                         'Fix the project'],
                                              'log': ['datacli-process-data command not found in PATH',
                                                      'datacli-validate command not found in PATH',
                                                      'datacli-inspect command not found in PATH'],
                                              'missing': [],
                                              'commands': ['datacli-process-data',
                                                           'datacli-validate',
                                                           'datacli-inspect'],
                                              'outer': '7 failed',
                                              'reason': 'The public datacli assignment expressly describes '
                                                        'three missing shell commands and requires '
                                                        'correcting hybrid package entry-point discovery. '
                                                        'All seven official verifier tests executed with '
                                                        'assertion failures in the unsolved original '
                                                        'workspace. No verifier executable is missing; no '
                                                        'package configuration or official test is edited.'},
 'machine-learning_20260607_104421_001': {'public': ['Build XGBoost version 1.7.0 from source',
                                                     'install the Python package from the built source',
                                                     '/app/model.json'],
                                          'log': ["ModuleNotFoundError: No module named 'xgboost'"],
                                          'missing': ['xgboost'],
                                          'commands': [],
                                          'outer': '4 failed',
                                          'reason': 'The public assignment explicitly requires building '
                                                    'XGBoost1.7.0 from source and installing its Python '
                                                    'package before training and saving the requested model. '
                                                    'Its absence in NOP is the assigned initial installation '
                                                    'state. All four official verifier tests executed with '
                                                    'assertion failures; no official verifier collection '
                                                    'failure occurred. This review installs nothing and '
                                                    'changes no task, tests, image or reward.'}}


def main():
    counts = attempt_counts()
    rows = {row['task_id']: row for row in active_rows(counts)}
    dispatches = [p for p in (n.R / 'stream/collection-r4/dispatches').glob('*/dispatch.json')]
    results = []
    for ident, case in CASES.items():
        if counts.get(ident, 0) or attempt_counts().get(ident, 0):
            raise ValueError('Review only a never-attempted Task: ' + ident)
        if n.blocking_review(ident):
            raise ValueError('An explicit trusted negative boundary review remains')
        row = rows[ident]
        admitted = n.prepare_identity(row)
        source = Path(row['source_path'] if row['pool']=='calibforge' else row['task_path'])
        instruction = (source / 'instruction.md').read_text()
        if any(value not in instruction for value in case['public']):
            raise ValueError('Public assignment boundary changed: ' + ident)
        prior = next(p for root in [n.R/'stream/collection-r4/deployment-r8',n.D] if (p:=root/'environment-failures'/(ident+'.json')).exists())
        rejection = json.loads(prior.read_text())
        if rejection['status'] != 'ENV_FAILED' or rejection['reason'] not in [
            'Verifier dependency/import origin requires trusted review; no teacher dispatch',
            'Original verifier collection failed without a missing public output module',
            'Original verifier executable/dependency failed to start',
        ]:
            raise ValueError('Unexpected original rejection')
        native = {}
        logs = []
        for p in dispatches:
            dispatch = json.loads(p.read_text())
            kind = dispatch['kind']
            if dispatch.get('task_id') != ident or kind not in ['install', 'nop']:
                continue
            cfg_path = p.parent / 'trial-config.json'
            cfg = json.loads(cfg_path.read_text())
            if cfg['environment']['kwargs'].get('project_namespace') != n.DEPLOYMENT['environment']['kwargs']['project_namespace']:
                continue
            if kind in native:
                raise ValueError('Ambiguous current17 native check')
            if n.sha(cfg_path) != dispatch['config_sha256']:
                raise ValueError('Native Trial configuration changed')
            if cfg['environment']['kwargs'] != n.native_config(admitted, kind).environment.kwargs:
                raise ValueError('Native check belongs to another deployment')
            if Path(cfg['task']['path']) != Path(admitted['prepared_task_path']):
                raise ValueError('Native check used a different prepared Task')
            trial = n.R / 'stream/collection-r4/trials' / dispatch['trial_name']
            result_path = trial / 'result.json'
            result = json.loads(result_path.read_text())
            if result.get('exception_info') or result.get('infrastructure_errors') or not result.get('finished_at'):
                raise ValueError('Lifecycle infrastructure failure cannot be reclassified')
            if kind == 'nop':
                reward = (result.get('verifier_result') or {}).get('rewards', {}).get('reward')
                if reward != 0 or not (result.get('verifier') or {}).get('finished_at'):
                    raise ValueError('Original official NOP verifier did not finish with zero')
                logs = list((trial / 'verifier').glob('test-*.txt'))
                text = '\n'.join(q.read_text(errors='replace') for q in logs)
                if any(value not in text for value in case['log']):
                    raise ValueError('Observed failure differs from the reviewed public boundary')
                if not re.search(r'^=+ '+re.escape(case['outer'])+r' in [\d.]+s =+$', text, re.M):
                    raise ValueError('Official outer verifier did not execute all three tests')
                missing = set(re.findall(r"ModuleNotFoundError: No module named ['\"]([^'\"]+)['\"]", text))
                if missing != set(case['missing']):
                    raise ValueError('An unreviewed missing module exists')
                if 'No module named pytest' in text or 'ERROR collecting' in text or any('command not found' in line and not any(name in line for name in case['commands']) for line in text.splitlines()):
                    raise ValueError('Verifier executable is unavailable')
            native[kind] = dict(trial=str(trial), result_sha256=n.sha(result_path),
                config=str(cfg_path), config_sha256=n.sha(cfg_path))
        if set(native) != {'install', 'nop'}:
            raise ValueError('Both completed original native17 checks are required')
        for artifact in admitted['verifier_files']:
            if n.sha(Path(admitted['prepared_task_path']) / artifact['path']) != artifact['sha256']:
                raise ValueError('Official verifier changed')
        if attempt_counts().get(ident, 0):
            raise ValueError('Task was attempted during review')
        review_file = n.R / 'checks/native-environment-reviews-r10' / (ident + '.json')
        review = dict(task_id=ident, pool=row['pool'], status='ENV_READY',
            reviewed_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
            review_source=str(Path(__file__)), review_source_sha256=n.sha(Path(__file__)),
            missing_modules=case['missing'], prior_outcome=str(prior), prior_outcome_sha256=n.sha(prior),
            native_results=native, original_verifier_logs=[dict(path=str(q), sha256=n.sha(q)) for q in logs],
            public_instruction=str(source / 'instruction.md'), public_instruction_sha256=n.sha(source / 'instruction.md'),
            controller_admission='Reuse completed current17 native checks; sole R8 controller retains normal teacher admission, budget and success audits',
            review_reason=case['reason'], official_outer_tests_executed=int(case['outer'].split()[0]),
            nested_application_failures_are_not_outer_verifier_collection_failures=True,
            model_calls=0, teacher_attempts_at_review=0, raw_failure_preserved=True,
            task_or_test_modifications=0, teacher_success_not_implied=True)
        if '--validate-only' in sys.argv:
            results.append(dict(task_id=ident,status='VALIDATED_NO_READY_PUBLICATION',prior_outcome=str(prior)))
            continue
        n.freeze(review_file, review)
        ready = dict(task_id=ident, pool=row['pool'], status='ENV_READY', admitted_task=admitted,
            engine_id=n.NODE['engine_id'], deployment_config_sha256=n.CONFIG_SHA,
            placement=admitted['deployment_assignment'], placement_sha256=admitted['deployment_assignment_sha256'],
            nop_reward=0, teacher_success_not_implied=True,
            raw_outcome=str(review_file), raw_outcome_sha256=n.sha(review_file))
        for kind in ['install', 'nop']:
            ready['native_' + kind + '_trial'] = native[kind]['trial']
            ready[kind + '_result_sha256'] = native[kind]['result_sha256']
        digest = hashlib.sha256(json.dumps(ready, sort_keys=True).encode()).hexdigest()
        destination = n.D / 'ready-revisions' / ident / (digest + '.json')
        n.freeze(destination, ready)
        results.append(dict(task_id=ident, status='ENV_READY', review=str(review_file), ready=str(destination)))
    if '--validate-only' in sys.argv:
        print(json.dumps(results))
        return
    n.freeze(n.R / 'checks/public-assigned-output-boundary-reviews-r22.json', dict(
        status='FOUR_REMAINING_NATIVE17_CHECKS_RECLASSIFIED_FROM_PUBLIC_BOUNDARIES',
        tasks=results, model_calls=0, source_sha256=n.sha(Path(__file__)),
        original_failures_preserved=True, task_or_test_modifications=0))
    print(json.dumps(results))


if __name__ == '__main__':
    main()
