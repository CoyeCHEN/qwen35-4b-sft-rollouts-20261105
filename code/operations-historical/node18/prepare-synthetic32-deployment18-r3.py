"""Explicit image provenance repair; no Task edits, builds, or Trial dispatch."""
import argparse,hashlib,json,os,re,runpy,shlex,shutil,subprocess,time
from pathlib import Path
R=Path('/ssd/chenkeyi/qwen35-sft-772-20261101');B=R/'synthetic32';E=R/'formal-native-eval-r1'
SOURCE_SHA='0cf3b68f4514534353284159432262cc1cebb0caba40df434df684e6d63662d5'
REBUILD={'custom-memory-heap-crash--r002--openharness','fix-git--r001--openharness','query-optimize--r002--openharness'}
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_text())
def write_new(p,value):
 p.parent.mkdir(parents=True,exist_ok=True);raw=json.dumps(value,indent=2)+'\n'
 if p.exists():assert p.read_text()==raw,str(p)
 else:
  temp=p.with_name(p.name+'.tmp');temp.write_text(raw);temp.replace(p)
def files(root):return {p.relative_to(root).as_posix():dict(sha256=sha(p),bytes=p.stat().st_size,mode=p.stat().st_mode&0o777)for p in sorted(root.rglob('*'))if p.is_file()}
def image_details(endpoint,tags):
 p=subprocess.run(['docker','--host',endpoint,'image','inspect',*sorted(tags)],capture_output=True,text=True,timeout=25)
 if p.returncode:raise RuntimeError('Required published/base images unavailable: '+p.stderr[-1000:])
 result={}
 for x in json.loads(p.stdout):
  for tag in x.get('RepoTags')or[]:
   if tag in tags:result[tag]=dict(image_id=x['Id'],repo_digests=x.get('RepoDigests')or[],rootfs=x['RootFS'],created=x.get('Created'))
 assert set(result)==tags
 return result
