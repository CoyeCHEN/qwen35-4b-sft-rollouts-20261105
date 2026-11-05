"""Invoke the14 preregistered native old behavior Jobs after the real formal801 gate."""
import importlib
import json
from pathlib import Path
import subprocess
import time

R=Path('/ssd/chenkeyi/qwen35-sft-772-20261101')
P=R/'old-four-arm'
C=Path('/data/chenkeyi/qwen35-sft-772-20261101/control')
cold=importlib.import_module('cold-old112-serving18-r1')
TAGS=['old-M1','old-M2']+[a+'-epoch'+str(e)for a in 'ABCD'for e in (1,3,5)]


def save(p,value):
    temp=p.with_name(p.name+'.tmp');temp.write_text(json.dumps(value,indent=2)+'\n');temp.replace(p)


def advance(owner,state,remote,request):
    if not importlib.import_module('resume-old-four-native18-r2').admitted()['admitted']:
        state['old112_behavior']='DEFERRED_UNTIL_ACTUAL_FORMAL_801_COMPLETE';return
    actual=remote('status');save(C/'REMOTE_NATIVE_EVAL_STATUS.json',actual)
    release=json.loads((R/'checks/NATIVE_EVAL149_DEPLOYMENT_RELEASE_R4.json').read_text())
    experiments=json.loads((P/'manifests/experiments.json').read_text());completed=[]
    active=[tag for tag in TAGS if 'ActiveState=active'in actual['modes']['old-'+tag]['systemd']]
    for tag in TAGS:
        mode='old-'+tag;item=actual['modes'][mode]
        if item['complete']or(item.get('progress')or{}).get('actual_terminal')==8:
            marker=C/('OLD112_SERVER_CLOSED_'+tag+'.json')
            if not marker.exists():cold.stop(tag);save(marker,dict(at=time.time(),native_terminal=8))
        if item['complete']:
            if item['complete']['actual_terminal']!=8:raise ValueError('Old behavior terminal membership differs')
            completed.append(tag);continue
        if active:
            state['old112_behavior']=dict(status='NATIVE_JOB_OR_POSTHOC_READOUT_RUNNING',model=active[0],
                native_progress=actual['modes']['old-'+active[0]],completed_models=completed);return
        if (C/'native-phase-requests'/(mode+'.json')).exists():
            state['old112_behavior']=dict(status='EXISTING_NATIVE_JOB_REQUIRES_INSPECTION',model=tag,observed=item);return
        if not tag.startswith('old-'):
            arm,epoch=tag.split('-epoch')
            path=Path(experiments['arms'][arm]['output_dir'])/('checkpoint-'+str(106*int(epoch)))
            if not(path/'CHECKPOINT_COMPLETE.json').exists():continue
        cold.start(tag)
        try:live=cold.info(tag)
        except OSError:
            state['old112_behavior']=dict(status='NATIVE_COLD_SERVER_STARTING',model=tag);return
        request(mode,dict(model_tag=tag,new_formal801_completed=True,model_path=live['model_path'],
            model_manifest=live['model_manifest'],weight_version=live['weight_version'],gpu_uuid=cold.GPU,
            old112_plan_sha256=release['old112_deployment_plan_sha256'],
            native_runner_sha256=release['old_study_sources']['run-old112-native149-r1.py'],
            original_ten_tools_finish_off=True,original_task_agent_limits=True,
            actual_model_info=live['actual_model_info']),owner)
        state['old112_behavior']=dict(status='NATIVE_8_TASK_JOB_SUBMITTED',model=tag,completed_models=completed);return
    state['old112_behavior']=dict(status='WAITING_FOR_OLD_NATIVE_CHECKPOINTS',completed_models=completed)
    if len(completed)==14:
        state['old112_behavior']['status']='ALL_112_NATIVE_TRIALS_TERMINAL'
        marker=C/'OLD112_NATIVE_ALL_TERMINAL.json'
        if not marker.exists():save(marker,dict(completed=True,actual_terminal=112,models=completed,
            score_coverage_and_behavior_validity_must_be_reported_separately=True,
            original_native_results_and_recorders_retained=True))
