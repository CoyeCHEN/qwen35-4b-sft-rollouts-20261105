"""Select by the user-authorized common30 count, then run native89xn3."""
import importlib
import json
from pathlib import Path
import subprocess
import time

phase=importlib.import_module('diagnostic150-phase18-r1')
continuations=importlib.import_module('pre-model-environment-recovery-phase18-r1')
R=phase.R;E=phase.E;C=phase.C
read=phase.read;sha=phase.sha;save=phase.save;props=phase.props


def advance(owner,state):
    cfg=read(R/'configs/diagnostic150-five-model-r1.json')
    selection=R/'checks/WINNER_FROM_COMMON30_SELECTION_R1.json'
    if not selection.exists():
        if not state.get('pre_model_environment_continuations',{}).get('complete'):return
        if not all((E/'checks'/('DIAGNOSTIC30_NATIVE_ALL_TERMINAL_'+m['tag']+'.json')).exists()for m in cfg['models']):return
        if not(C/'EPOCH3_FIXED_SERVER_CLOSED_new-m1.json').exists():return
        subprocess.run([str(R/'env/harbor-native-eval-r1/bin/python'),str(R/'sync-closed-e3-evidence18-r1.py')],check=True,timeout=14400)
        subprocess.run([str(R/'env/harbor-native-eval-r1/bin/python'),str(E/'scripts/read-diagnostic150-matrix18-r2.py')],check=True,timeout=3600)
        matrix=read(E/'checks/DIAGNOSTIC150_MATRIX_R2.json');assert matrix['complete']and matrix['logical_terminal']==150
        order=cfg['selection']['tie_order'];winner=min(order,key=lambda tag:(-matrix['models'][tag]['confirmed_reward_successes'],order.index(tag)))
        model=next(m for m in cfg['models']if m['tag']==winner)
        save(selection,dict(at=time.time(),winner=winner,model=model,
            common30_matrix_sha256=sha(E/'checks/DIAGNOSTIC150_MATRIX_R2.json'),
            candidates=matrix['models'],criterion=cfg['selection'],
            largest_confirmed_correct_count=matrix['models'][winner]['confirmed_reward_successes'],
            unknowns_not_reward_zero=True,selection_may_be_uncertain_with_unknowns=True,
            selected_on_subset_of_full89=True,not_unselected_holdout=True,
            user_scope_override_sha256=sha(C/'USER_EVALUATION_SCOPE_OVERRIDE_R1.json')))
    chosen=read(selection);model=chosen['model']
    released=R/'checks/DIAG150_ALL_MODEL_SERVICES_RELEASED_R1.json'
    if not released.exists():
        stopped=[]
        for candidate in cfg['models']:
            replicas=candidate.get('replicas')or[dict(unit=candidate['serving_unit'])]
            for replica in replicas:
                unit=replica['unit']
                if props(unit)['ActiveState']=='active':subprocess.run(['systemctl','--user','stop',unit],check=True,timeout=60);stopped.append(unit)
        save(released,dict(at=time.time(),stopped_completed_services=stopped,all150_logical_terminal=True,selection_sha256=sha(selection)))
    binding=R/'checks/SELECTED267_MODEL_BINDING_R1.json'
    if not binding.exists():
        runtime=read(R/'new-sft/workspace/configs/runtime.json');ports=[18300,18301,18302,18308,18303,18309,18306,18307]
        full=dict(model,tag='selected267',model_id='qwen35-new772-selected30-winner',source_agent_index=2,
            display_name='Qwen3.5-4B selected by common30',new_trials=267,concurrency=16,
            job_name='qwen35-user-selected30-winner-tb21-n3-267-20261102-r1',
            job_unit='qwen35-user-selected267-native18-20261102-r1.service',
            replicas=[dict(gpu_index=i,gpu_uuid=runtime['authorized_gpu_uuids'][i],port=ports[i],
                unit='qwen35-user-selected267-gpu'+str(i)+'-20261102-r1.service')for i in range(8)])
        save(binding,full)
        source=read(E/'manifests/FORMAL_801_TRIAL_PLAN.json')
        trials=[]
        for row in source['trials']:
            if row['model_name']!='openai/qwen35-new772-m0':continue
            item=dict(row,tag='selected267',model_name='openai/'+full['model_id'],
                trial_name=row['task_id']+'__selected30-winner-n3-r'+str(row['repetition']),reuse_existing_trial=False)
            trials.append(item)
        assert len(trials)==267 and len({x['trial_name']for x in trials})==267
        assert len({x['task_id']for x in trials})==89
        save(E/'manifests/SELECTED267_BOUND_TRIAL_PLAN_R1.json',dict(expected=267,trials=trials,
            sampling_manifest_sha256=cfg['sampling_manifest_sha256'],selection_sha256=sha(selection),
            selected_model_manifest_sha256=model['weight_version'],no_old801_trials_reused=True))
    done=E/'checks/SELECTED267_COMPARISON_R1.json'
    if done.exists():
        result=read(done);assert result['complete']and result['terminal']==267
        state.update(status='USER_SELECTED267_COMPLETE_OLD_RESEARCH_HANDOFF_PENDING',selected267_result_sha256=sha(done))
        return
    full=read(binding)
    for replica in full['replicas']:phase.start_replica(full,replica)
    state['selected267']=continuations.launch(full,owner,recovery=False)
    status=E/'checks/SELECTED267_STATUS_R1.json'
    if status.exists():state['selected267']['progress']=read(status)
    done=E/'checks/SELECTED267_COMPARISON_R1.json'
    state['status']='SELECTED_MODEL_FULL89_N3_RUNNING_OR_COLD_STARTING'
    if done.exists():
        result=read(done);assert result['complete']and result['terminal']==267
        state.update(status='USER_SELECTED267_COMPLETE_OLD_RESEARCH_HANDOFF_PENDING',selected267_result_sha256=sha(done))


if __name__=='__main__':raise SystemExit('Only the existing unique controller may advance this phase')
