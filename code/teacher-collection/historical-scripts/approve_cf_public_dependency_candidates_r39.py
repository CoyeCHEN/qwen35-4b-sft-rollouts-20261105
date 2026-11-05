"""Approve exact native candidate evidence; publish no current-controller Ready."""
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import subprocess

import collection_readiness_r7 as n
from collection_attempts_r8 import attempt_counts
from collection_selection_r7 import active_rows


S = n.R / 'stream/cf-public-dependency-native-candidates-r37'


def main():
    plan_path = S / 'PLAN.json'
    plan = json.loads(plan_path.read_text())
    if n.sha(n.R / 'scripts/accept_cf_public_dependency_candidates149_r37.py') != plan['worker_source_sha256']:
        raise ValueError('Frozen native candidate worker changed')
    terminal = json.loads((S / 'TERMINAL.json').read_text())
    if Path('/proc/' + str(terminal['pid'])).exists() or terminal['terminal'] != terminal['planned']:
        raise ValueError('Observe the live native candidate worker')
    node_goal = n.NODE['ssd_root'] + '/cf-verifier-public-dependency-r36/public-cg-build-goal-source-proof-r39.json'
    public_goal = n.R / 'checks/public-cg-build-goal-source-proof-r39.json'
    if public_goal.exists():
        raise FileExistsError('Inspect the existing candidate approval, never replay blindly')
    subprocess.run(['rsync', '-a', '-e', shlex.join(n.DEPLOYMENT['ssh']),
        n.DEPLOYMENT['host'] + ':' + node_goal, str(public_goal)], check=True, timeout=60)
    goal_proof = json.loads(public_goal.read_text())
    if not goal_proof['passed'] or not goal_proof['original_and_candidate_goal_files_byte_identical']:
        raise ValueError('Public Goal source differs between original and candidate')
    rows = {row['task_id']:row for row in active_rows(attempt_counts())}
    approvals = []
    for item in plan['tasks']:
        ident = item['task_id']
        if attempt_counts().get(ident, 0):
            raise ValueError('A candidate Task has already been attempted')
        prior_path = S / 'candidate-outcomes' / (ident + '.json')
        prior = json.loads(prior_path.read_text())
        if prior['model_calls'] or prior['teacher_dispatches'] or prior['published_current_controller_ready']:
            raise ValueError('Native candidate scope was contaminated with teacher dispatch')
        build_path = Path(item['local_build_receipt'])
        if n.sha(build_path) != item['build_receipt_sha256']:
            raise ValueError('Exact native build receipt changed')
        built = json.loads(build_path.read_text())
        base = n.prepare_identity(rows[ident])
        nop = Path(prior['native_nop_trial'])
        cfg = json.loads((nop / 'config.json').read_text())
        prepared = Path(cfg['task']['path'])
        admitted = dict(base, prepared_task_path=str(prepared),
            prepared_task_toml_sha256=n.sha(prepared / 'task.toml'), image_id=built['image_id'],
            original_published_image_id=base['image_id'], explicit_public_verifier_dependency_candidate=True,
            candidate_build_receipt=str(build_path), candidate_build_receipt_sha256=n.sha(build_path))
        if cfg['environment']['kwargs'] != n.native_config(admitted, 'nop').environment.kwargs:
            raise ValueError('Original native Engine/socket/resources differ')
        instruction = prepared / 'instruction.md'
        if n.sha(instruction) != rows[ident]['instruction_sha256']:
            raise ValueError('Original public instruction changed')
        for artifact in base['verifier_files']:
            if n.sha(prepared / artifact['path']) != artifact['sha256']:
                raise ValueError('Official verifier/test member changed')
        native = {}
        for kind in ['install', 'nop']:
            trial = Path(prior['native_' + kind + '_trial'])
            raw = trial / 'result.json'
            if n.sha(raw) != prior[kind + '_result_sha256']:
                raise ValueError('Preserved native Result changed')
            result = json.loads(raw.read_text())
            if result.get('exception_info') or result.get('infrastructure_errors') or not result.get('finished_at'):
                raise ValueError('Native lifecycle failure cannot be approved')
            archive_path = S / 'ssd-trial-archives' / (trial.name + '.json')
            archived = json.loads(archive_path.read_text())
            if archived['result_sha256'] != n.sha(raw) or archived['node'] != '17' or archived['engine_id'] != n.NODE['engine_id']:
                raise ValueError('Native Result lacks matching SSD archive evidence')
            native[kind] = dict(trial=str(trial), result_sha256=n.sha(raw),
                node17_result=archived['authoritative_ssd_root'] + '/result.json',
                node17_archive_proof_sha256=n.sha(archive_path))
        result = json.loads((nop / 'result.json').read_text())
        reward = (result.get('verifier_result') or {}).get('rewards', {}).get('reward')
        if reward != 0 or not (result.get('verifier') or {}).get('finished_at'):
            raise ValueError('The unchanged official NOP verifier must complete with original zero')
        logs = sorted((nop / 'verifier').glob('test-*.txt'))
        text = '\n'.join(path.read_text(errors='replace') for path in logs)
        missing = set(re.findall(r"ModuleNotFoundError: No module named ['\"]([^'\"]+)['\"]", text))
        review = None
        if ident == 'optimization_20260604_194036_001':
            if prior['status'] != 'CANDIDATE_ENV_FAILED' or prior['reason'] != 'Verifier dependency/import origin requires trusted review; no teacher dispatch':
                raise ValueError('Unexpected original candidate boundary rejection')
            if missing != {'cg_solver_c'} or any(value not in instruction.read_text() for value in ['cg_solver.c', 'cg_solver.py', 'python3 setup.py build_ext --inplace']):
                raise ValueError('The missing extension is not the documented public build goal')
            if not re.search(r'^=+ 4 failed, 4 passed in [\d.]+s =+$', text, re.M):
                raise ValueError('All8 official tests did not actually execute')
            if any(value in text for value in ['ERROR collecting', 'ImportError while importing', 'No module named pytest', 'command not found']):
                raise ValueError('A verifier/bootstrap failure remains')
            if goal_proof['public_assigned_build_target'] != 'cg_solver_c' or {image['image_id'] for image in goal_proof['images']} != {base['image_id'], built['image_id']}:
                raise ValueError('Public build target proof belongs to another image pair')
            review = dict(task_id=ident, image_id=built['image_id'], original_image_id=base['image_id'],
                status='PUBLIC_COMPILED_GOAL_MODULE_REVIEWED_FOR_EXACT_CANDIDATE',
                missing_modules=['cg_solver_c'], official_outer_tests_executed=8,
                review_reason='The official verifier NumPy dependency now imports correctly. All8 tests executed; the missing cg_solver_c extension is the public solver build output. Its original setup.py and both CG source skeletons remain byte-identical in the original/candidate images. No compiled extension or CG implementation was installed by this environment correction.',
                public_goal_source_proof=str(public_goal), public_goal_source_proof_sha256=n.sha(public_goal),
                original_candidate_rejection=str(prior_path), original_candidate_rejection_sha256=n.sha(prior_path),
                original_verifier_logs=[dict(path=str(path), sha256=n.sha(path)) for path in logs],
                native_results=native, teacher_calls=0, current_controller_ready_publications=0)
            review_path = S / 'public-goal-boundary-reviews' / (ident + '.json')
            n.freeze(review_path, review)
        elif ident == 'system-administration_20260510_062946_002':
            if prior['status'] != 'NATIVE_CANDIDATE_ACCEPTED_PENDING_CONTROLLED_PROMOTION' or missing:
                raise ValueError('CA candidate did not pass the original strict native acceptance')
            review_path = None
        else:
            raise ValueError('Unexpected finite public dependency candidate')
        lineage_path = S / 'image-lineage-and-load' / (ident + '.json')
        lineage = json.loads(lineage_path.read_text())
        if not lineage['original_rootfs_diffid_prefix_preserved'] or not lineage['runtime_environment_config_unchanged']:
            raise ValueError('The candidate changed runtime or original image lineage')
        value = dict(task_id=ident, pool='calibforge', status='APPROVED_NATIVE_CANDIDATE_PENDING_CONTROLLED_CAMPAIGN_PROMOTION',
            reviewed_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
            review_source=str(Path(__file__)), review_source_sha256=n.sha(Path(__file__)),
            original_published_image_id=base['image_id'], image_id=built['image_id'],
            original_task_toml_sha256=rows[ident]['task_toml_sha256'], official_private_files=base['verifier_files'],
            original_public_instruction_sha256=rows[ident]['instruction_sha256'],
            admitted_task=admitted, native_results=native, nop_reward=0,
            original_candidate_outcome=str(prior_path), original_candidate_outcome_sha256=n.sha(prior_path),
            image_lineage_proof=str(lineage_path), image_lineage_proof_sha256=n.sha(lineage_path),
            original_base_layers_and_runtime_config_preserved=True,
            public_goal_boundary_review=str(review_path) if review_path else None,
            public_goal_boundary_review_sha256=n.sha(review_path) if review_path else None,
            archive=built['archive'], archive_sha256=built['archive_sha256'],
            image_audit=str(Path(built['archive']).parent / 'image-audit.json'),
            image_audit_sha256=built['image_audit_sha256'], build_receipt=str(build_path), build_receipt_sha256=n.sha(build_path),
            candidate_source_scope149_sha256=plan['source_scope149_sha256'],
            model_calls=0, teacher_dispatches=0, official_task_or_test_changes=0,
            published_current_controller_ready=False, teacher_success_not_implied=True)
        digest = hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()
        path = S / 'accepted-revisions' / ident / (digest + '.json')
        n.freeze(path, value)
        approvals.append(dict(task_id=ident, path=str(path), sha256=n.sha(path), approval=value))
    n.freeze(n.R / 'manifests/CF_PUBLIC_VERIFIER_DEPENDENCY_APPROVALS_R39.json', dict(
        status='NATIVE_ACCEPTED_IMAGE_SPECIFIC_ENVIRONMENT_CORRECTIONS_PENDING_CAMPAIGN_PROMOTION',
        tasks=approvals, engine_id=n.NODE['engine_id'], model_calls=0,
        current_controller_ready_publications=0, original_task_or_test_changes=0,
        source_sha256=n.sha(Path(__file__))))
    print(json.dumps(dict(approved_candidates=len(approvals), model_calls=0, current_controller_ready_publications=0)))


if __name__ == '__main__':
    for key in ['DEEPSEEK_API_KEY', 'OPENAI_API_KEY', 'GH_TOKEN']:
        os.environ.pop(key, None)
    os.environ['PATH'] = str(n.R / 'client-bin-v2') + ':' + os.environ['PATH']
    os.environ['SSH_AUTH_SOCK'] = '/home/chenkeyi/.local/share/harbor-rsi/near-r3-20261015/auth.sock'
    main()
