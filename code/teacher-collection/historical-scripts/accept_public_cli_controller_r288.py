"""Validate the exact setup-only deployment delta before any new authority."""
import ast
from collections import Counter
import datetime
import json
from pathlib import Path

import collection_readiness_r19 as old
import collection_readiness_r20 as new
from collection_attempts_r8 import attempt_counts
from collection_selection_r7 import active_rows
import run_collection_stream_r20 as controller

R = new.R


def main():
    runtime = controller.validate_controller_runtime()
    if new.NODE != old.NODE or new.DEPLOYMENT['environment'] != old.DEPLOYMENT['environment']:
        raise ValueError('Engine, SSD storage or native environment changed')
    for key in ['task_public_dependencies', 'task_runtime_initialization', 'public_verifier_dependency_approvals149', 'public_image_bindings_mirror149', 'dependency_override', 'dependency_override_sha256', 'native_client_bin', 'native_client_ssh_sha256', 'native_ssh_pool', 'teacher_limit', 'hot_setup_buffer', 'native_lifecycle_capacity', 'preparation_concurrency']:
        if old.DEPLOYMENT[key] != new.DEPLOYMENT[key]:
            raise ValueError('Unrelated deployment delta: ' + key)
    bootstrap = new.DEPLOYMENT['public_cli_bootstrap']
    for key in ['compose', 'script', 'native_acceptance']:
        if new.sha(Path(bootstrap[key])) != bootstrap[key + '_sha256']:
            raise ValueError('Accepted public bootstrap changed')
    native = json.loads(Path(bootstrap['native_acceptance']).read_text())
    if native['status'] != 'ENV_READY' or native['model_calls'] != 0 or native['teacher_dispatches'] != 0:
        raise ValueError('Prototype is not a terminal zero-model native acceptance')
    results = {}
    for kind in ['install', 'nop']:
        trial = Path(native['native_' + kind + '_trial'])
        path = trial / 'result.json'
        if new.sha(path) != native[kind + '_result_sha256']:
            raise ValueError('Original native Result changed')
        value = json.loads(path.read_text())
        if not value['finished_at'] or value.get('exception_info') or value['infrastructure_errors']:
            raise ValueError('Native lifecycle did not finish cleanly')
        if not value['agent_setup']['finished_at']:
            raise ValueError('Original native CLI setup did not finish')
        if kind == 'nop':
            new.verify_nop(type('Result', (), {'exception_info': None, 'infrastructure_errors': []})(), trial, native['admitted_task'])
            receipt = json.loads((trial / 'agent/public-cpython-bootstrap-r273.json').read_text())
            if not receipt['passed'] or receipt['cache_base'] != bootstrap['cache_base'] or receipt['model_calls'] or receipt['model_proxy_changes']:
                raise ValueError('Public original cache was not actually used')
            if receipt['uv_sha256'] != '3e801df892439f5cde65d8b51ea69b69abff199ef37cc3cae4481be15d592df0' or receipt['original_cpython_archive_sha256'] != '1dbaa624a09e15afe7efbdac08d42993135a68db8d34f986ef6977a6d77bdc3c':
                raise ValueError('Public cache byte identity differs')
        results[kind] = dict(trial=str(trial), result_sha256=new.sha(path))
    before = ast.parse((R / 'scripts/run_collection_stream_r19.py').read_text())
    after = ast.parse((R / 'scripts/run_collection_stream_r20.py').read_text().replace("'r20'", "'r19'"))
    def callbacks(tree):
        parent = next(x for x in tree.body if isinstance(x, ast.AsyncFunctionDef) and x.name == 'main')
        return {x.name: ast.dump(x, include_attributes=False) for x in parent.body if isinstance(x, ast.AsyncFunctionDef) and x.name in ['admitted_teacher', 'ended_agent', 'ended_teacher', 'stage', 'diagnostic', 'prepare']}
    if callbacks(before) != callbacks(after):
        raise ValueError('Native admission, budget, setup or lifecycle callbacks changed')
    source = R / 'scripts/run_collection_stream_r20.py'
    phase = R / 'checks/controller-r20-agent-phase-acceptance-r275.json'
    if not json.loads(phase.read_text())['passed'] or json.loads(phase.read_text())['controller_source_sha256'] != new.sha(source):
        raise ValueError('Native phase acceptance is stale')
    counts = attempt_counts()
    rows = active_rows(counts)
    accepted={}
    for root in old.readiness_roots():
        for path in [*sorted((root/'environment-outcomes').glob('*.json')),*sorted((root/'ready-revisions').glob('*/*.json'))]:
            value=json.loads(path.read_text())
            if value['status']!='ENV_READY':continue
            if value['task_id'] in old.DEPLOYMENT['new_native_acceptance_required_task_ids'] and value.get('deployment_config_sha256')!=old.CONFIG_SHA:continue
            value=old.normalize_ready(value,path)
            for kind in ['install','nop']:
                if old.sha(Path(value['native_'+kind+'_trial'])/'result.json')!=value[kind+'_result_sha256']:raise ValueError('Original native Ready Result changed')
            accepted[value['task_id']]=value
    checked = Counter()
    historical_not_migrated=[]
    for row in rows:
        if row['task_id'] not in accepted:

            if not counts.get(row['task_id'],0):raise ValueError('Unattempted Task lacks an accepted original source')
            historical_not_migrated.append(dict(task_id=row['task_id'],pool=row['pool'],attempt_budget_used=counts[row['task_id']],reason='Already-attempted historical Task without a17 materialization receipt; never replay for deployment validation'))
            continue
        admitted=accepted[row['task_id']]['admitted_task']
        task=Path(admitted['prepared_task_path'])
        if new.sha(task/'task.toml')!=admitted['prepared_task_toml_sha256'] or new.sha(task/'instruction.md')!=row['instruction_sha256']:raise ValueError('Frozen accepted Task changed')
        for artifact in admitted['verifier_files']:
            if new.sha(task/artifact['path'])!=artifact['sha256']:raise ValueError('Official accepted Verifier changed')
        for kind in ['teacher', 'install', 'nop']:
            a = old.native_config(admitted, kind).model_dump(mode='json')
            b = new.native_config(admitted, kind).model_dump(mode='json')
            a.pop('trial_name'); b.pop('trial_name')
            if row['pool'] == bootstrap['pool']:
                added = b['environment']['extra_docker_compose'].pop()
                if added != bootstrap['compose']:
                    raise ValueError('Public bootstrap is absent from the new native config')
            if a != b:
                raise ValueError('Native Task/Agent/Verifier config changed beyond the declared setup: ' + row['task_id'])
        checked[row['pool']] += 1
    if sum(checked.values())+len(historical_not_migrated)!=1000 or len(rows)!=1000:raise ValueError('Fixed selected scope changed')
    promoted = new.normalize_ready(native, Path(bootstrap['native_acceptance']))
    promoted.update(raw_outcome=bootstrap['native_acceptance'], raw_outcome_sha256=bootstrap['native_acceptance_sha256'], prototype_admission_changed=False)
    ready = new.D / 'ready-revisions/public-cli-r274' / (native['task_id'] + '.json')
    new.freeze(ready, promoted)
    proof = dict(passed=True, checked_at=datetime.datetime.now(datetime.timezone.utc).isoformat(), controller_source_sha256=new.sha(source), deployment_config_sha256=new.CONFIG_SHA, old_deployment_config_sha256=old.CONFIG_SHA, controller_runtime=runtime, native_results=results, public_cache=receipt, current17_tasks_config_compared=dict(checked),historical_not_migrated=historical_not_migrated, native_configs_compared=sum(checked.values()) * 3, original_task_agent_verifier_resources_deadlines_and_model_contract_unchanged=True, exact_native_callbacks_unchanged=True, qualified_success_not_implied=True, ready_receipt=str(ready), ready_receipt_sha256=new.sha(ready), helper_sha256={name:new.sha(R / 'scripts' / name) for name in ['run_collection_stream_r20.py','collection_readiness_r20.py','collection_readiness_r19.py','collection_attempts_r8.py','collection_selection_r7.py']}, model_calls=0, teacher_admission_granted=False, source_sha256=new.sha(Path(__file__)))
    new.freeze(R / 'checks/controller-r20-offline-acceptance-r288.json', proof)
    print(json.dumps(proof))


if __name__ == '__main__':
    main()
