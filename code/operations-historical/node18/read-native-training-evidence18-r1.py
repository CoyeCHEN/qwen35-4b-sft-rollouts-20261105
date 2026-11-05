"""Read native Rank evidence and map committed exposure to immutable data; no dispatch."""
from collections import Counter,defaultdict
import hashlib
import json
import math
from pathlib import Path
import time
import yaml

R=Path('/ssd/chenkeyi/qwen35-sft-772-20261101')
W=R/'new-sft/workspace'
F=R/'frozen-data-772-r3'
SOURCE='293ba2a7dca8569bb39e11bc0137a0e1180a0391402f10d49ff5b4ad00ce6c93'
STAGES=[('new-cf416-m1','new-m1-cf416-128k-e5','calibforge',40,200),
        ('new-cf416-tmax356-m2','new-m2-tmax356-128k-e5','tmax',25,125)]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def load(p):return json.loads(p.read_text())if p.exists()else None
def save(p,value):
    temp=p.with_name(p.name+'.tmp');temp.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n');temp.replace(p)


def events(path):
    if not path.exists():return [],None
    blob=path.read_bytes();lines=blob.splitlines();values=[];incomplete=False
    for index,line in enumerate(lines):
        try:values.append(json.loads(line))
        except json.JSONDecodeError:
            if index!=len(lines)-1 or blob.endswith(b'\n'):raise
            incomplete=True
    return values,dict(path=str(path),snapshot_bytes=len(blob),sha256=hashlib.sha256(blob).hexdigest(),
        incomplete_trailing_line_excluded=incomplete)


