"""Audit an immutable partial primary-index snapshot against native Qwen caches.

No tokenizer, template, targets or labels are rewritten. This is an interim
cache/mapping audit, not the final corpus release or a new success-index writer.
"""
from collections import Counter
import datetime
import fcntl
import gzip
import hashlib
import json
import os
import shutil
from pathlib import Path

S=Path('/ssd/chenkeyi/qwen35-new-cf500-tmax500-20261029')
D=S/'data-primary-snapshots/r238'


def sha(path):
    with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()


def audit():
    lock=(D/'audit.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    source=D/'INPUTS.json';inputs=json.loads(source.read_text())
    if (D/'PARTIAL_DATA_TARGET_AUDIT_R238.json').exists():raise FileExistsError('Observe existing immutable partial snapshot audit')
    report=dict(status='PARTIAL_PRIMARY_NATIVE_CACHE_AUDIT',checked_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        full_campaign_complete=False,formal_corpus_release=False,training_started=False,model_calls=0,
        snapshot_inputs_sha256=sha(source),source_sha256=sha(Path(__file__)),pools={},
        scope='First qualified success per Task at snapshot time; separate128K/256K views. Existing per-Trial official Loader/Collator/Serving/loss-gradient proofs retained. Final assembled corpus Loader audit remains required.')
    for pool in ['calibforge','tmax']:
        file=D/(pool.upper()+'_SUCCESS_INDEX.jsonl')
        if sha(file)!=inputs['files'][file.name]['sha256']:raise ValueError('Primary index snapshot changed')
        rows=[item for line in file.open() if (item:=json.loads(line))['is_primary_trajectory']]
        if len({x['task_id'] for x in rows})!=len(rows):raise ValueError('A Task has multiple primary trajectories')
        counts=dict(qualified_independent_tasks=len(rows),primary_trajectories=len(rows),planned_unique_tasks=500,
            fixed_splits=dict(Counter(x['split'] for x in rows)),original_assistant_targets=0,
            primary_trajectories_with_multiple_assistant_targets=sum(len(x['student_proof']['original_call_ids'])>1 for x in rows),
            original_supervision_token_classes={},qwen_revisions=[],encoder_sha256=[],length_views={})
        classes=Counter();versions=set();encoders=set()
        for row in rows:
            if not row['qualified_success'] or not row['is_primary_trajectory'] or row['classification']!='QUALIFIED_SUCCESS':raise ValueError('Unqualified row entered a primary snapshot')
            proof=row['student_proof']
            for key in ['semantic_projection_passed','exact_deployment_prefixes','all_original_targets_once','native_loader_and_collator_passed','native_streaming_and_nonstreaming_parsers_passed','native_loss_gradient_reference_passed']:
                if not proof[key]:raise ValueError('Unaccepted per-Trial student proof: '+key)
            if proof['source_journal_sha256']!=row['source_journal_sha256']:raise ValueError('Student/native source identity differs')
            calls=proof['original_call_ids']
            if len(calls)!=len(set(calls)):raise ValueError('Original Assistant target IDs repeat')
            counts['original_assistant_targets']+=len(calls);classes.update(proof['supervision_token_classes'])
            versions.add(proof['qwen_revision']);encoders.add(proof['encoder_sha256'])
        counts.update(original_supervision_token_classes=dict(classes),qwen_revisions=sorted(versions),encoder_sha256=sorted(encoders))
        if len(versions)!=1 or not encoders<={'8506585c55ea67585d2512a86a45b689f324a766ac1679fb98aba30a6170b947','68c2a68bb6d2c93d2981ca911eba22a880c29aaf817d7a45209a8da40da18d48'}:raise ValueError('Unreviewed student projection contract')
        for cutoff in [131072,262144]:
            totals=Counter();weights=[];mapping_file=D/(pool+'-'+str(cutoff)+'-sample-target-mapping.jsonl.gz')
            with gzip.open(mapping_file,'xt') as mapping:
                for task_index,item in enumerate(rows):
                    proof=item['student_proof'];view=proof['length_views'][str(cutoff)];cache=Path(view['cache'])
                    original_cache=cache
                    if sha(cache)!=view['cache_sha256']:raise ValueError('Native Qwen cache changed')
                    if not cache.resolve().is_relative_to(S):
                        # Preserve old Canary cache bytes and source proof; place
                        # a verified identical input copy on the current SSD.
                        mirror=D/'historical-cache-mirrors'/item['trial_id']/cache.name
                        mirror.parent.mkdir(parents=True,exist_ok=True)
                        with cache.open('rb') as source_stream,mirror.open('xb') as target_stream:
                            shutil.copyfileobj(source_stream,target_stream);target_stream.flush();os.fsync(target_stream.fileno())
                        if sha(mirror)!=view['cache_sha256']:raise ValueError('Historical cache SSD copy differs')
                        cache=mirror;totals['historical_cache_files_mirrored_to_ssd']+=1
                    original=proof['original_call_ids'];removed={x['call_id'] for x in view['quarantine']};seen=[];task_tokens=0;segments=0
                    with gzip.open(cache,'rb') as stream:
                        for ordinal,line in enumerate(stream):
                            value=json.loads(line);row=value['row'];e=value['evidence'];ids=row['input_ids'];labels=row['labels']
                            if len(ids)!=len(labels) or len(ids)!=len(row['attention_mask']) or len(ids)!=e['input_tokens']:raise ValueError('Native cache token dimensions differ')
                            if e['cutoff']!=cutoff or e['truncation'] or not e['overlap_history_input_only'] or not e['all_target_prefixes_exact']:raise ValueError('Native cache context or truncation contract differs')
                            native_length=((len(ids)+e['processor_tokens']+7)//8)*8
                            if native_length!=view['collated_lengths'][ordinal] or native_length>cutoff:raise ValueError('Formal processor/padding input+target length differs')
                            ranges=bytearray(len(ids));decisions=e['decision_mapping']
                            for decision in decisions:
                                begin,end=decision['supervised_range']
                                if not 0<=begin<end<=len(ids) or any(ranges[begin:end]):raise ValueError('Target label ranges overlap or escape a sample')
                                ranges[begin:end]=b'\1'*(end-begin);seen.append(decision['call_id'])
                            for token,label,supervised in zip(ids,labels,ranges):
                                if label!=(token if supervised else -100):raise ValueError('Token label differs from exact Assistant target ranges')
                            supervised=sum(ranges)
                            if supervised!=e['supervised_tokens']:raise ValueError('Native supervision token count differs')
                            task_tokens+=supervised;segments+=1;totals['input_plus_target_tokens']+=native_length
                            totals['cached_samples']+=1
                            totals['cached_samples_with_multiple_supervised_assistant_targets']+=len(decisions)>1
                            mapping.write(json.dumps(dict(pool=pool,task_id=item['task_id'],trial_id=item['trial_id'],split=item['split'],family_id=item['family_id'],
                                cutoff=cutoff,cache=str(cache),original_cache=str(original_cache),byte_identical_ssd_mirror=cache!=original_cache,cache_sha256=view['cache_sha256'],cache_row_ordinal=ordinal,
                                decompressed_sample_sha256=hashlib.sha256(line).hexdigest(),input_sha256=e['input_sha256'],labels_sha256=e['labels_sha256'],
                                input_plus_target_tokens=native_length,supervised_tokens=supervised,segment_index=e['segment_index'],targets=decisions),ensure_ascii=False)+'\n')
                    if len(seen)!=len(set(seen)) or set(seen)!=set(original)-removed or len(seen)!=view['targets']:raise ValueError('Each retained original target must be supervised exactly once')
                    if task_tokens!=view['supervised_tokens'] or segments!=view['segments']:raise ValueError('Native sample/segment/token summary differs')
                    end_retained=bool(original and original[-1] in seen)
                    totals.update(tasks_with_retained_targets=bool(seen),tasks_with_all_targets_once=set(seen)==set(original),
                        normal_closure_last_target_retained=end_retained,assistant_targets=len(seen),segments=segments,
                        supervised_tokens=task_tokens,quarantined_targets=len(removed))
                    weights.append(dict(task_id=item['task_id'],trial_id=item['trial_id'],split=item['split'],retained_targets=len(seen),
                        supervised_tokens=task_tokens,normal_closure_last_target_retained=end_retained))
                    progress=dict(status='PARTIAL_NATIVE_CACHE_TOKEN_AND_MAPPING_AUDIT',pool=pool,cutoff=cutoff,completed_tasks=task_index+1,planned_tasks=len(rows),last_task_id=item['task_id'],checked_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),model_calls=0,training_started=False)
                    temporary=D/'progress.pending';temporary.write_text(json.dumps(progress,indent=2));temporary.replace(D/'progress.json')
            for item in weights:
                item['share_of_pool_supervised_tokens']=item['supervised_tokens']/totals['supervised_tokens'] if totals['supervised_tokens'] else 0
            weights_file=D/(pool+'-'+str(cutoff)+'-task-supervision-weights.json')
            with weights_file.open('x') as stream:json.dump(dict(scope='Observed token contributions; no new training loss weighting policy introduced',tasks=weights),stream)
            counts['length_views'][str(cutoff)]=dict(totals,normal_closure_retention_fraction=totals['normal_closure_last_target_retained']/len(rows) if rows else None,
                mapping=str(mapping_file),mapping_sha256=sha(mapping_file),task_supervision_contributions=str(weights_file),task_supervision_contributions_sha256=sha(weights_file),
                length_definition='Full input+target including actual native processor overhead and padding; Qwen cache token IDs, not DeepSeek usage',
                sample_and_segment_definition='This cache stores one real-context segment per cached sample. Samples with multiple supervised Assistant targets are counted separately; Task/Trial/target counts remain independent')
        report['pools'][pool]=counts
        with (D/(pool.upper()+'_PARTIAL_DATA_MANIFEST_R238.json')).open('x') as stream:
            json.dump(dict(full_campaign_complete=False,formal_corpus_release=False,pool=pool,source_success_index_sha256=sha(file),**counts),stream,indent=2)
    with (D/'PARTIAL_DATA_TARGET_AUDIT_R238.json').open('x') as stream:json.dump(report,stream,indent=2)
    print(json.dumps(dict(report=str(D/'PARTIAL_DATA_TARGET_AUDIT_R238.json'),pools=report['pools'])),flush=True)


if __name__=='__main__':audit()
