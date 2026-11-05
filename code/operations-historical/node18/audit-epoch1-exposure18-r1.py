"""Map every real E1 microbatch to frozen CF Train Task/Trial/Call identity."""
from collections import Counter,defaultdict
import hashlib
import json
from pathlib import Path

R=Path('/ssd/chenkeyi/qwen35-sft-772-20261101')
F=R/'frozen-data-772-r3'


def main():
    mappings=[json.loads(line)for line in(F/'calibforge/SAMPLE_MAPPING-131072.jsonl').open()]
    index={}
    for row in mappings:
        key=row['input_sha256'],row['labels_sha256']
        assert key not in index;index[key]=row
    classes={(x['split'],x['row_index']):x for x in(json.loads(line)for line in
        (R/'supplemental-nll-label-index-r1/calibforge-131072.jsonl').open())}
    outputs=[];task_counts=Counter();row_counts=Counter();updates=Counter();supervised=0;visible=0
    category_counts=Counter();stage_counts=Counter();target_counts=Counter()
    rank_steps={}
    for rank in range(4):
        events=[json.loads(line)for line in(R/'runs/new-m1-cf416-128k-e5'/f'preflight-evidence-rank{rank}.jsonl').open()]
        records=[x for x in events if x['event']=='optimizer_step' and 1<=x['global_step']<=40]
        assert [x['global_step']for x in records]==list(range(1,41))
        rank_steps[str(rank)]=40
        for event in records:
            step=event['global_step']
            for ordinal,batch in enumerate(event['model_input_batches']):
                row=index[(batch['input_sha256'],batch['labels_sha256'])]
                assert row['split']=='train' and batch['supervised_tokens']==row['supervised_tokens']
                assert batch['nonpadding_tokens']==row['input_tokens']
                task_counts[row['task_id']]+=1;row_counts[row['row_index']]+=1;updates[step]+=1
                supervised+=batch['supervised_tokens'];visible+=batch['nonpadding_tokens']
                for span in classes[('train',row['row_index'])]['spans']:
                    count=span['end']-span['start'];category_counts[span['category']]+=count;stage_counts[span['decision_stage']]+=count
                for call in row['decision_mapping']:target_counts[(row['trial_id'],call['call_id'])]+=1
                outputs.append(dict(optimizer_step=step,rank=rank,microbatch_ordinal=ordinal,
                    task_id=row['task_id'],trial_id=row['trial_id'],row_index=row['row_index'],
                    sample_sha256=row['sample_sha256'],input_sha256=row['input_sha256'],labels_sha256=row['labels_sha256'],
                    supervised_tokens=batch['supervised_tokens'],input_tokens=batch['nonpadding_tokens'],
                    call_ids=[x['call_id']for x in row['decision_mapping']]))
    train=[x for x in mappings if x['split']=='train']
    assert set(row_counts)=={x['row_index']for x in train}and len(row_counts)==1270
    assert len(outputs)==1272 and len(task_counts)==374 and len(target_counts)==14407
    assert all(updates[s]==32 for s in range(1,40))and updates[40]==24
    assert supervised==sum(category_counts.values())==sum(stage_counts.values())
    out=R/'checks/NEW_M1_EPOCH1_EXPOSURE_ROWS.jsonl';assert not out.exists()
    out.write_text(''.join(json.dumps(x)+'\n'for x in outputs))
    result=dict(passed=True,optimizer_steps=40,rank_steps=rank_steps,independent_train_tasks=374,
        unique_train_samples=1270,actual_sample_exposures=1272,unique_assistant_targets=14407,
        actual_assistant_target_exposures=sum(target_counts.values()),supervised_token_exposures=supervised,
        visible_input_token_exposures=visible,category_supervised_token_exposures=dict(category_counts),
        decision_stage_supervised_token_exposures=dict(stage_counts),
        update_sample_counts=dict(updates),native_sampler_padding_samples={str(k):v for k,v in row_counts.items()if v>1},
        all_observed_rows_from_cf_fixed_train=True,validation_or_tmax_training_exposures=0,
        task_sample_exposures=dict(task_counts),task_exposure_fraction={k:v/1272 for k,v in task_counts.items()},
        task_fraction_is_exposure_not_a_custom_loss_weight=True,
        last_native_update_has_24_samples_configured_global_batch_is_32=True,
        row_mapping_sha256=hashlib.sha256(out.read_bytes()).hexdigest(),
        source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    (R/'checks/NEW_M1_EPOCH1_EXPOSURE_AUDIT.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items()if k not in ['task_sample_exposures','task_exposure_fraction','update_sample_counts']}))


if __name__=='__main__':main()
