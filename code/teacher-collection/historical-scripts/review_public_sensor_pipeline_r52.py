"""Admit an unchanged Task whose original unsolved goal intentionally deadlocks.

The old NOP verifier timeout remains a timeout, with no Reward invented. Actual
teacher qualification still requires completed official verification/reward1.
"""
import ast
import datetime
import hashlib
import json
from pathlib import Path
import re
import sys
import tomllib

import collection_readiness_r9 as n
from collection_attempts_r8 import attempt_counts
from collection_selection_r7 import active_rows

IDENT = 'software-engineering_20260507_170334_011'


def read(path):
    return json.loads(path.read_bytes())


def main():
    if attempt_counts().get(IDENT, 0) or n.blocking_review(IDENT):
        raise ValueError('Review is restricted to the original unattempted/unblocked Task')
    row = next(item for item in active_rows(attempt_counts()) if item['task_id'] == IDENT)
    admitted = n.prepare_identity(row)
    task = Path(admitted['prepared_task_path'])
    public = task / 'instruction.md'
    instruction = public.read_text()
    if n.sha(public) != row['instruction_sha256'] or not all(text in instruction for text in
        ['sensor_pipeline.py', 'hangs', 'mp.Process', 'mp.Queue()', '20']):
        raise ValueError('The public deadlock assignment changed')
    references = {}
    for scope, worker in [('native-verifier-timeout-recheck17-r24', 'recheck_native_verifier_timeouts17_r24.py'),
        ('cf-public-verifier-bootstrap17-r50', 'probe_cf_public_verifier_bootstrap17_r50.py')]:
        plan = n.R / 'stream' / scope / 'PLAN.json'
        value = read(plan)
        if value['engine_id'] != n.NODE['engine_id'] or value['model_calls'] != 0:
            raise ValueError('Diagnostic engine/model boundary differs')
        if n.sha(n.R / 'scripts' / worker) != value['source_sha256']:
            raise ValueError('Frozen diagnostic source changed')
        references[scope] = dict(plan=str(plan), plan_sha256=n.sha(plan), source_sha256=value['source_sha256'])
    prior = n.R / 'stream/native-verifier-timeout-recheck17-r24/environment-outcomes' / (IDENT + '.json')
    original = read(prior)
    native = {}
    for kind in ['install', 'nop']:
        trial = Path(original['native_' + kind + '_trial'])
        result_path = trial / 'result.json'
        result = read(result_path)
        if n.sha(result_path) != original[kind + '_result_sha256'] or not result['finished_at'] or result.get('infrastructure_errors'):
            raise ValueError('Original native result/cleanup identity differs')
        config = result['config']
        if Path(config['task']['path']) != task or config['environment']['kwargs'] != n.native_config(admitted, kind).environment.kwargs:
            raise ValueError('The existing native acceptance used another Task/deployment')
        exception = (result.get('exception_info') or {}).get('exception_type')
        if kind == 'install' and (exception or not config['install_only']):
            raise ValueError('CLI installation did not finish normally')
        if kind == 'nop' and (exception != 'VerifierTimeoutError' or result.get('verifier_result') is not None):
            raise ValueError('Do not rewrite an existing NOP result or invent Reward')
        native[kind] = dict(trial=str(trial), result_sha256=n.sha(result_path), exception_type=exception)
    goal = n.R / 'stream/cf-public-verifier-bootstrap17-r50/probes' / IDENT
    collection = n.R / 'stream/cf-public-verifier-bootstrap17-r50/probes' / IDENT
    for directory in [goal]:
        probe = read(directory / 'PROBE.json')
        if not probe['native_cleanup_completed'] or {step['name']:step['return_code'] for step in probe['steps']}!={'original_public_bootstrap_only':0,'trusted_official_test_collection':0,'public_assigned_hang_reproduction':124,'no_reward_written':0}:
            raise ValueError('A public/trusted diagnostic did not complete/clean normally')
        if probe['official_verifier_runs'] != 0:
            raise ValueError('Test discovery must not manufacture an official Reward')
        if read(directory / 'environment.json')['image_id'] != admitted['image_id']:
            raise ValueError('Diagnostic image differs from the unchanged original')
    contention_file = goal / 'public_assigned_hang_reproduction-stderr.txt'
    text=contention_file.read_text()
    if not all(marker in text for marker in ['Generated 20 readings','Processing 20 readings in parallel','Waiting for workers to finish...']):
        raise ValueError('The unchanged public pipeline did not reach its reported waiting state')
    contention=dict(bounded_public_goal_timeout_seconds=15,observed_waiting_for_workers=True,
        meaning='Original public Goal still waiting after the bounded diagnostic; original full NOP300s timeout remains preserved. This is not a completed verifier or Reward0.')
    collected = collection / 'trusted_official_test_collection-stdout.txt'
    if not re.search(r'^8 tests collected in [\d.]+s$', collected.read_text(), re.M):
        raise ValueError('All original official tests were not discovered normally')
    for artifact in admitted['verifier_files']:
        if n.sha(task / artifact['path']) != artifact['sha256']:
            raise ValueError('Official verifier bytes differ')
    final_test = task / 'tests/test_outputs.py'
    tree = ast.parse(final_test.read_bytes())
    if len([node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name.startswith('test_')]) != 8:
        raise ValueError('Official test item count changed')
    if not any(isinstance(node,ast.Constant) and node.value=='/app/sensor_pipeline.py' for node in ast.walk(tree)):
        raise ValueError('Original tests no longer refer to the publicly assigned pipeline')
    if tomllib.loads((task / 'task.toml').read_text())['environment']['docker_image'] != admitted['image_id']:
        raise ValueError('Original image pin changed')
    if attempt_counts().get(IDENT, 0):
        raise ValueError('A teacher attempt started during review')
    if '--validate-only' in sys.argv:
        print(json.dumps(dict(task_id=IDENT, validated=True, ready_published=False, official_reward_invented=False)))
        return
    review_path = n.R / 'checks/public-sensor-pipeline-readiness-review-r52.json'
    review = dict(task_id=IDENT, pool='calibforge', status='ENV_READY', reviewed_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        source_sha256=n.sha(Path(__file__)), prior_outcome=str(prior), prior_outcome_sha256=n.sha(prior),
        public_instruction=str(public), public_instruction_sha256=n.sha(public), original_image_id=admitted['image_id'],
        native_results=native, diagnostic_plans=references,
        contention_evidence=str(contention_file), contention_evidence_sha256=n.sha(contention_file), contention=contention,
        official_test_collection=str(collected), official_test_collection_sha256=n.sha(collected),
        official_test_discovery_count=8, original_nop_verifier_completed=False, original_nop_reward=None,
        task_goal_repairs=0, official_task_or_test_changes=0, original_resource_or_deadline_changes=0,
        model_calls=0, teacher_attempts_before_review=0,
        review_reason='The public Task explicitly requires fixing the multiprocessing Queue hang without replacing its architecture. On17 the unchanged public verifier bootstrap completed in33.87s and all8 original tests loaded. The original pipeline reached Waiting for workers to finish and exceeded the bounded15s diagnostic; the old full NOP300s timeout is retained with no Reward. No Goal, official tests, resources or deadlines changed. This Ready permits the first teacher attempt; qualified success still needs actual completed official reward1 and all Recorder/Qwen audits.')
    n.freeze(review_path, review)
    ready = dict(task_id=IDENT, pool='calibforge', status='ENV_READY', admitted_task=admitted,
        engine_id=n.NODE['engine_id'], deployment_config_sha256=n.CONFIG_SHA,
        placement=admitted['deployment_assignment'], placement_sha256=admitted['deployment_assignment_sha256'],
        raw_outcome=str(review_path), raw_outcome_sha256=n.sha(review_path),
        reason=review['review_reason'], nop_reward=None, original_nop_verifier_completed=False, preflight_exception='PUBLICLY_ASSIGNED_UNSOLVED_DEADLOCK',
        teacher_success_not_implied=True)
    for kind, item in native.items():
        ready['native_' + kind + '_trial'] = item['trial']
        ready[kind + '_result_sha256'] = item['result_sha256']
    digest = hashlib.sha256(json.dumps(ready, sort_keys=True).encode()).hexdigest()
    path = n.D / 'ready-revisions' / IDENT / (digest + '.json')
    n.freeze(path, ready)
    print(json.dumps(dict(task_id=IDENT, ready=str(path), raw_nop_timeout_preserved=True, teacher_calls=0)))


if __name__ == '__main__':
    main()
