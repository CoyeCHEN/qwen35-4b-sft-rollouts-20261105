"""Derive token-class positions from frozen monotonic class counts; never retokenize or edit SFT."""
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import time
from datasets import load_from_disk
from transformers import AutoTokenizer

R=Path('/ssd/chenkeyi/qwen35-sft-772-20261101')
F=R/'frozen-data-772-r3'
OUT=R/'supplemental-nll-label-index-r1'
CLASSES=('thinking','thinking_boundary','body','action','ending')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def digest(v):return hashlib.sha256(json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def main():
    start=time.monotonic();release_sha=sha(F/'DATA_RELEASE.json')
    assert release_sha=='fa4f07c05af4a8156547dbdda1cba60fb20e3c8626cd41cd40de4694e5f54821'
    assert not OUT.exists(),'Do not overwrite an existing derived index'
    staging=OUT.with_name(OUT.name+'.staging');assert not staging.exists();staging.mkdir()
    tokenizer=AutoTokenizer.from_pretrained(R/'assets/source17-r1/student-tokenizer',local_files_only=True)
    summaries=[]
    for pool in ['calibforge','tmax']:
        root=F/pool;manifest=json.loads((root/'DATA_MANIFEST.json').read_text())
        targets={}
        for task in json.loads((root/'TASK_AUDIT.json').read_text()):
            path=root/task['target_mapping']['relative_path'];assert sha(path)==task['target_mapping']['sha256']
            for target in json.loads(path.read_text()):
                key=(target['trial_id'],target['call_id']);assert key not in targets;targets[key]=target
        for cutoff in [131072,262144]:
            cache=load_from_disk(str(root/('cache-'+str(cutoff))))
            mappings=[json.loads(line)for line in(root/('SAMPLE_MAPPING-'+str(cutoff)+'.jsonl')).open()]
            assigned=set();counts=Counter();nrows=0
            file=staging/(pool+'-'+str(cutoff)+'.jsonl')
            with file.open('x')as stream:
                for mapping in mappings:
                    row=cache[mapping['split']][mapping['row_index']]
                    ids,labels=row['input_ids'],row['labels']
                    assert digest(ids)==mapping['input_sha256'] and digest(labels)==mapping['labels_sha256']
                    spans=[];covered=0;previous_end=-1
                    for decision in mapping['decision_mapping']:
                        key=(mapping['trial_id'],decision['call_id']);assert key not in assigned;assigned.add(key)
                        target=targets[key];left,right=decision['supervised_range']
                        assert target['supervised_range']==[left,right]
                        assert target['generation_prefix_sha256']==decision['generation_prefix_sha256']
                        assert target['input_sha256']==decision['original_input_sha256']
                        assert left>=previous_end and right>left and labels[left:right]==ids[left:right]
                        assert sum(target['supervision_token_classes'].values())==right-left
                        assert target['classification_policy']=='Token assigned by starting character offset in official rendered target'
                        position=left
                        # This is precisely the ordered if/elif partition in the frozen
                        # teacher_segments.py encoder, including indivisible boundary tokens.
                        for category in CLASSES:
                            count=target['supervision_token_classes'][category]
                            if count:
                                end=position+count
                                spans.append(dict(start=position,end=end,category=category,call_id=target['call_id'],
                                    decision_stage=target['stage'],closing_target=target['closing_target'],
                                    has_finish=target['target_has_finish']))
                                counts[(mapping['split'],category)]+=count
                                if category=='ending':assert count==1 and ids[position]==tokenizer.eos_token_id
                                position=end
                        assert position==right
                        covered+=right-left;previous_end=right
                    assert covered==sum(v!=-100 for v in labels)==mapping['supervised_tokens']
                    stream.write(json.dumps(dict(pool=pool,cutoff=cutoff,split=mapping['split'],
                        task_id=mapping['task_id'],trial_id=mapping['trial_id'],row_index=mapping['row_index'],
                        sample_sha256=mapping['sample_sha256'],input_sha256=mapping['input_sha256'],
                        labels_sha256=mapping['labels_sha256'],input_tokens=len(ids),spans=spans),ensure_ascii=False)+'\n')
                    nrows+=1
            for split in ['train','validation']:
                expected=manifest['length_views'][str(cutoff)][split]
                assert all(counts[(split,k)]==expected['supervision_token_classes'][k]for k in CLASSES)
            expected=sum(manifest['length_views'][str(cutoff)][s]['retained_targets']for s in ['train','validation'])
            assert len(assigned)==expected
            summaries.append(dict(pool=pool,cutoff=cutoff,rows=nrows,targets=len(assigned),file=file.name,
                sha256=sha(file),category_tokens={s:{k:counts[(s,k)]for k in CLASSES}for s in ['train','validation']}))
    assert sha(F/'DATA_RELEASE.json')==release_sha
    result=dict(passed=True,source_data_release_sha256=release_sha,files=summaries,
        frozen_sft_cache_modified=False,input_ids_or_labels_rewritten=False,new_teacher_or_model_calls=0,
        source_sha256=sha(Path(__file__)),elapsed_seconds=time.monotonic()-start,
        position_semantics='Unpadded frozen Qwen cache positions. Native SGLang input_ids scoring uses the same visible tokens. LF processor masked placeholders are not reintroduced into deployment history.',
        classification_semantics='Exact monotonic class counts from frozen teacher_segments encoder; no new string heuristics and no retokenization.')
    (staging/'LABEL_CLASS_INDEX_AUDIT.json').write_text(json.dumps(result,indent=2)+'\n')
    staging.rename(OUT);print(json.dumps(result),flush=True)


if __name__=='__main__':main()
