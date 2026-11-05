"""User update: five common30 checkpoints, then one selected89xn3 model."""
import copy
import hashlib
import json
from pathlib import Path
import time

R=Path('/ssd/chenkeyi/qwen35-sft-772-20261101');E=R/'formal-native-eval-r1'
C=Path('/data/chenkeyi/qwen35-sft-772-20261101/control')
def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,v):
    assert not p.exists(),p
    p.write_text(json.dumps(v,indent=2)+'\n')


def main():
    assert not(C/'native-phase-requests/formal-n3.json').exists()
    assert not(E/'jobs/qwen35-new772-tb21-n3').exists()
    assert read(R/'checks/FORMAL_CONTROLLER18_M0_NATIVE_JOINT_ACCEPTANCE_R1.json')['passed']
    assert read(R/'runs/new-m2-tmax356-128k-e5/FINAL_HF_ADMISSION.json')['passed']
    old=read(R/'configs/diagnostic30-four-model-r1.json');plan=read(E/'manifests/DIAGNOSTIC30_120_TRIAL_PLAN_R1.json')
    sample=read(E/'manifests/DIAGNOSTIC30_SAMPLING_MANIFEST_R1.json')
    ids=read(E/'manifests/OFFICIAL_89_TASK_IDENTITIES.json')['tasks'];byid={x['task_id']:x for x in ids}
    uuids=read(R/'new-sft/workspace/configs/runtime.json')['authorized_gpu_uuids']
    models=copy.deepcopy(old['models']);bytag={x['tag']:x for x in models}
    e1=bytag['new-m2-e1-diag'];assert not(E/'jobs'/e1['job_name']).exists()
    assert not(R/'checks/DIAGNOSTIC30_MODEL_BINDING_new-m2-e1-diag.json').exists()
    e1.update(job_unit='qwen35-new772-diag150-native-new-m2-e1-diag-20261102-r1.service',concurrency=4,
        replicas=[dict(gpu_index=i,gpu_uuid=uuids[i],port=18300+i,
            unit='qwen35-new772-diag150-e1-gpu'+str(i)+'-20261102-r1.service')for i in [0,1]])
    e5=dict(tag='new-m2-e5-diag',source_agent_index=2,model_id='qwen35-new772-new-m2-e5',
        model_path=str(R/'runs/new-m2-tmax356-128k-e5'),model_manifest=str(R/'runs/new-m2-tmax356-128k-e5/HF_EXPORT_COMPLETE.json'),
        weight_version=sha(R/'runs/new-m2-tmax356-128k-e5/HF_EXPORT_COMPLETE.json'),epoch=5,new_trials=30,
        job_name='qwen35-new772-new-m2-epoch5-diagnostic30-20261102-r1',
        job_unit='qwen35-new772-diag150-native-new-m2-e5-diag-20261102-r1.service',
        display_name='Qwen3.5-4B NEW-M2 Epoch5 common30',concurrency=6,
        replicas=[dict(gpu_index=2,gpu_uuid=uuids[2],port=18302,
            unit='qwen35-new772-cold-new-m2-e5-20261101.service',reuse_running=True),
            dict(gpu_index=3,gpu_uuid=uuids[3],port=18308,unit='qwen35-new772-diag150-e5-gpu3-20261102-r1.service'),
            dict(gpu_index=5,gpu_uuid=uuids[5],port=18309,unit='qwen35-new772-diag150-e5-gpu5-20261102-r1.service')])
    models.append(e5)
    for model in models:
        if model['tag']not in ['new-m2-e1-diag','new-m2-e5-diag']:
            model.update(legacy_running=True,job_unit=model['job_unit'].replace('-r1.service','-r2.service'))
    trials=copy.deepcopy(plan['trials'])
    for task in sample['tasks']:
        trials.append(dict(tag=e5['tag'],task_id=task,task_path=byid[task]['path'],
            trial_name=task+'__new-m2-e5-diagnostic30-r1',model_name='openai/'+e5['model_id'],
            agent_override_timeout_sec=max(10800,byid[task]['original_agent_timeout_sec']),
            reuse_existing_trial=False,repetition=1))
    assert len(trials)==150 and len({x['trial_name']for x in trials})==150
    cfg=dict(kind='USER_FIVE_CHECKPOINT_COMMON30_THEN_MAX_CORRECT_WINNER_N3',at=time.time(),
        models=models,expected_trials=150,sampling_manifest_sha256=sha(E/'manifests/DIAGNOSTIC30_SAMPLING_MANIFEST_R1.json'),
        previous_120_plan_sha256=sha(E/'manifests/DIAGNOSTIC30_120_TRIAL_PLAN_R1.json'),
        wheel_sha256=old['wheel_sha256'],new_model_native_concurrency=10,legacy_concurrency_unchanged=True,
        gpu_indices=list(range(8)),selection=dict(primary='confirmed_verifier_reward_successes',
            fixed_tasks=30,unknown_not_reward_zero=True,
            tie_order=['new-m2-e5-diag','new-m1-e5-diag','new-m2-e3-diag','new-m1-e3-diag','new-m2-e1-diag']),
        full_n3=dict(models=1,tasks=89,repetitions=3,expected_trials=267,native_concurrency=16),
        previous_801_auto_dispatch_superseded=True,
        selection_subset_overlaps_full89_report_selection_bias=True)
    save(R/'configs/diagnostic150-five-model-r1.json',cfg)
    save(E/'manifests/DIAGNOSTIC150_TRIAL_PLAN_R1.json',dict(expected=150,trials=trials,
        sampling_manifest_sha256=cfg['sampling_manifest_sha256'],previous_120_plan_sha256=cfg['previous_120_plan_sha256'],
        original_120_identities_unchanged=True,new_e5_trials=30,original_two_oom_results_stay_unknown=True))
    save(C/'USER_EVALUATION_SCOPE_OVERRIDE_R1.json',dict(at=time.time(),
        user_authorized_five_checkpoint_common30=True,common30_plan_sha256=sha(E/'manifests/DIAGNOSTIC150_TRIAL_PLAN_R1.json'),
        deployment_sha256=sha(R/'configs/diagnostic150-five-model-r1.json'),
        old_801_plan_kept_historical_no_new_dispatch=True,winner_full_n3_expected=267,
        selection=cfg['selection'],eight_authorized_gpus=True,higher_native_concurrency_authorized=True,
        all_started_trials_and_original_results_preserved=True,source_sha256=sha(Path(__file__))))
    print(json.dumps(dict(prepared=True,diagnostic_trials=150,new_e5=30,new_e1_unstarted=30,
        future_selected_model_full_n3_trials=267,gpu_indices=list(range(8)))))


if __name__=='__main__':main()
