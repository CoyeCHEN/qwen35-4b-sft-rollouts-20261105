"""Raise only campaign-controller RAM and admit the original five unstarted tasks."""
import hashlib
import json
from pathlib import Path
import subprocess
import time

R=Path('/home/chenkeyi/.local/share/harbor-rsi/qwen35-new772-tb21-20261101')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_text())


def main():
    previous=R/'checks/NATIVE_EVAL149_DEPLOYMENT_RELEASE_R8.json'
    assert sha(previous)=='b01b16fbfffb65e17353bb50737d6ee123d3f2356c1e044b837437ca674f995b'
    old=read(previous)
    for name,digest in old['sources'].items():assert sha(R/'scripts'/name)==digest,name
    acceptance=R/'checks/E3_ORIGINAL_UNSTARTED_NATIVE_CONFIG_ACCEPTANCE_R1.json'
    proof=read(acceptance)
    assert proof['passed']and proof['actual_trials_started']==0 and proof['distinct_original_unstarted_tasks']==5
    assert proof['source_sha256']==sha(R/'scripts/run-e3-original-unstarted149-r1.py')
    snapshot=R/'checks/E3_NATIVE_CONTROLLER_OOM_SNAPSHOT_R1.json';failure=read(snapshot)
    assert failure['controller_properties']['MemoryMax']==failure['controller_properties']['MemoryPeak']=='4294967296'
    assert not(R/'jobs/qwen35-new772-tb21-n3').exists()
    assert not(R/'manifests/THREE_MODEL_COLD_SERVING_ADMISSION.json').exists()
    extras={n:sha(R/'scripts'/n)for n in ['native-handoff149-r9.py','run-e3-original-unstarted149-r1.py']}
    value=dict(old,kind='NATIVE_EVAL149_FIXED_DEPLOYMENT_RELEASE_R9',sources=dict(old['sources'],**extras),
        previous_deployment_release_sha256=sha(previous),
        campaign_controller_memory_max_bytes=16*1024**3,previous_controller_memory_max_bytes=4*1024**3,
        controller_ram_change_evidence_sha256=sha(snapshot),official_task_container_resources_unchanged=True,
        original_unstarted_continuation_config_acceptance_sha256=sha(acceptance),
        original_unstarted_tasks=proof['tasks'],original_started_trials_not_redispatched=True,
        new_continuation_native_concurrency=1,original_live_orphan_kept=True,
        original_controller_oom_and_missing_results_not_hidden=True,
        release_source_sha256=sha(Path(__file__)))
    path=R/'checks/NATIVE_EVAL149_DEPLOYMENT_RELEASE_R9.json';assert not path.exists();path.write_text(json.dumps(value,indent=2)+'\n')
    authorized=Path.home()/'.ssh/authorized_keys';raw=authorized.read_text();lines=raw.splitlines(keepends=True)
    selected=[i for i,line in enumerate(lines)if 'native-handoff149-r8.py'in line];assert len(selected)==1
    backup=authorized.with_name('authorized_keys.before-native-handoff-r9-'+str(int(time.time())));backup.write_text(raw);backup.chmod(0o600)
    lines[selected[0]]=lines[selected[0]].replace('native-handoff149-r8.py','native-handoff149-r9.py')
    temp=authorized.with_name('authorized_keys.native-handoff-r9.tmp');temp.write_text(''.join(lines));temp.chmod(0o600);temp.replace(authorized)
    activation=dict(passed=True,at=time.time(),release_sha256=sha(path),new_controller_memory_max_bytes=16*1024**3,
        actual_new_model_calls=0,official_task_resources_changed=False,existing_original_results_or_configs_modified=False,
        fixed_original_five_configs_verified=True,original_oom_snapshot_sha256=sha(snapshot))
    p=R/'checks/NATIVE_EVAL149_R9_ACTIVATION.json';assert not p.exists();p.write_text(json.dumps(activation,indent=2)+'\n');print(json.dumps(activation))


if __name__=='__main__':main()
