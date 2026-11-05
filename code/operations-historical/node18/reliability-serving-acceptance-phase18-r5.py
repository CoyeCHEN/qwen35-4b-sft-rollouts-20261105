"""Six finite model requests admitted by the existing unique controller only."""
import importlib

base = importlib.import_module('reliability-cold-serving18-r4')
R, C, D = base.R, base.C, base.D
F = D / 'finite-serving-acceptance-r3'
PLAN_SHA = 'c08b3b518e6f67b16bd3a9059f491587ea4783c62d1e0f126ee609e0f9a8e6ef'
COLD_SHA = 'f3581288f923fb4405698accd3b0cf35b7fe210e4074e8a861779bdb16591b0b'
SOURCE_SHA = '87daffcdc128074c61239e46c30efb2c5f75fe17d316395b6565058732880849'


def advance(owner, state, launch):
    if base.read(C / 'NATIVE_ADVANCE_OWNER.json') != owner:
        raise RuntimeError('Finite serving requests require the unique controller')
    if not (R / 'checks/NATIVE_ADVANCE_R45_HANDOFF_COMPLETED.json').exists():
        state['reliability_finite_serving'] = dict(status='WAITING_NATIVE_HANDOFF', formal_ready=False)
        return
    plan = F / 'FINITE_SERVING_ACCEPTANCE_PLAN_R2.json'
    cold = D / 'COLD_SERVICES_LAUNCHED_R1.json'
    source = F / 'finite_serving_acceptance18_r3.py'
    if base.sha(plan) != PLAN_SHA or base.sha(cold) != COLD_SHA or base.sha(source) != SOURCE_SHA:
        raise RuntimeError('Finite serving acceptance input identity changed')
    fixture = R / 'lifecycle-boundary-r1/recorder-privacy-fixtures-r3/FIXTURE_ACCEPTANCE_R3.json'
    if base.sha(fixture) != 'af1d80cec96b714296040157607a21dcf0377a9e485ba9df9995a31ab62f080c' or not base.read(fixture)['passed']:
        raise RuntimeError('Native Wheel/Recorder acceptance not confirmed')
    count = D / 'readonly-real-payload-counter-r1/ACTUAL_REAL_PAYLOAD_COUNTER_AND_PLAN_ACCEPTANCE_R1.json'
    if base.sha(count) != 'cb56acb24b293a14d3be34da4ebe6a389a71b623d7f0b5f95bde42860a02b4f6':
        raise RuntimeError('Actual count-only regressions not confirmed')
    admission = F / 'ADMISSION_R3.json'
    output = F / 'actual-run-r1'
    args = ['--admission', str(admission), '--plan', str(plan), '--tool-schemas',
            str(F / 'ELEVEN_TOOL_SCHEMAS_R1.json'), '--owner-state', str(C / 'NATIVE_ADVANCE_OWNER.json'),
            '--output-dir', str(output)]
    state['reliability_finite_serving'] = launch(
        'qwen35-reliability-serving-acceptance-20261103-r1.service', str(source), args, admission, owner,
        dict(plan_sha256=PLAN_SHA, cold_manifest_path=str(cold), cold_manifest_sha256=COLD_SHA,
             artifacts_manifest_path=str(D / 'artifacts-r1/INTEGRATED_ARTIFACT_MANIFEST_R1.json'),
             scope='Finite direct Serving acceptance; not Agent/Task/Verifier or model score',
             max_model_generation_requests=6, no_retries=True),
        native_python=R / 'env/serve-reliability-r1/bin/python')
    progress = output / 'PROGRESS.json'
    if progress.exists():
        value = base.read(progress)
        state['reliability_finite_serving_progress'] = {
            k: value[k] for k in ['expected', 'completed', 'passed', 'max_model_request_attempts']}
    result = output / 'FINITE_SERVING_ACCEPTANCE_RESULT_R1.json'
    if result.exists():
        value = base.read(result)
        state['reliability_finite_serving_result'] = dict(
            path=str(result), sha256=base.sha(result), passed=value['passed'], completed=value['completed'],
            semantic_passed=value['semantic_passed'], formal_ready=False, not_task_success_rate=True)


if __name__ == '__main__':
    raise SystemExit('Only the existing unique controller may advance this acceptance')
