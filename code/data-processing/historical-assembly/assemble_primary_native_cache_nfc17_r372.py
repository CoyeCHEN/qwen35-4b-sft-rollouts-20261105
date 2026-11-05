"""Assemble exactly audited native token rows, then use the frozen LF full audit.

This finite CPU data job cannot release a corpus, train, or call a teacher.
Native per-Trial caches and target evidence stay unchanged. All outputs use SSD.
"""
import argparse
from collections import Counter
import datetime
import fcntl
import gzip
import hashlib
import inspect
import json
import os
from pathlib import Path

os.environ['CUDA_VISIBLE_DEVICES']=''
from sft.public_corpus import admitted_records,file_sha,stage,uniform_segment_mean_weights
from sft.public_corpus_audit import audit_corpus
from sft.qwen35 import digest,REVISION,TEMPLATE_SHA

SSD=Path('/ssd/chenkeyi/qwen35-new-cf500-tmax500-20261029')
ENCODER_SHA='68c2a68bb6d2c93d2981ca911eba22a880c29aaf817d7a45209a8da40da18d48'
LEGACY_ENCODER_SHA='8506585c55ea67585d2512a86a45b689f324a766ac1679fb98aba30a6170b947'
CAPS=(131072,262144)
CLASSES=('thinking','thinking_boundary','body','action','ending')
read=lambda path:json.loads(Path(path).read_bytes())


def write_json(path,value):
    with path.open('x') as stream:json.dump(value,stream,ensure_ascii=False,indent=2)
    return file_sha(path)


def native_rows(files):
    """Side-effect-free HF generator over exact immutable native cache files."""
    for name,expected in files:
        path=Path(name)
        if file_sha(path)!=expected:raise ValueError('Native token cache changed')
        with gzip.open(path,'rt') as stream:
            for line in stream:yield json.loads(line)['row']


CANONICAL_BACKEND_SHA='027a3f1c30acd5438805f34bb427a99772640beba2a4e5153ada9c90fc259281'


def canonical_binding(record):
    """Bind each unchanged cache to the accepted training and serving backend."""
    resource=SSD/'student-tokenizer-r155'
    if file_sha(resource/'tokenizer.json')!='5f9e4d4901a92b997e463c1f46055088b6cca5ca61a6522d1b9f64c4bb81cb42' or file_sha(resource/'tokenizer_config.json')!='3dd1cee8a0cb8f51800bcb47bd157eeef5bda2d39c85b7569892b9af95170071':
        raise ValueError('Accepted canonical tokenizer resource changed')
    proof=record['student_proof'];contract=proof.get('student_tokenizer_runtime_contract')
    if contract:
        if contract['backend_semantics_sha256']!=CANONICAL_BACKEND_SHA or contract['model_resource']!=str(resource) or contract['source_manifest_sha256']!=file_sha(resource/'SOURCE_MANIFEST_R155.json'):
            raise ValueError('Per-Trial tokenizer runtime contract differs')
        return dict(scope='Full per-Trial canonical training/Loader/serving acceptance',runtime_contract=contract)
    evidence={}
    gap_file=SSD/'data-canonical-gaps-r239/PLAN.json'
    gap=read(gap_file)
    if gap['input_manifest_sha256']!=file_sha(SSD/'data-primary-snapshots/r238/INPUTS.json'):
        raise ValueError('Canonical gap plan belongs to another input snapshot')
    missing={x['trial_id']:x for x in gap['missing_two_runtime_revalidation']}
    cohort='data-canonical-primary-r240' if record['trial_id'] in missing else 'data-canonical-primary-r161'
    for label in ['training','serving']:
        directory=SSD/cohort/label
        identity=read(directory/'IDENTITY.json')
        if cohort=='data-canonical-primary-r240' and identity['gap_manifest_sha256']!=file_sha(gap_file):
            raise ValueError('Canonical gap cohort provenance changed')
        if identity['backend_semantics_sha256']!=CANONICAL_BACKEND_SHA or identity['encoder_sha256']!=LEGACY_ENCODER_SHA or identity['model_resource']!=str(resource):
            raise ValueError('Historical canonical revalidation runtime differs')
        path=directory/(record['trial_id']+'.json');row=read(path)
        if any(row[key]!=record[key] for key in ['task_id','trial_id','source_journal_sha256','result_sha256']) or row['source_export_sha256']!=proof['raw_export_sha256']:
            raise ValueError('Historical canonical revalidation source differs')
        if not row['passed'] or row['errors'] or row['mismatches'] or not row['all_original_targets_compared_once'] or row['compared_targets']!=len(proof['original_call_ids']):
            raise ValueError('Historical canonical target revalidation is incomplete')
        evidence[label]=dict(path=str(path),sha256=file_sha(path),runtime_identity_sha256=file_sha(directory/'IDENTITY.json'))
    return dict(scope='Every historical target reprojected under both accepted runtimes; original cache unchanged',proofs=evidence)


