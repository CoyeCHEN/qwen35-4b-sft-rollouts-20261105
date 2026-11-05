"""Select/extract public TMax tasks and reuse its pinned upstream Harbor converter.

Never read solutions for selection or expose task.json/truth in the build context.
"""
from collections import Counter,defaultdict
import datetime
import hashlib
import importlib.util
import json
from pathlib import Path, PurePosixPath
import random
import re
import stat
import sys
import tomllib
import zipfile

ROOT=Path('/home/chenkeyi/.local/share/harbor-rsi/qwen35-new-cf500-tmax500-20261029')
ARCHIVE=ROOT/'sources/tmax/tasks.zip'
RAW=ROOT/'sources/tmax/selected-raw';HARBOR=ROOT/'sources/tmax/selected-harbor'
REV='e3ded940596cc611c9815684ba51a7e8ee0cffc9'
spec=importlib.util.spec_from_file_location('upstream_tmax_harbor',ROOT/'scripts/upstream-convert-to-harbor.py')
converter=importlib.util.module_from_spec(spec);spec.loader.exec_module(converter)
base_post,base_env=converter.load_intricate_base(ROOT/'scripts/base_intricate.def')
base_sha=hashlib.sha256((ROOT/'scripts/base_intricate.def').read_bytes()).hexdigest()
source=json.loads((ROOT/'checks/tmax-native-converter.json').read_text())
assert source['commit_pinned_blob_matches']
assert hashlib.sha256((ROOT/'scripts/upstream-convert-to-harbor.py').read_bytes()).hexdigest()==source['source_sha256']
cf=[json.loads(line)for line in (ROOT/'manifests/calibforge500-tasks.jsonl').open()]
cf_hashes={r['normalized_instruction_sha256']for r in cf}
tb=Path('/home/chenkeyi/.local/share/harbor-rsi/near-r3-20261015/tb21-formal-20261015T023432Z/tasks')
tb_hashes={hashlib.sha256(' '.join(p.read_text().split()).encode()).hexdigest()for p in tb.glob('*/instruction.md')}
assert len(tb_hashes)==89
groups=defaultdict(list);excluded=Counter();member_index=defaultdict(list);safety=[]


def sha(data):return hashlib.sha256(data).hexdigest()


