"""Validate native restart wiring and administrative rejection semantics without a teacher."""
import ast
import asyncio
from collections import Counter
import copy
import datetime
import json
from pathlib import Path
from types import SimpleNamespace

import collection_readiness_r21 as old
import collection_readiness_r22 as new
import run_collection_stream_r22 as controller
from collection_attempts_r8 import attempt_counts
from collection_selection_r7 import active_rows
from collection_current_setup_blocks_r293 import current_setup_blocks
from collection_administrative_ready_r427 import reconcile

R = new.R


def function(tree, name):
    return next(node for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name)


def dump(value):
    if isinstance(value, list):
        value = ast.Module(body=value, type_ignores=[])
    return ast.dump(value, include_attributes=False)


async def check_stage(source, fixtures):
    stage = copy.deepcopy(function(ast.parse(source.read_text()), 'stage'))
    registry = json.loads((R / 'checks/ADMINISTRATIVE_READY_RECONCILIATION_R423.json').read_text())
    cases = []
    originals = {}
    for ident, receipt in registry['cases'].items():
        accepted = json.loads(Path(receipt['receipt']).read_text())
        path = Path(accepted['administrative_admission_reconciliation']['original_administrative_result'])
        raw = json.loads(path.read_text())
        originals[str(path)] = new.sha(path)
        cases.append((ident, raw, False, True))
    reference = copy.deepcopy(cases[0][1])
    for message in ['Authorized teacher budget exhausted', 'Sampling slot changed before agent admission']:
        value = copy.deepcopy(reference)
        value['exception_info']['exception_message'] = message
        cases.append((message, value, False, True))
    unknown = copy.deepcopy(reference)
    unknown['exception_info']['exception_message'] = 'Unreviewed environment initialization failure'
    executed = copy.deepcopy(reference)
    executed['agent_execution'] = {'started_at': '2026-10-31T22:00:00+00:00'}
    infrastructure = copy.deepcopy(reference)
    infrastructure['exception_info']['exception_type'] = 'RemoteDockerError'
    cases += [('unknown-value-error', unknown, False, False), ('execution-present', executed, False, False),
        ('recorder-present', reference, True, False), ('actual-infrastructure', infrastructure, False, False)]
    observations = []
    for ordinal, (label, raw, recorded, administrative) in enumerate(cases):
        root = fixtures / str(ordinal)
        stream, destination = root / 'stream', root / 'controller'
        trial_name = 'isolated-test-' + str(ordinal)
        trial = stream / 'trials' / trial_name
        trial.mkdir(parents=True)
        destination.mkdir()
        (trial / 'result.json').write_text(json.dumps(raw))
        (destination / 'DRAIN_REQUESTED.json').write_text('{"isolated_test":true}')
        if recorded:
            journal = trial / 'agent/openharness-rollout/events.jsonl'
            journal.parent.mkdir(parents=True)
            journal.write_text('{}\n')
        cfg = SimpleNamespace(trial_name=trial_name, model_dump_json=lambda **kwargs: '{"isolated_test":true}')
        ready = dict(status='ENV_READY', unchanged_proof='identity-checked-original')
        outcomes = {'fixture-task': copy.deepcopy(ready)}
        blocks, archiving, releasing = [], {}, {}
        async def submit(config):
            return SimpleNamespace()
        async def nothing(*args):
            return None
        namespace = dict(S=stream, D=destination, Path=Path, uuid4=__import__('uuid').uuid4,
            read=controller.read, freeze=controller.freeze, sha=controller.sha,
            administrative_admission_rejection=controller.administrative_admission_rejection,
            config=lambda row, kind: cfg, stage_rows={}, teacher_queue=SimpleNamespace(submit=submit),
            archiving=archiving, persist_trial=nothing, admitted_names=set(), outcomes=outcomes,
            block_current_readiness=lambda ident: blocks.append(ident), releasing=releasing,
            release=nothing, asyncio=asyncio, save=lambda *args: (_ for _ in ()).throw(AssertionError('Unexpected stage exception')))
        module = ast.Module(body=[stage], type_ignores=[])
        ast.fix_missing_locations(module)
        exec(compile(module, str(source), 'exec'), namespace)
        await namespace['stage'](dict(task_id='fixture-task', pool='tmax'))
        await asyncio.gather(*archiving.values(), *releasing.values())
        administrative_files = list((destination / 'administrative-admission-rejections').glob('*.json'))
        failures = list((destination / 'setup-failures').glob('*.json'))
        if administrative:
            assert len(administrative_files) == 1 and not failures and not blocks and outcomes['fixture-task'] == ready
        else:
            assert not administrative_files and len(failures) == 1 and blocks == ['fixture-task']
            assert outcomes['fixture-task']['status'] == 'ENV_BLOCKED'
        observations.append(dict(case=label, administrative=administrative, passed=True))
    assert all(new.sha(Path(path)) == digest for path, digest in originals.items())
    return observations


