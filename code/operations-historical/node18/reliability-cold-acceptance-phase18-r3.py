"""Existing controller's finite cold-service acceptance leaf; no evaluation queue."""
import importlib
from pathlib import Path

base = importlib.import_module('reliability-cold-serving18-r3')
R, C, D = base.R, base.C, base.D


def advance(owner, state, launch):
    if base.read(C / 'NATIVE_ADVANCE_OWNER.json') != owner:
        raise RuntimeError('Cold acceptance requires the existing unique controller')
    if not (R / 'checks/NATIVE_ADVANCE_R43_HANDOFF_COMPLETED.json').exists():
        state['reliability_cold_services'] = dict(status='WAITING_NATIVE_HANDOFF_RECEIPT', formal_ready=False)
        return
    proof = base.read(D / 'COMBINED_SOURCE_CPU_ACCEPTANCE_R1.json')
    if not proof['passed'] or proof['harness_tests'] != 144:
        raise RuntimeError('Integrated source regression is not accepted')
    admission = D / 'COLD_SERVICES_ADMISSION_R1.json'
    state['reliability_cold_bootstrap'] = launch(
        'qwen35-reliability-cold-bootstrap-20261103-r1.service',
        'reliability-cold-serving18-r3.py', [str(admission)], admission, owner,
        dict(purpose='Cold Serving and exact count acceptance only; no task evaluation dispatch',
             artifact_manifest_sha256=base.ARTIFACT_SHA))
    path = D / 'COLD_SERVICES_LAUNCHED_R1.json'
    if not path.exists():
        state['reliability_cold_services'] = dict(status='BOOTSTRAP_PENDING', formal_ready=False)
        return
    replicas = []
    for item in base.read(path)['replicas']:
        try:
            live = base.get(item['port'], '/model_info')
            if live['model_path'] != item['model_path'] or live['weight_version'] != item['weight_version']:
                raise RuntimeError('Actual cold model identity differs')
            replicas.append(dict(tag=item['tag'], port=item['port'], gpu_uuid=item['gpu_uuid'],
                                 status='COLD_MODEL_IDENTITY_CONFIRMED', weight_version=item['weight_version']))
        except Exception as error:
            replicas.append(dict(tag=item['tag'], port=item['port'], status='NOT_READY', error=repr(error)))
    state['reliability_cold_services'] = dict(replicas=replicas,
        formal_ready=False, model_trial_dispatch=False, exact_counter_and_wheel_e2e_pending=True)


if __name__ == '__main__':
    raise SystemExit('Only the original unique controller may advance this acceptance leaf')
