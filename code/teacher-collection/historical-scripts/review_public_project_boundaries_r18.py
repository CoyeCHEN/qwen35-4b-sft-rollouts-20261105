"""Classify three completed native17 NOPs against their public assignments.

This finite review changes no task, image, verifier, Result or teacher contract.
The official outer verifier executed all its tests; nested application failures
and the vendored dependency are the work explicitly assigned to the solver.
"""
import datetime
import hashlib
import json
from pathlib import Path
import re

import collection_readiness_r7 as n
from collection_attempts_r8 import attempt_counts
from collection_selection_r7 import active_rows


CASES = {
    'task_001025_8d13ffe8': {
        'public': ['Fix and Install the Vendored Dependency', '/app/annoy-1.17.3/setup.py', '/home/user/detector.py'],
        'log': ["No module named 'annoy'", 'FAILED test_final_state.py::test_annoy_installed_and_working', 'FAILED test_final_state.py::test_index_file_exists', 'FAILED test_final_state.py::test_detector_script_against_corpora'],
        'missing': ['annoy'],
        'reason': 'The public task explicitly requires fixing and installing vendored annoy, building the index and writing detector.py. The untouched workspace lacks those assigned outputs. The original outer verifier collected and ran all three tests and reported three assertion failures; annoy is the assigned broken dependency, not a missing verifier dependency.',
    },
    'task_004900_ebeb969a': {
        'public': ['/home/user/sensor_project', 'pytest tests/test_pipeline.py', 'src/math_utils.py', '/home/user/mre.py'],
        'log': ["No module named 'src'", "from src.pipeline import process_batch", 'FAILED test_final_state.py::test_bad_commit_hash', 'FAILED test_final_state.py::test_mre_script', 'FAILED test_final_state.py::test_pipeline_tests_pass'],
        'missing': ['src'],
        'reason': 'The failed src import belongs to the public sensor_project application test subprocess, which the assignment requires reproducing and fixing. It is nested inside the official final-state assertion. All three official outer verifier tests executed and failed on the unchanged application or missing assigned outputs. No third-party verifier import failed; the application import path is left for the solver.',
    },
    'task_005562_00c4dfae': {
        'public': ['Import Ordering Issue', '/home/user/project/test_main.py', 'Fix `test_main.py`', 'maturin build --release'],
        'log': ['TEST_MODE environment variable must be set before importing main in tests!', '/home/user/project/test_main.py:1:', 'FAILED test_final_state.py::test_pytest_passes', 'FAILED test_final_state.py::test_wheel_generated', 'FAILED test_final_state.py::test_symbols_extracted'],
        'missing': [],
        'reason': 'The collection error occurs inside public project/test_main.py and its main module, exactly the import-order bug the public assignment requires fixing. It is not collection of the official verifier. All three official final-state tests executed and failed on that assigned bug and missing wheel/symbol outputs. No TEST_MODE, source file, dependency or test is repaired by this review.',
    },
}


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
        source = Path(row['task_path'])
        instruction = (source / 'instruction.md').read_text()
        if any(value not in instruction for value in case['public']):
            raise ValueError('Public assignment boundary changed: ' + ident)
        prior = n.D / 'environment-failures' / (ident + '.json')
        rejection = json.loads(prior.read_text())
        if rejection['status'] != 'ENV_FAILED' or rejection['reason'] not in [
            'Verifier dependency/import origin requires trusted review; no teacher dispatch',
            'Original verifier collection failed without a missing public output module',
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
                if not re.search(r'^=+ 3 failed in [\d.]+s =+$', text, re.M):
                    raise ValueError('Official outer verifier did not execute all three tests')
                missing = set(re.findall(r"ModuleNotFoundError: No module named ['\"]([^'\"]+)['\"]", text))
                if missing != set(case['missing']):
                    raise ValueError('An unreviewed missing module exists')
                if 'No module named pytest' in text or 'command not found' in text:
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
        review = dict(task_id=ident, pool='tmax', status='ENV_READY',
            reviewed_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
            review_source=str(Path(__file__)), review_source_sha256=n.sha(Path(__file__)),
            missing_modules=case['missing'], prior_outcome=str(prior), prior_outcome_sha256=n.sha(prior),
            native_results=native, original_verifier_logs=[dict(path=str(q), sha256=n.sha(q)) for q in logs],
            public_instruction=str(source / 'instruction.md'), public_instruction_sha256=n.sha(source / 'instruction.md'),
            review_reason=case['reason'], official_outer_tests_executed=3,
            nested_application_failures_are_not_outer_verifier_collection_failures=True,
            model_calls=0, teacher_attempts_at_review=0, raw_failure_preserved=True,
            task_or_test_modifications=0, teacher_success_not_implied=True)
        n.freeze(review_file, review)
        ready = dict(task_id=ident, pool='tmax', status='ENV_READY', admitted_task=admitted,
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
    n.freeze(n.R / 'checks/public-project-boundary-reviews-r18.json', dict(
        status='THREE_COMPLETED_NATIVE17_CHECKS_RECLASSIFIED_FROM_PUBLIC_BOUNDARIES',
        tasks=results, model_calls=0, source_sha256=n.sha(Path(__file__)),
        original_failures_preserved=True, task_or_test_modifications=0))
    print(json.dumps(results))


if __name__ == '__main__':
    main()