def main():
    before_counts = attempt_counts()
    runtime = controller.validate_controller_runtime()
    allowed = {'revision','deployment_revision','readiness_root','controller_root','previous_deployment_config',
        'previous_deployment_config_sha256','legacy_readiness','new_native_acceptance_required_task_ids'}
    changed = {key for key in old.DEPLOYMENT if old.DEPLOYMENT[key] != new.DEPLOYMENT[key]}
    assert changed <= allowed and set(old.DEPLOYMENT) == set(new.DEPLOYMENT)
    assert old.NODE == new.NODE and old.DEPLOYMENT['environment'] == new.DEPLOYMENT['environment']
    assert new.DEPLOYMENT['new_native_acceptance_required_task_ids'] == []
    assert new.DEPLOYMENT['legacy_readiness']['sha256'] == old.CONFIG_SHA
    source = R / 'scripts/run_collection_stream_r22.py'
    phase = R / 'checks/controller-r22-agent-phase-acceptance-r442.json'
    assert json.loads(phase.read_text())['passed'] and json.loads(phase.read_text())['controller_source_sha256'] == new.sha(source)
    before = ast.parse((R / 'scripts/run_collection_stream_r21.py').read_text())
    after = ast.parse(source.read_text().replace("'r22'", "'r21'"))
    for name in ['ended_agent','ended_teacher','prepare','diagnostic','resident','release','persist_trial','warm']:
        assert dump(function(before, name)) == dump(function(after, name)), name
    admitted = copy.deepcopy(function(before, 'admitted_teacher'))
    admitted.body = [stmt for stmt in admitted.body if not (isinstance(stmt, ast.If)
        and any(isinstance(node, ast.Name) and node.id == 'legacy_reader_alive' for node in ast.walk(stmt)))]
    # The removed reader check is nested in the existing native try block.
    for node in ast.walk(admitted):
        if isinstance(node, ast.Try):
            node.body = [stmt for stmt in node.body if not (isinstance(stmt, ast.If)
                and any(isinstance(child, ast.Name) and child.id == 'legacy_reader_alive' for child in ast.walk(stmt)))]
    assert dump(admitted) == dump(function(after, 'admitted_teacher'))
    previous_stage, next_stage = function(before, 'stage'), function(after, 'stage')
    assert dump(previous_stage.body[:-1]) == dump(next_stage.body[:-1])
    assert dump(previous_stage.body[-1].finalbody) == dump(next_stage.body[-1].finalbody)
    assert dump(previous_stage.body[-1].handlers) == dump(next_stage.body[-1].handlers)
    old_ready_tree = ast.parse((R / 'scripts/collection_readiness_r21.py').read_text())
    new_ready_tree = ast.parse((R / 'scripts/collection_readiness_r22.py').read_text())
    for name in ['rpc','choose','native_config','ensure_resident','release_cold_cache','initial','archive_trial','verify_nop']:
        assert dump(function(old_ready_tree, name)) == dump(function(new_ready_tree, name)), name
    rows = active_rows(before_counts)
    assert len(rows) == 1000 and Counter(row['pool'] for row in rows) == {'calibforge':500,'tmax':500}
    for pool in ['calibforge','tmax']:
        assert Counter(row['split'] for row in rows if row['pool'] == pool) == {'train':450,'validation':50}
    accepted, source_paths = {}, {}
    for root in old.readiness_roots():
        for path in [*sorted((root/'environment-outcomes').glob('*.json')),*sorted((root/'ready-revisions').glob('*/*.json'))]:
            value = json.loads(path.read_text())
            if value['status'] != 'ENV_READY':
                continue
            accepted[value['task_id']] = old.normalize_ready(value, path)
            source_paths[value['task_id']] = path
    blocks, reconciled = reconcile(R, accepted, current_setup_blocks(R, accepted))
    assert len(reconciled) == 5 and set(blocks) == {'task_008794_911eb529'}
    gate = json.loads((R/'checks/data-finalization-readiness-r370.json').read_text())
    unfinished = {row['task_id'] for row in gate['tasks'] if row['status'] in ['UNATTEMPTED','REMAINING_ALLOWED_ATTEMPT']}
    assert len(unfinished) == 22
    compared = []
    for ident in sorted(unfinished):
        value = new.normalize_ready(accepted[ident], source_paths[ident])
        assert value['engine_id'] == new.NODE['engine_id'] and value['deployment_config_sha256'] == new.CONFIG_SHA
        assert new.sha(Path(value['placement'])) == value['placement_sha256']
        for kind in ['install','nop','teacher']:
            a = old.native_config(accepted[ident]['admitted_task'],kind).model_dump(mode='json')
            b = new.native_config(value['admitted_task'],kind).model_dump(mode='json')
            a.pop('trial_name');b.pop('trial_name')
            assert a == b, (ident, kind)
        compared.append(dict(task_id=ident, native_configurations=3, current_environment_blocked=ident in blocks))
    proof_root = R / 'checks/controller-r22-stage-contract-r443'
    proof_root.mkdir(exist_ok=False)
    cases = asyncio.run(check_stage(source, proof_root))
    assert attempt_counts() == before_counts
    assert (R/'scripts/observe_collection_resume_r445.py').read_text().replace("['R22','R21','R20'","['R21','R20'") == (R/'scripts/observe_collection_drained_r428.py').read_text()
    assert (R/'scripts/check_final_data_readiness_r446.py').read_text().replace("['R22','R21','R20'","['R21','R20'") == (R/'scripts/check_final_data_readiness_r370.py').read_text()
    assert (R/'scripts/freeze_final_corpus_inputs149_r447.py').read_text().replace('scripts/check_final_data_readiness_r446.py','scripts/check_final_data_readiness_r370.py') == (R/'scripts/freeze_final_corpus_inputs149_r373.py').read_text()
    helpers = ['run_collection_stream_r22.py','collection_readiness_r22.py','collection_readiness_r21.py',
        'collection_administrative_ready_r427.py','collection_current_setup_blocks_r293.py','collection_attempts_r8.py',
        'collection_selection_r7.py','accept_resume_controller_r443.py','accept_agent_phase_r442.py',
        'check_final_data_readiness_r446.py','freeze_final_corpus_inputs149_r447.py','observe_collection_resume_r445.py']
    out = dict(passed=True, checked_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        controller_source_sha256=new.sha(source), deployment_config_sha256=new.CONFIG_SHA,
        previous_deployment_config_sha256=old.CONFIG_SHA, deployment_changed_fields=sorted(changed),
        controller_runtime=runtime, native_phase_proof_sha256=new.sha(phase), stage_contract_cases=cases,
        native_task_agent_verifier_resources_model_and_tools_unchanged=True, native_configs_compared=compared,
        obsolete_exited_reader_hold_removed=True, actual_attempt_counter_unchanged=True,
        actual_or_conservative_attempts=sum(before_counts.values()), independent_attempted_tasks=len(before_counts),
        reviewed_administrative_environments_restored=reconciled, real_environment_blocks=blocks,
        actual_teacher_dispatches=0, model_calls=0, new_controller_started=False,
        helper_sha256={name:new.sha(R/'scripts'/name) for name in helpers})
    new.freeze(R/'checks/controller-r22-offline-acceptance-r443.json', out)
    print(json.dumps(dict(passed=True, actual_teachers=0, model_calls=0, configuration_cases=len(compared)*3,
        stage_contract_cases=len(cases), attempt_counter=sum(before_counts.values()), new_controller_started=False)))


if __name__ == '__main__':
    main()