def prepare(check_only=False):
 os.environ['PATH']=str(R/'formal-controller18-client-bin-r1')+':'+os.environ['PATH']
 source=B/'FROZEN_USER_SYNTHETIC32_SOURCE_R2.json';assert sha(source)==SOURCE_SHA;frozen=read(source);assert frozen['unique_variants']==32 and frozen['unique_seed_families']==14
 official_path=E/'manifests/OFFICIAL_89_TASK_IDENTITIES.json';official={x['image']:x for x in read(official_path)['tasks']}
 public={x['original_environment']['docker_image']for x in frozen['tasks']if x['original_environment'].get('docker_image','').startswith('alexgshaw/')}
 bases={}
 for item in frozen['tasks']:
  if item['task_id']in REBUILD:
   text=(Path(item['runtime_task_path'])/'environment/Dockerfile').read_text();base=re.findall(r'^FROM\s+(\S+)',text,re.M);assert len(base)==1;bases[item['task_id']]=base[0]
 endpoint='ssh://chenkeyi@127.0.0.1:18449';live=image_details(endpoint,public|set(bases.values()))
 for tag in public|set(bases.values()):
  assert tag in official,tag
  assert live[tag]['image_id']==official[tag]['image_id'],tag
 rows=[]
 for item in frozen['tasks']:
  task=item['task_id'];taskdir=Path(item['runtime_task_path']);context=Path(item['public_context']);declared=item['original_environment'].get('docker_image');original_env=taskdir/'environment'
  assert sha(taskdir/'task.toml')==item['runtime_task_toml_sha256'] and sha(taskdir/'instruction.md')==item['instruction_sha256']
  for entry in item['official_for_this_user_dataset_tests']:assert sha(taskdir/entry['path'])==entry['sha256']
  assert files(context)==files(original_env),task
  row=dict(task_id=task,runtime_task_path=str(taskdir),source_task_toml_sha256=item['runtime_task_toml_sha256'],recipe_sha256=sha(original_env/'Dockerfile'),public_context=str(context),public_context_files=files(context),declared_image=declared,force_build=False,force_build_by_stage=dict(prep=False,eval=False),original_task_tests_reward_resources_unmodified=True)
  if task in REBUILD:
   row.update(mode='ORIGINAL_RECIPE_REBUILD_NOT_BIT_IDENTICAL_SOURCE167_PREBUILT',force_build=True,force_build_by_stage=dict(prep=True,eval=False),private_image_tag='rsi-synthetic32-recipe:'+item['file_manifest_tree_sha256'][:24],source167_prebuilt_identity='UNVERIFIED_ACCESS_DENIED_AND_NO_ARCHIVE',base_image=bases[task],base_image_identity=live[bases[task]],required_independent_recheck=True,legacy_nop_acceptance='PROVISIONAL_NOT_SOURCE167_IMAGE_ACCEPTANCE')
   # Check every original COPY input exists. No fixture guessing or substitution.
   inputs=[]
   for line in (original_env/'Dockerfile').read_text().splitlines():
    if not line.strip().upper().startswith('COPY '):continue
    parts=shlex.split(line.strip());assert len(parts)==3 and not parts[1].startswith('--'),line
    p=context/parts[1];assert p.exists(),str(p);inputs.append(dict(source=parts[1],destination=parts[2],files=files(p)if p.is_dir()else dict(sha256=sha(p),bytes=p.stat().st_size)))
   row['verified_recipe_public_inputs']=inputs
   output=B/'public-deployment-r3'/task;newcontext=output/('context-'+item['file_manifest_tree_sha256'][:16]);row['public_context']=str(newcontext)
   image_assets=[]
   if task.startswith('custom-memory'):
    for name in ['main.cpp','user.h','user.cpp']:
     p=context/'program'/name;image_assets.append(dict(target='/app/'+name,sha256=sha(p),bytes=p.stat().st_size,source=str(p)))
    # Reviewed original public generator: definitions only; no output or host mutation.
    generator=context/'data/make_readings.py';module=runpy.run_path(str(generator));text=module['build'](rows=30000,stations=['ST-%05d'%i for i in range(1,101)],days=range(1,302),seed=20251031).encode()
    image_assets.append(dict(target='/app/data/readings.csv',sha256=hashlib.sha256(text).hexdigest(),bytes=len(text),source_original_public_generator_sha256=sha(generator)))
   if task.startswith('query-optimize'):
    p=context/'task-deps/slow-query.sql';image_assets.append(dict(target='/app/slow-query.sql',sha256=sha(p),bytes=p.stat().st_size,source=str(p)))
    digest=re.search(r'([0-9a-f]{64})\s+/app/oewn.sqlite',(original_env/'Dockerfile').read_text());assert digest;image_assets.append(dict(target='/app/oewn.sqlite',sha256=digest[1],bytes=None,source='Original recipe verifies public seed database unchanged'))
   row['image_public_files']=image_assets
   row['fixture_recipe_review']=dict(sufficient=True,reason='Original COPY inputs present; heap deterministic generator and program present; fix-git original setup asserts base commit/object identities and builds fixture; SQL original query and unchanged database SHA asserted by original Dockerfile')
   if not check_only:
    if newcontext.exists():assert files(newcontext)==files(context)
    else:output.mkdir(parents=True,exist_ok=True);shutil.copytree(context,newcontext)
   row['overlays']={}
   for stage in ['prep','eval']:
    overlay=read(Path(item['overlays'][stage]['path']))
    if stage=='prep':overlay['services']['main'].update(image=row['private_image_tag'],build=dict(context=str(newcontext),dockerfile='Dockerfile'))
    else:overlay=dict(networks=overlay['networks'],services=dict(main=dict(image=row['private_image_tag'])))
    path=output/(stage+'.compose.json')
    if not check_only:write_new(path,overlay)
    row['overlays'][stage]=dict(path=str(path),sha256=hashlib.sha256((json.dumps(overlay,indent=2)+'\n').encode()).hexdigest(),subnet=item['overlays'][stage]['subnet'])
  elif declared:
   assert declared in public;row.update(mode='DECLARED_PUBLISHED_PREBUILT',expected_image_identity=live[declared],build_allowed=False,local_image_required_before_prepare=True,required_independent_recheck=False);row['overlays']={}
   for stage in ['prep','eval']:
    overlay=dict(networks=read(Path(item['overlays'][stage]['path']))['networks']);path=B/'public-deployment-r3'/task/(stage+'.compose.json')
    assert 'services'not in overlay
    if not check_only:write_new(path,overlay)
    row['overlays'][stage]=dict(path=str(path),sha256=hashlib.sha256((json.dumps(overlay,indent=2)+'\n').encode()).hexdigest(),subnet=item['overlays'][stage]['subnet'])
  else:
   row.update(mode='ORIGINAL_DOCKERFILE_UNIQUE_CONTEXT',overlays=item['overlays'],required_independent_recheck=False)
  rows.append(row)
 value=dict(schema='synthetic32-explicit-image-deployment-r3',source_manifest_path=str(source),source_manifest_sha256=SOURCE_SHA,official89_identity_manifest_sha256=sha(official_path),expected_tasks=32,seed_families=14,engine_id='c6e16cdf-e878-4cc5-84c8-78a56c54b5c5',endpoint=endpoint,tasks=rows,published_prebuilt_tasks=sum(r['mode']=='DECLARED_PUBLISHED_PREBUILT'for r in rows),original_nonprebuilt_tasks=sum(r['mode']=='ORIGINAL_DOCKERFILE_UNIQUE_CONTEXT'for r in rows),explicit_original_recipe_rebuild_tasks=sorted(REBUILD),source167_original_image_equivalence_claimed=False,original_task_tests_reward_resources_unmodified=True,source_sha256=sha(Path(__file__)) if Path(__file__).is_file() else 'CHECK_ONLY_STDIN')
 assert len(rows)==32
 if not check_only:write_new(B/'SYNTHETIC32_DEPLOYMENT_R3.json',value)
 print(json.dumps(value,indent=2));return value
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--check-only',action='store_true');prepare(p.parse_args().check_only)
