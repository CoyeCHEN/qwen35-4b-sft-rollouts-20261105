"""Finite native acceptance Jobs under the original unique controller lock."""
import importlib

base = importlib.import_module('reliability-cold-serving18-r4')
R, C, D = base.R, base.C, base.D
FIXTURE_PLAN_SHA = 'f6ae55a89c736d033966d61f72b68ba0792b43f3facac4c79efba7639bc9a47e'


def advance(owner, state, launch):
    if base.read(C / 'NATIVE_ADVANCE_OWNER.json') != owner:
        raise RuntimeError('Native acceptance requires the original unique controller')
    if not (R / 'checks/NATIVE_ADVANCE_R44_HANDOFF_COMPLETED.json').exists():
        state['reliability_native_acceptance'] = dict(status='WAITING_NATIVE_HANDOFF', formal_ready=False)
        return
    proof = base.read(D / 'COMBINED_SOURCE_CPU_ACCEPTANCE_R1.json')
    if not proof['passed'] or proof['harness_tests'] != 144:
        raise RuntimeError('Integrated source acceptance is missing')
    admission = D / 'COLD_SERVICES_ADMISSION_R2.json'
    cold = launch('qwen35-reliability-cold-bootstrap-20261103-r2.service',
        'reliability-cold-serving18-r4.py', [str(admission)], admission, owner,
        dict(purpose='Independent acceptance after preserved zero-model read-only observer failure',
             artifact_manifest_sha256=base.ARTIFACT_SHA,
             previous_failed_admission=str(D / 'COLD_SERVICES_ADMISSION_R1.json'),
             observer_source_sha256='71b245d9f1863bda8a4d9677c96b73652be53c767c1b7635d68e1951357fc1a8'))
    state['reliability_cold_bootstrap_r2'] = cold
    plan_path = D / 'FIXTURE_NATIVE_LAUNCH_PLAN_R3.json'
    if base.sha(plan_path) != FIXTURE_PLAN_SHA:
        raise RuntimeError('Finite fixture launch plan identity changed')
    plan = base.read(plan_path)
    argv = plan['argv']
    if not plan['frozen'] or plan['new_model_generation_calls'] != 0 or plan['task_cases'] != 2:
        raise RuntimeError('Unexpected native fixture scope')
    if argv[0] != str(R / 'env/harbor-reliability-r1/bin/python') or base.sha(argv[1]) != plan['source_sha256']:
        raise RuntimeError('Finite fixture source or interpreter differs')
    state['reliability_privacy_fixture'] = launch(
        'qwen35-reliability-recorder-privacy-20261103-r3.service',
        argv[1], argv[2:], D / 'NATIVE_PRIVACY_FIXTURE_ADMISSION_R3.json', owner,
        dict(frozen_plan_path=str(plan_path), frozen_plan_sha256=FIXTURE_PLAN_SHA,
             new_model_generation_calls=0), native_python=argv[0])
    result_path = R / 'lifecycle-boundary-r1/recorder-privacy-fixtures-r3/FIXTURE_ACCEPTANCE_R3.json'
    if result_path.exists():
        result = base.read(result_path)
        state['reliability_privacy_fixture_result'] = dict(
            passed=result['passed'], path=str(result_path), sha256=base.sha(result_path),
            completed_cases=result['completed_fixture_cases'], model_generation_calls=result['model_generation_calls'])
    launched = D / 'COLD_SERVICES_LAUNCHED_R1.json'
    replicas = []
    if launched.exists():
        for item in base.read(launched)['replicas']:
            try:
                live = base.get(item['port'], '/model_info')
                if live['model_path'] != item['model_path'] or live['weight_version'] != item['weight_version']:
                    raise RuntimeError('Actual cold model identity differs')
                replicas.append(dict(tag=item['tag'], port=item['port'], gpu_uuid=item['gpu_uuid'],
                                     status='COLD_MODEL_IDENTITY_CONFIRMED', weight_version=item['weight_version']))
            except Exception as error:
                replicas.append(dict(tag=item['tag'], port=item['port'], status='NOT_READY', error=repr(error)))
    unit = cold.get('unit', cold)
    state['reliability_native_acceptance'] = dict(
        status='COLD_REPLICAS_LAUNCHED' if replicas else
               'COLD_BOOTSTRAP_FAILED' if unit.get('ActiveState') == 'failed' else 'COLD_BOOTSTRAP_PENDING',
        replicas=replicas, formal_ready=False, new_model_trial_dispatch=False,
        exact_counter_and_live_model_acceptance_pending=True,
        legacy_jobs_results_rewards_and_recorders_unmodified=True)


if __name__ == '__main__':
    raise SystemExit('Only the existing unique controller may advance acceptance')