def target_evidence(record):
    proof=record['student_proof']
    for key in ['semantic_projection_passed','exact_deployment_prefixes','all_original_targets_once',
            'native_loader_and_collator_passed','native_streaming_and_nonstreaming_parsers_passed',
            'native_loss_gradient_reference_passed']:
        if proof.get(key) is not True:raise ValueError('Incomplete native student evidence: '+key)
    if proof['qwen_revision']!=REVISION or proof['encoder_sha256'] not in [LEGACY_ENCODER_SHA,ENCODER_SHA]:
        raise ValueError('Frozen student contract differs')
    cache=Path(proof['length_views']['262144']['cache'])
    root=cache.parent.parent.parent
    bundle=read(root/'checks/STUDENT_AUDIT_TRIALS_ALL.json')
    artifact=bundle['proofs']['canary-qwen-projection-all-v4.json']
    projection=Path(artifact['path'])
    if file_sha(projection)!=artifact['sha256']:raise ValueError('Frozen projection evidence changed')
    matches=[x for x in read(projection) if x['trial_id']==record['trial_id']]
    if len(matches)!=1:raise ValueError('No unique native projection record')
    item=matches[0];path=Path(item['target_mapping'])
    if item['errors'] or item['raw_export_sha256']!=proof['raw_export_sha256']:
        raise ValueError('Projection is not bound to the qualified source')
    if file_sha(path)!=item['target_mapping_sha256']:raise ValueError('Native target evidence changed')
    targets=read(path)
    if [x['call_id'] for x in targets]!=proof['original_call_ids']:raise ValueError('Original targets differ')
    totals={key:sum(x['supervision_token_classes'][key] for x in targets) for key in CLASSES}
    if totals!=proof['supervision_token_classes']:raise ValueError('Target supervision classes differ')
    return targets,dict(path=str(path),sha256=item['target_mapping_sha256'],projection_path=str(projection),projection_sha256=artifact['sha256'])