def expose(stage,folder,pool,per_epoch,planned):
    cfg_path=W/'configs'/(stage+'.yaml');cfg=yaml.safe_load(cfg_path.read_text())
    job=load(W/'jobs'/('new772-'+stage)/'job.json')
    result=dict(stage=stage,run_path=str(folder),planned_optimizer_steps=planned,
        config_path=str(cfg_path),config_sha256=sha(cfg_path),config=cfg,
        deepspeed_sha256=sha(Path(cfg['deepspeed'])),job=job,
        trainer_state=load(folder/'trainer_state.json'),hf_export=load(folder/'HF_EXPORT_COMPLETE.json'),
        final_hf_admission=load(folder/'FINAL_HF_ADMISSION.json'),native_checkpoints={},nll_audits={},intermediate_hf={},
        five_epochs_completed_and_final_hf_admitted=False)
    for epoch in (1,3,5):
        tag=('new-m1'if pool=='calibforge'else'new-m2')+'-epoch'+str(epoch)
        hf=R/'epoch-models'/tag/'EPOCH_MODEL_EXPORT_COMPLETE.json'
        if hf.exists():result['intermediate_hf'][str(epoch)]=dict(path=str(hf.parent),manifest_sha256=sha(hf),manifest=load(hf))
        proof=folder/('checkpoint-'+str(per_epoch*epoch))/'CHECKPOINT_COMPLETE.json'
        if proof.exists():result['native_checkpoints'][str(epoch)]=dict(path=str(proof.parent),marker_sha256=sha(proof),
            trainer_state=load(proof.parent/'trainer_state.json'),identity=load(proof).get('identity'))
        audit=R/'nll-audits'/('new-m1'if pool=='calibforge'else'new-m2')
        audit=audit.with_name(audit.name+'-epoch'+str(epoch))/'NLL_AUDIT_COMPLETE.json'
        if audit.exists():result['nll_audits'][str(epoch)]=dict(path=str(audit),sha256=sha(audit),result=load(audit))
    rank_events={};snapshots={};updates={};begins={}
    for rank in range(4):
        values,snapshot=events(folder/('preflight-evidence-rank'+str(rank)+'.jsonl'))
        rank_events[rank]=values;snapshots[str(rank)]=snapshot
        starts=[v for v in values if v['event']=='train_begin'];records=[v for v in values if v['event']=='optimizer_step']
        if len(starts)>1 or len({v['global_step']for v in records})!=len(records):
            raise ValueError('Recovery/rollback exposure requires explicit segment audit; never silently deduplicate native updates')
        if starts:
            b=starts[0]
            if b['training_source_sha256']!=SOURCE or b['identity']['config_sha256']!=result['config_sha256']:
                raise ValueError('Native training source/config identity changed')
            begins[str(rank)]=b
        if [v['global_step']for v in records]!=list(range(1,len(records)+1)):
            raise ValueError('Noncontiguous native optimizer updates')
        updates[rank]=records
    result.update(rank_snapshots=snapshots,real_native_train_begin=bool(begins),rank_train_begin=begins,
        actual_optimizer_step_rank0=len(updates[0]),all_rank_committed_optimizer_steps=min(map(len,updates.values())))
    if not any(updates.values()):result['exposure_status']='NOT_STARTED';return result
    if not job or job['training_source_sha256']!=SOURCE or job['config_sha256']!=result['config_sha256']:
        raise ValueError('Actual native job identity differs')
    common=result['all_rank_committed_optimizer_steps']
    mappings=[json.loads(line)for line in(F/pool/'SAMPLE_MAPPING-131072.jsonl').open()]
    index={}
    for row in mappings:
        key=row['input_sha256'],row['labels_sha256']
        if key in index:raise ValueError('Ambiguous immutable row mapping')
        index[key]=row
    classes={(r['split'],r['row_index']):r for r in(json.loads(line)for line in
        (R/'supplemental-nll-label-index-r1'/(pool+'-131072.jsonl')).open())}
    tasks=Counter();samples=Counter();targets=Counter();categories=Counter();phases=Counter();batches=Counter();epochs=defaultdict(Counter)
    supervised=0;inputs=0;rows=[]
    for rank in range(4):
        for update in updates[rank][:common]:
            step=update['global_step'];epoch=(step-1)//per_epoch+1
            if not update['batch_contract_verified']:raise ValueError('Native per-batch contract failed')
            for ordinal,batch in enumerate(update['model_input_batches']):
                key=batch['input_sha256'],batch['labels_sha256']
                if key not in index:raise ValueError('Native model input/labels are absent from frozen cache')
                row=index[key]
                if row['split']!='train':raise ValueError('Validation row entered actual training')
                if batch['supervised_tokens']!=row['supervised_tokens']or batch['nonpadding_tokens']!=row['input_tokens']:
                    raise ValueError('Native exposure token count differs from frozen mapping')
                tasks[row['task_id']]+=1;samples[row['row_index']]+=1;batches[step]+=1;epochs[epoch][row['row_index']]+=1
                supervised+=batch['supervised_tokens'];inputs+=batch['nonpadding_tokens']
                for span in classes[('train',row['row_index'])]['spans']:
                    n=span['end']-span['start'];categories[span['category']]+=n;phases[span['decision_stage']]+=n
                for target in row['decision_mapping']:targets[(row['trial_id'],target['call_id'])]+=1
                rows.append(dict(rank=rank,optimizer_step=step,epoch=epoch,microbatch_ordinal=ordinal,
                    task_id=row['task_id'],trial_id=row['trial_id'],row_index=row['row_index'],sample_sha256=row['sample_sha256'],
                    input_sha256=key[0],labels_sha256=key[1],supervised_tokens=batch['supervised_tokens'],input_tokens=batch['nonpadding_tokens'],
                    call_ids=[x['call_id']for x in row['decision_mapping']]))
    if supervised!=sum(categories.values())or supervised!=sum(phases.values()):raise ValueError('Supervision partition count differs')
    train={r['row_index']for r in mappings if r['split']=='train'}
    completed_epochs={}
    for epoch,row_counts in epochs.items():
        if common>=epoch*per_epoch:
            if set(row_counts)!=train:raise ValueError('Complete epoch did not expose exactly the fixed Train rows')
            completed_epochs[str(epoch)]=dict(unique_train_rows=len(row_counts),actual_sample_exposures=sum(row_counts.values()),
                sampler_padding_row_counts={str(k):v for k,v in row_counts.items()if v>1})
    for step,n in batches.items():
        if n!=(24 if step%per_epoch==0 else 32):raise ValueError('Actual native accumulation exposure differs from accepted sampler')
    path=R/'checks'/('ACTUAL_TRAINING_EXPOSURE_ROWS_'+stage+'_R1.jsonl');tmp=path.with_name(path.name+'.tmp')
    tmp.write_text(''.join(json.dumps(x)+'\n'for x in rows));tmp.replace(path)
    latest=[v[-1]for v in updates.values()if v]
    metrics=[v for v in rank_events[0]if v['event']=='metrics']
    result.update(exposure_status='PASS_FOR_ALL_RANK_COMMITTED_UPDATES',actual_independent_train_tasks=len(tasks),
        actual_unique_train_samples=len(samples),actual_sample_exposures=len(rows),actual_unique_assistant_targets=len(targets),
        actual_assistant_target_exposures=sum(targets.values()),supervised_token_exposures=supervised,visible_input_token_exposures=inputs,
        category_supervised_token_exposures=dict(categories),decision_stage_supervised_token_exposures=dict(phases),
        per_task_sample_exposures=dict(tasks),per_task_exposure_fraction={t:n/len(rows)for t,n in tasks.items()},
        exposure_fraction_is_not_custom_loss_weight=True,completed_epochs=completed_epochs,
        update_sample_counts=dict(batches),latest_metrics=metrics[-1]['metrics']if metrics else None,
        sampled_gradient_values_finite=all(g['finite']for u in latest for g in u['gradients'].values()),
        recorded_loss_and_gradient_norm_finite=all(math.isfinite(float(value))for event in metrics for key,value in event['metrics'].items()
            if key in ('loss','train_loss','eval_loss','grad_norm')and value is not None),
        latest_native_optimizer_state_dtypes={str(i):dict(master=u['master_partition_dtypes'],adam=u['optimizer_moment_dtypes'])for i,u in enumerate(latest)},
        max_memory_allocated=max(v['peak_allocated_bytes']for rank in updates.values()for v in rank),
        max_memory_reserved=max(v['peak_reserved_bytes']for rank in updates.values()for v in rank),
        exposure_rows_path=str(path),exposure_rows_sha256=sha(path),validation_training_exposures=0)
    state=result['trainer_state']or{}
    result['five_epochs_completed_and_final_hf_admitted']=bool(result['final_hf_admission']and result['final_hf_admission'].get('passed')
        and state.get('global_step')==planned and state.get('epoch',0)>=4.99 and common==planned)
    return result


def main():
    result=dict(checked_at=time.time(),source_sha256=sha(Path(__file__)),raw_training_or_frozen_data_modified=False,
        new_optimizer_or_gpu_calls=0,exposure_is_all_rank_committed_prefix=True,
        stages={stage:expose(stage,R/'runs'/folder,pool,per,planned)for stage,folder,pool,per,planned in STAGES})
    save(R/'checks/NATIVE_TRAINING_READOUT_R1.json',result)
    print(json.dumps({stage:{k:v.get(k)for k in ['actual_optimizer_step_rank0','all_rank_committed_optimizer_steps',
        'actual_independent_train_tasks','actual_sample_exposures','supervised_token_exposures','exposure_status',
        'five_epochs_completed_and_final_hf_admitted']}for stage,v in result['stages'].items()}))


if __name__=='__main__':main()
