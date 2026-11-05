"""Freeze the authorized 30-task matrix using public metadata, never scores."""
from collections import Counter
import hashlib
import json
from pathlib import Path
import shutil
import time
import tomllib

R=Path('/ssd/chenkeyi/qwen35-sft-772-20261101');E=R/'formal-native-eval-r1'
def read(path):return json.loads(path.read_text())
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def save(path,value):
    assert not path.exists(),str(path)
    path.write_text(json.dumps(value,indent=2)+'\n')


def main():
    original=E/'manifests/EPOCH3_DIAGNOSTIC_PREREGISTRATION.json'
    assert sha(original)=='472afd0e83e7bbcf748f8d5c5e6a04494774b45aea44052cef11bf03f0bc0434'
    first=read(original)['tasks'];identities=read(E/'manifests/OFFICIAL_89_TASK_IDENTITIES.json')['tasks']
    byid={item['task_id']:item for item in identities};metadata={}
    for task,item in byid.items():
        path=Path(item['path']);assert sha(path/'task.toml')==item['task_toml_sha256']
        metadata[task]=tomllib.loads((path/'task.toml').read_text())['metadata']
    sizes=Counter(meta['category']for meta in metadata.values())
    retained=Counter(metadata[task]['category']for task in first)
    quota={category:max(1,retained[category])for category in sizes}
    while sum(quota.values())<30:
        category=min((k for k in sizes if quota[k]<sizes[k]),key=lambda k:(-(30*sizes[k]/89-quota[k]),k))
        quota[category]+=1
    rank=lambda task:hashlib.sha256(('seed42:'+task).encode()).hexdigest()
    added=[]
    for category in sorted(sizes):
        candidates=sorted((task for task in byid if task not in first and metadata[task]['category']==category),key=rank)
        added.extend(candidates[:quota[category]-retained[category]])
    selected=first+added;assert len(selected)==len(set(selected))==30 and len(added)==21
    manifest=dict(kind='PUBLIC_METADATA_DIAGNOSTIC30_SEED42',created_at=time.time(),seed=42,
        original_nine_manifest_sha256=sha(original),original_nine=first,additional_twenty_one=added,tasks=selected,
        selection='Retain the original nine. Cover all public categories; allocate remaining slots by largest deficit from 30*Ncategory/89; SHA256(seed42:task_id) order within category.',
        original_category_counts=dict(sizes),selected_category_counts=dict(Counter(metadata[t]['category']for t in selected)),
        selected_difficulty_counts=dict(Counter(metadata[t]['difficulty']for t in selected)),
        model_results_read_for_selection=False,same_labels_do_not_claim_identical_distribution=True,
        source_identities_sha256=sha(E/'manifests/OFFICIAL_89_TASK_IDENTITIES.json'),
        selected_task_identities=[dict(byid[t],public_metadata=metadata[t])for t in selected],source_sha256=sha(Path(__file__)))
    sampling=E/'manifests/DIAGNOSTIC30_SAMPLING_MANIFEST_R1.json';save(sampling,manifest)
    uuids=read(R/'new-sft/workspace/configs/runtime.json')['authorized_gpu_uuids']
    definitions=[
      ('new-m1-e3-diag',1,4,18303,'qwen35-new772-new-m1-epoch3-fixed','epoch-models/new-m1-epoch3','epoch-models/new-m1-epoch3/EPOCH_MODEL_EXPORT_COMPLETE.json','qwen35-new772-new-m1-epoch3-fixed-expanded21-20261102-r1',3,True,21),
      ('new-m1-e5-diag',1,6,18306,'qwen35-new772-new-m1-e5-diag','runs/new-m1-cf416-128k-e5','runs/new-m1-cf416-128k-e5/HF_EXPORT_COMPLETE.json','qwen35-new772-new-m1-e5-diagnostic30-r1',5,False,30),
      ('new-m2-e3-diag',2,7,18307,'qwen35-new772-new-m2-epoch3-fixed','epoch-models/new-m2-epoch3','epoch-models/new-m2-epoch3/EPOCH_MODEL_EXPORT_COMPLETE.json','qwen35-new772-new-m2-epoch3-fixed-diagnostic',3,False,30),
      ('new-m2-e1-diag',2,None,None,'qwen35-new772-new-m2-epoch1-diag','epoch-models/new-m2-epoch1','epoch-models/new-m2-epoch1/EPOCH_MODEL_EXPORT_COMPLETE.json','qwen35-new772-new-m2-epoch1-diagnostic30-r1',1,False,30)]
    models=[];trials=[]
    for tag,index,gpu,port,alias,folder,proof,job,epoch,reuse,count in definitions:
        path=R/proof;assert path.exists()
        if tag=='new-m1-e5-diag':assert read(R/'runs/new-m1-cf416-128k-e5/FINAL_HF_ADMISSION.json')['passed']
        assert not(E/'jobs'/job).exists()
        model=dict(tag=tag,source_agent_index=index,gpu_index=gpu,gpu_uuid=uuids[gpu]if gpu is not None else None,
            port=port,model_id=alias,model_path=str(R/folder),model_manifest=str(path),weight_version=sha(path),
            job_name=job,epoch=epoch,reuse_service=reuse,new_trials=count,display_name='Qwen3.5-4B '+tag,
            serving_unit='qwen35-new772-cold-new-m1-epoch3-fixed-20261101.service'if reuse else'qwen35-new772-diag30-serving-'+tag+'-20261102-r1.service',
            job_unit='qwen35-new772-diag30-native-'+tag+'-20261102-r1.service')
        models.append(model)
        for task in selected:
            suffix=('__new-m1-e3-fixed-r1'if tag=='new-m1-e3-diag'else'__new-m2-e3-fixed-r1'if tag=='new-m2-e3-diag'else'__'+tag+'-diagnostic30-r1')
            trials.append(dict(tag=tag,task_id=task,task_path=byid[task]['path'],trial_name=task+suffix,
                model_name='openai/'+alias,agent_override_timeout_sec=max(10800,byid[task]['original_agent_timeout_sec']),
                reuse_existing_trial=bool(reuse and task in first),repetition=1))
    assert len(trials)==120 and sum(not x['reuse_existing_trial']for x in trials)==111
    save(R/'configs/diagnostic30-four-model-r1.json',dict(kind='USER_AUTHORIZED_FOUR_MODEL_DIAGNOSTIC30',
        expected_trials=120,expected_new_native_trials=111,authorized_gpu_indices=[6,7],models=models,
        original_m1_e3_gpu4_and_all_running_trials_preserved=True,m2_e1_uses_first_completed_gpu6_or7=True,
        formal_801_excluded=True,sampling_manifest_sha256=sha(sampling),
        wheel_sha256='1d27eef1ca6696275f306d8c653f7a266a4c7aea7321f0d47fd01b739c27fa18'))
    save(E/'manifests/DIAGNOSTIC30_120_TRIAL_PLAN_R1.json',dict(expected=120,preregistration_sha256=sha(original),
        sampling_manifest_sha256=sha(sampling),trials=trials,formal_801_excluded=True,
        nine_existing_m1_e3_attempts_reused_without_retry=True,original_two_missing_results_remain_unknown=True))
    shutil.copyfile(R/'run-30task-native-diagnostic18-r1.py',E/'scripts/run-30task-native-diagnostic18-r1.py')
    print(json.dumps(dict(prepared=True,selected_tasks=30,new_native_trials=111,reused_m1_e3_identities=9,
        sampling_manifest_sha256=sha(sampling),category_counts=manifest['selected_category_counts'],actual_model_calls=0)))


if __name__=='__main__':main()