def assemble_pool(pool,records,inputs,output,provenance):
    from datasets import Dataset,DatasetDict,Features,Sequence,Value

    selected=admitted_records(records,pool)
    output.mkdir(exist_ok=False)
    features=Features({name:Sequence(Value('string' if name in ['images','videos','audios'] else 'int64'))
        for name in ['input_ids','attention_mask','labels','images','videos','audios']})
    mappings={cap:[] for cap in CAPS};descriptors={cap:{split:[] for split in ['train','validation']} for cap in CAPS}
    tasks=[];quarantine=[];artifacts={};families={}
    for record in selected:
        source={key:record[key] for key in ['pool','task_id','trial_id','split','family_id','source_revision','source_journal_sha256','result_sha256']}
        source['raw_export_sha256']=record['student_proof']['raw_export_sha256']
        split=record['split'];families[record['family_id']]=split
        canonical=canonical_binding(record)
        targets,origin=target_evidence(record);by_id={x['call_id']:x for x in targets}
        target_path=output/(record['trial_id']+'-targets.json')
        artifacts[target_path.name]=write_json(target_path,[dict(**source,ordinal=i,stage=stage(i,len(targets)),
            closing_target=i==len(targets)-1,**item) for i,item in enumerate(targets)])
        task=dict(**source,original_targets=len(targets),target_mapping=dict(relative_path=target_path.name,
            sha256=artifacts[target_path.name]),native_target_evidence=origin,canonical_tokenizer_acceptance=canonical,views={})
        for cap in CAPS:
            declared=record['student_proof']['length_views'][str(cap)]
            original_cache=Path(declared['cache']);cache=original_cache
            if not cache.resolve().is_relative_to(SSD):
                cache=inputs/'historical-cache-mirrors'/record['trial_id']/cache.name
            if not cache.resolve().is_relative_to(SSD) or file_sha(cache)!=declared['cache_sha256']:
                raise ValueError('Expected identical SSD native cache unavailable')
            descriptors[cap][split].append((str(cache),declared['cache_sha256']))
            removed={x['call_id'] for x in declared['quarantine']};seen=[];segments=0;tokens=0;multi=0;collated=0
            for entry in declared['quarantine']:quarantine.append(dict(**source,quarantine='OVERLONG_DECISION',**entry))
            with gzip.open(cache,'rt') as stream:
                for ordinal,line in enumerate(stream):
                    item=json.loads(line);row=item['row'];e=item['evidence']
                    if any(row[name] for name in ['images','videos','audios']):raise ValueError('Unsupported multimodal rows require a separate processor audit')
                    if e['truncation'] or not e['overlap_history_input_only'] or not e['all_target_prefixes_exact'] or e['cutoff']!=cap or e['processor_tokens']!=66:
                        raise ValueError('Native context/length contract differs')
                    length=((len(row['input_ids'])+66+7)//8)*8
                    if length!=declared['collated_lengths'][ordinal] or length>cap:raise ValueError('Native input+target+processor/padding differs')
                    if digest(row['input_ids'])!=e['input_sha256'] or digest(row['labels'])!=e['labels_sha256']:
                        raise ValueError('Native token IDs or labels changed')
                    for decision in e['decision_mapping']:
                        target=by_id[decision['call_id']]
                        if decision['generation_prefix_sha256']!=target['generation_prefix_sha256'] or decision['original_input_sha256']!=target['input_sha256']:
                            raise ValueError('Sample target not bound to its original deployment prefix')
                        seen.append(decision['call_id'])
                    index=sum(m['split']==split for m in mappings[cap])
                    mappings[cap].append(dict(**source,row_index=index,sample_sha256=digest(row),
                        native_cache=str(cache),native_cache_sha256=declared['cache_sha256'],native_cache_row_ordinal=ordinal,**e))
                    segments+=1;tokens+=e['supervised_tokens'];multi+=len(e['decision_mapping'])>1;collated+=length
            expected=[x['call_id'] for x in targets if x['call_id'] not in removed]
            if seen!=expected or len(seen)!=declared['targets'] or segments!=declared['segments'] or tokens!=declared['supervised_tokens']:
                raise ValueError('Retained original targets must occur exactly once in order')
            classes={key:sum(by_id[ident]['supervision_token_classes'][key] for ident in seen) for key in CLASSES}
            if sum(classes.values())!=tokens:raise ValueError('Retained token classes differ from labels')
            task['views'][str(cap)]=dict(original_targets=len(targets),retained_targets=len(seen),segments=segments,
                multi_assistant_samples=multi,supervised_tokens=tokens,input_plus_target_qwen_tokens=collated,
                all_targets_retained=not removed,closing_target_retained=bool(targets and targets[-1]['call_id'] in seen),
                supervision_token_classes=classes,stage_target_counts={name:sum(stage(i,len(targets))==name and target['call_id'] in seen for i,target in enumerate(targets)) for name in ['early','middle','late']})
        tasks.append(task)
    summaries={}
    for cap in CAPS:
        cache_path=output/('cache-'+str(cap));parts={};summaries[str(cap)]={}
        for split in ['train','validation']:
            if descriptors[cap][split]:
                parts[split]=Dataset.from_generator(native_rows,features=features,gen_kwargs=dict(files=descriptors[cap][split]),
                    cache_dir=str(output/'generator-cache'/str(cap)/split),writer_batch_size=1)
            else:parts[split]=Dataset.from_dict({key:[] for key in features},features=features)
            subset=[m for m in mappings[cap] if m['split']==split]
            weights=uniform_segment_mean_weights(subset)
            for mapping,coefficient in zip(subset,weights['per_token_coefficients']):
                mapping['uniform_segment_mean_per_supervised_token_coefficient']=coefficient
            members=[t for t in tasks if t['split']==split];views=[t['views'][str(cap)] for t in members]
            totals={key:sum(v[key] for v in views) for key in ['original_targets','retained_targets','segments','multi_assistant_samples','supervised_tokens','input_plus_target_qwen_tokens']}
            summaries[str(cap)][split]=dict(qualified_tasks=len(members),semantically_projected_tasks=len(members),
                retained_independent_tasks=sum(v['retained_targets']>0 for v in views),complete_tasks=sum(v['all_targets_retained'] for v in views),
                closing_tasks=sum(v['closing_target_retained'] for v in views),**totals,
                supervision_token_classes={key:sum(v['supervision_token_classes'][key] for v in views) for key in CLASSES},
                stage_target_counts={name:sum(v['stage_target_counts'][name] for v in views) for name in ['early','middle','late']},
                task_segment_share={t['task_id']:weights['task_segment_share'].get(t['task_id'],0) for t in members},
                task_supervised_token_share={t['task_id']:t['views'][str(cap)]['supervised_tokens']/totals['supervised_tokens'] if totals['supervised_tokens'] else 0 for t in members})
        DatasetDict(parts).save_to_disk(str(cache_path))
        mapping_path=output/('SAMPLE_MAPPING-'+str(cap)+'.jsonl')
        with mapping_path.open('x') as stream:
            for item in mappings[cap]:stream.write(json.dumps(item,ensure_ascii=False)+'\n')
        artifacts[mapping_path.name]=file_sha(mapping_path)
        for path in cache_path.rglob('*'):
            if path.is_file():artifacts[str(path.relative_to(output))]=file_sha(path)
    artifacts['TASK_AUDIT.json']=write_json(output/'TASK_AUDIT.json',tasks)
    artifacts['QUARANTINE.json']=write_json(output/'QUARANTINE.json',quarantine)
    manifest=dict(status='STAGING_PENDING_FULL_CACHE_LOADER_AND_COLLATOR_AUDIT',pool=pool,provenance=provenance,
        qualified_independent_tasks=len(selected),primary_trajectories=len(selected),semantically_projected_tasks=len(tasks),
        qualified_success_is_not_a_length_retention_count=True,length_views=summaries,family_splits=families,artifacts=artifacts,
        canonical_model_resource=str(SSD/'student-tokenizer-r155'),canonical_backend_semantics_sha256=CANONICAL_BACKEND_SHA,processor_extra_tokens=66,pad_to_multiple_of=8,cap_includes_input_target_processor_and_padding=True,
        target_policy='Full Thinking+Action; each retained original Assistant target exactly once; overlapping history input only',
        historical_thinking_policy='Pinned official Qwen Jinja last-real-user policy, identical at serving',
        reasoning_projection='DeepSeek reasoning_content to official Qwen field; provider-private signatures omitted',
        observation_basis='Actual provider payload after toolResultBudget; no history or larger raw observation restored',
        unsupported_multimodal_policy='Whole-trace quarantine by qualification; never remove images and retain dependent targets',
        stage_policy='Chronological original-decision thirds, not inferred quality stages',
        multi_assistant_sample_definition='A segment containing at least two newly supervised Assistant targets',
        token_and_label_rewrites=0,truncation=False,released=False)
    write_json(output/'DATA_MANIFEST.json',manifest)
    return manifest


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input-snapshot',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();inputs=args.input_snapshot.resolve();output=args.output.resolve()
    if not inputs.is_relative_to(SSD) or not output.is_relative_to(SSD) or output.exists():raise ValueError('New output and inputs must be on campaign SSD')
    contract=read(inputs/'INPUTS.json');prior=read(inputs/'PARTIAL_DATA_TARGET_AUDIT_R238.json')
    if prior['snapshot_inputs_sha256']!=file_sha(inputs/'INPUTS.json'):raise ValueError('Prior complete token audit inputs differ')
    for name,identity in contract['files'].items():
        if Path(name).name!=name or file_sha(inputs/name)!=identity['sha256']:raise ValueError('Immutable source index snapshot changed')
    source=Path(inspect.getfile(audit_corpus)).parent
    expected={'public_corpus.py':'f28b1d3a0cbc28ceda3bd9eda188bb8240d972f078c3313472297d364d7f66e5',
        'public_corpus_audit.py':'ff9d66dd6f9a1e97248fb4dd057d25497227099b8aa28ce4f09f2c4c66fc63aa',
        'teacher_segments.py':ENCODER_SHA}
    if any(file_sha(source/name)!=sha for name,sha in expected.items()):raise ValueError('Frozen native student audit source changed')
    output.mkdir(parents=True,exist_ok=False)
    lock=(output/'assembly.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    provenance=dict(scope='PARTIAL_COMBINED_NATIVE_CACHE_ACCEPTANCE',full_campaign_complete=False,formal_corpus_release=False,
        input_snapshot=str(inputs),input_snapshot_sha256=file_sha(inputs/'INPUTS.json'),input_indexes=contract['files'],
        source_sha256=file_sha(Path(__file__)),native_audit_source_sha256=expected,qwen_revision=REVISION,official_template_sha256=TEMPLATE_SHA,
        serving_policy=dict(enable_thinking=True,reasoning_parser='qwen3',tool_call_parser='qwen3_coder',force_reasoning=True,separate_reasoning=True),
        token_source='Byte/hash-verified native per-Trial caches; no retokenization or rewriting')
    write_json(output/'PLAN.json',provenance)
    report=dict(status='PARTIAL_COMBINED_CACHE_FORMAL_LOADER_AUDIT',pools={},full_campaign_complete=False,formal_corpus_release=False,
        model_calls=0,training_started=False,source_sha256=file_sha(Path(__file__)))
    for pool in ['calibforge','tmax']:
        records=[]
        for kind in ['SUCCESS_INDEX','FAILURE_OR_PENDING_INDEX']:
            records.extend(json.loads(line) for line in (inputs/(pool.upper()+'_'+kind+'.jsonl')).open())
        manifest=assemble_pool(pool,records,inputs,output/pool,provenance)
        audit=audit_corpus(output/pool,model_path=str(SSD/'student-tokenizer-r155'))
        if not audit['passed']:raise ValueError('Formal combined-cache native audit failed')
        report['pools'][pool]=dict(qualified_independent_tasks=manifest['qualified_independent_tasks'],
            manifest_sha256=file_sha(output/pool/'DATA_MANIFEST.json'),formal_loader_audit_sha256=file_sha(output/pool/'NATIVE_CACHE_AUDIT.json'),
            all_row_labels_verified=audit['all_row_labels_checked'],numerical_reference=audit['numerical_reference'],
            cached_rows=len(audit['rows']),length_views=manifest['length_views'],source_failure_or_pending_classifications=dict(Counter(x['classification'] for x in records if not x['qualified_success'])))
    report['checked_at']=datetime.datetime.now(datetime.timezone.utc).isoformat()
    write_json(output/'DATA_AUDIT_PARTIAL.json',report)
    print(json.dumps(dict(report=str(output/'DATA_AUDIT_PARTIAL.json'),pools={pool:v['qualified_independent_tasks'] for pool,v in report['pools'].items()},formal_release=False)),flush=True)


if __name__=='__main__':main()
