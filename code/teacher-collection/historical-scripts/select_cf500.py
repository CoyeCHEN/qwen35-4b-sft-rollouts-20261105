"""Freeze 500 public task identities; not trajectories or paid dispatch."""
from collections import Counter,defaultdict
import datetime
import hashlib
import json
from pathlib import Path
import random
import re

ROOT=Path('/home/chenkeyi/workspace/RSI/runtime-evidence/qwen35-new-cf500-tmax500-20261029')
OLD=Path('/home/chenkeyi/workspace/RSI/runtime-evidence/qwen35-calibforge-ab-20261027')
DOWNLOAD=Path('/ssd/chenkeyi/qwen35-calibforge-ab-20261027/sources/calibforge-task-release')
REV='c2fae4c1f536461142b2a89a8b9423a8bc376088'
triage={r['task_id'] for r in map(json.loads,(OLD/'checks/task-source-overlap-triage.jsonl').open())
    if r.get('source_triage')=='QUARANTINE_NAMED_REFERENCE_DOMAIN'}
gpu=set(json.loads((OLD/'preflight-final-20261029/checks/release-audit.json').read_text())['gpu_source_hint_tasks'])
groups=defaultdict(list);excluded=Counter();seen=set()
for row in map(json.loads,(DOWNLOAD/'metadata.jsonl').open()):
    task=row['task_id'];text=' '.join(row['instruction'].split());sha=hashlib.sha256(text.encode()).hexdigest()
    if task in triage:excluded['named_reference_quarantine']+=1;continue
    if task in gpu:excluded['unverified_gpu_requirement']+=1;continue
    if task=='file-operations_20260501_000112_003':excluded['prior_canary_diagnostic_only']+=1;continue
    if sha in seen:excluded['duplicate_normalized_instruction']+=1;continue
    seen.add(sha);groups[row['category']].append(row)
rng=random.Random(42)
for category in sorted(groups):rng.shuffle(groups[category])
# Round-robin categories supplies diversity without ranking model success.
selected=[];families=set()
while len(selected)<500:
    progressed=False
    for category in sorted(groups):
        while groups[category]:
            row=groups[category].pop();family=re.sub(r'_\d+$','',row['task_id'])
            if family in families:excluded['candidate_same_generation_family']+=1;continue
            families.add(family);selected.append((row,family));progressed=True;break
        if len(selected)==500:break
    assert progressed, 'Not enough distinct public task candidate families'
rows=[]
for row,family in selected:
    split='validation' if int(hashlib.sha256(('42:'+family).encode()).hexdigest()[:8],16)%10==0 else 'train'
    rows.append(dict(task_id=row['task_id'],dataset='AweAI-Team/CalibForge',revision=REV,
        source_split='train',proposed_sft_split=split,task_group=family,category=row['category'],
        difficulty=row['difficulty'],source_path=str(DOWNLOAD/row['task_path']),relative_source_path=row['task_path'],
        docker_image=row['docker_image'],instruction_sha256=hashlib.sha256(row['instruction'].encode()).hexdigest(),
        normalized_instruction_sha256=hashlib.sha256(' '.join(row['instruction'].split()).encode()).hexdigest(),
        provenance='published_harbor_task',task_family_policy='Conservative source-generation ID; never split this family',
        evaluation_screen='Exact/lexical/named TB89 screen, not a proof against all semantic rewrites',
        new_campaign_only=True,old_teacher_trajectories_allowed=False,max_rollout_attempts=2,
        stop_after_first_qualified_success=True,environment_preparation='PENDING_ALL_SELECTED_TASKS',formal_sft_eligible=False))
destination=ROOT/'manifests/calibforge500-tasks.jsonl'
with destination.open('x') as stream:
    for row in rows:stream.write(json.dumps(row)+'\n')
result=dict(checked_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),dataset='AweAI-Team/CalibForge',
    revision=REV,tasks=500,unique_task_ids=len({r['task_id']for r in rows}),
    unique_normalized_instructions=len({r['normalized_instruction_sha256']for r in rows}),
    seed=42,selection='Category round-robin without observing teacher success; source family unique',
    category_counts=dict(Counter(r['category']for r in rows)),difficulty_counts=dict(Counter(r['difficulty']for r in rows)),
    proposed_sft_split_counts=dict(Counter(r['proposed_sft_split']for r in rows)),exclusions=dict(excluded),
    manifest_sha256=hashlib.sha256(destination.read_bytes()).hexdigest(),paid_requests=0,
    environment_ready=False,full_success_trajectory_count=0)
(ROOT/'checks/calibforge500-selection.json').write_text(json.dumps(result,indent=2));print(json.dumps(result))