with zipfile.ZipFile(ARCHIVE)as archive:
    infos=archive.infolist();names={i.filename for i in infos}
    assert len(names)==len(infos),'Duplicate zip member paths'
    for info in infos:
        path=PurePosixPath(info.filename)
        assert not path.is_absolute() and '..'not in path.parts,'Unsafe archive path'
        assert stat.S_IFMT(info.external_attr>>16)!=stat.S_IFLNK,'Archive symlink requires explicit review'
        if path.parts:member_index[path.parts[0]].append(info)
    total=0;seen=set()
    for name in sorted(n for n in names if n.endswith('/task.json')):
        total+=1;data=json.loads(archive.read(name));task=name.split('/')[0]
        if data.get('name')!=task:excluded['task_identity_mismatch']+=1;continue
        description=data.get('description','');normalized=' '.join(description.split());ident=sha(normalized.encode())
        if not normalized:excluded['empty_instruction']+=1;continue
        if ident in seen:excluded['duplicate_normalized_instruction']+=1;continue
        seen.add(ident)
        if ident in cf_hashes:excluded['same_instruction_as_CF500']+=1;continue
        if ident in tb_hashes:excluded['same_instruction_as_TB89']+=1;continue
        if data.get('fixture_kind')in ('image','audio','video'):
            excluded['explicit_multimodal_fixture_outside_text_SFT_scope']+=1;continue
        required={task+'/container.def',task+'/test_final_state.py'}
        if not required<=names:excluded['missing_environment_or_verifier']+=1;continue
        # This inventory uses public task metadata, never the truth/solutions fields.
        groups[data.get('domain','unknown')].append(dict(task_id=task,domain=data.get('domain'),
            skill_type=data.get('skill_type'),task_complexity=data.get('task_complexity'),
            fixture_kind=data.get('fixture_kind'),base_image=data.get('base_image'),description=description,
            instruction_sha256=sha(description.encode()),normalized_instruction_sha256=ident,
            original_task_json_sha256=sha(archive.read(name))))
    rng=random.Random(42)
    for category in sorted(groups):rng.shuffle(groups[category])
    selected=[];families=set()
    RAW.mkdir(parents=True,exist_ok=False);HARBOR.mkdir(exist_ok=False)
    while len(selected)<500:
        progressed=False
        for category in sorted(groups):
            while groups[category]:
                row=groups[category].pop();task=row['task_id'];family=task.rsplit('_',1)[0]
                if family in families:excluded['same_generation_index_candidate_family']+=1;continue
                task_dir=RAW/task;task_dir.mkdir()
                # Exclude all prior solutions; verifier stays in a host-side source directory.
                records=[]
                for info in member_index[task]:
                    relative=PurePosixPath(info.filename).relative_to(task)
                    if not relative.parts or relative.parts[0]=='solutions':continue
                    output=task_dir.joinpath(*relative.parts)
                    if info.is_dir():output.mkdir(parents=True,exist_ok=True);continue
                    output.parent.mkdir(parents=True,exist_ok=True);data=archive.read(info)
                    with output.open('xb')as stream:stream.write(data)
                    mode=(info.external_attr>>16)&0o777
                    if mode:output.chmod(mode)
                    records.append(dict(path=str(relative),sha256=sha(data),bytes=len(data)))
                pairs=converter.parse_files_section(task_dir/'container.def');problem=None
                for src,dst in pairs:
                    resolved=converter._resolve_fixture_src(src,task_dir)
                    if resolved is None or not resolved.resolve().is_relative_to(task_dir.resolve()):
                        problem='UNAVAILABLE_OR_EXTERNAL_HOST_FIXTURE';break
                    target=PurePosixPath(dst)
                    if '..'in target.parts or any(c.isspace()for c in dst):problem='UNSAFE_FIXTURE_DESTINATION';break
                if problem:
                    excluded[problem]+=1;safety.append(dict(task_id=task,reason=problem,raw_preserved=str(task_dir)));continue
                converted=converter.convert_task(task_dir,HARBOR,intricate_base_post=base_post,
                    intricate_env=base_env,intricate_base_image_tag=None)
                assert converted==task
                output=HARBOR/task
                assert (output/'instruction.md').read_text()==row['description']
                assert sha((output/'tests/test_final_state.py').read_bytes())==sha((task_dir/'test_final_state.py').read_bytes())
                assert not (output/'environment/task.json').exists() and not list((output/'environment').rglob('solutions'))
                config=tomllib.loads((output/'task.toml').read_text())
                # Parse with the actual native Harbor contract before publishing identities.
                from harbor.models.task.config import TaskConfig
                parsed=TaskConfig.model_validate(config)
                files=[dict(path=str(p.relative_to(output)),sha256=sha(p.read_bytes()),bytes=p.stat().st_size)
                    for p in sorted(output.rglob('*'))if p.is_file()]
                split='validation'if int(sha(('42:tmax:'+family).encode())[:8],16)%10==0 else'train'
                public={k:v for k,v in row.items()if k!='description'}
                selected.append(public|dict(dataset='allenai/TMax-15K',revision=REV,source_split='train',
                    task_group='tmax:'+family,proposed_sft_split=split,execution_path=str(output),
                    source_task_path=str(task_dir),original_source_files=records,derived_harbor_files=files,
                    converter_commit=source['commit_sha'],converter_sha256=source['source_sha256'],base_intricate_sha256=base_sha,
                    original_verifier_unchanged=True,reference_solutions_excluded=True,
                    environment_build_status='NOT_BUILT',max_rollout_attempts=2,first_qualified_success_stops=True,
                    formal_sft_eligible=False))
                families.add(family);progressed=True;break
            if len(selected)==500:break
        assert progressed,'Not enough supported distinct public task families'
destination=ROOT/'manifests/tmax500-tasks.jsonl'
with destination.open('x')as stream:
    for row in selected:stream.write(json.dumps(row)+'\n')
summary=dict(checked_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),source_tasks=total,selected_tasks=500,
    source_archive_sha256='59e2efd8785d68214f4f8f61c383ef806dff9778d965af5d13cf45f02e3dc106',revision=REV,
    archive_members=len(infos),unique_task_ids=len({r['task_id']for r in selected}),
    domain_counts=dict(Counter(r['domain']for r in selected)),split_counts=dict(Counter(r['proposed_sft_split']for r in selected)),
    exclusions=dict(excluded),fixture_safety_rejections=safety,manifest_sha256=sha(destination.read_bytes()),
    upstream_converter_reused=True,verifiers_changed=False,solutions_exposed_to_teacher=False,
    native_task_configs_valid=500,environments_built=0,paid_model_requests=0,
    cross_source_and_TB89_exact_instruction_matches=0,
    semantic_overlap_proof='UNVERIFIED beyond normalized exact matching; source and family review still recorded')
(ROOT/'checks/tmax500-selection.json').write_text(json.dumps(summary,indent=2));print(json.dumps(summary),flush=True)
