"""Freeze user dataset bytes and equivalent unique public Docker build contexts."""
from pathlib import Path
import hashlib,ipaddress,json,os,shlex,shutil,subprocess,time,re,difflib
import tomllib
R=Path('/ssd/chenkeyi/qwen35-sft-772-20261101');B=R/'synthetic32';S=B/'source';E=R/'formal-native-eval-r1';C=Path('/data/chenkeyi/qwen35-sft-772-20261101/control')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
manifest=json.loads((B/'FILE_MANIFEST_SOURCE167_R1.json').read_text());assert len(manifest['files'])==480
for row in manifest['files']:
 p=S/row['path'];assert not p.is_symlink()and p.stat().st_size==row['bytes']and sha(p)==row['sha256']
assert sha(S/'tasks.json')=='73b2d2087e7957e6d4cee958bc1e7deff028652e4d3d2a2d231446bd58bdd07d'
original=json.loads((S/'tasks.json').read_text());assert len(original)==len({x['id']for x in original})==32
code="import subprocess,json; n=subprocess.check_output(['docker','network','ls','-q'],text=True).split(); a=json.loads(subprocess.check_output(['docker','network','inspect',*n],text=True)); print(json.dumps(dict(engine=subprocess.check_output(['docker','info','--format','{{.ID}}'],text=True).strip(),subnets=[c['Subnet']for v in a for c in v.get('IPAM',{}).get('Config')or[]if c.get('Subnet')],routes=json.loads(subprocess.check_output(['ip','-j','route'],text=True)))))"
network=json.loads(subprocess.check_output(['/usr/bin/ssh','-F',str(R/'control-ssh/formal-engine149-r1.conf'),'127.0.0.1','python3 -c '+shlex.quote(code)],text=True,timeout=20));assert network['engine']=='c6e16cdf-e878-4cc5-84c8-78a56c54b5c5'
pool=ipaddress.ip_network('10.248.64.0/22');assert not any(pool.overlaps(ipaddress.ip_network(s,strict=False))for s in network['subnets']+[r['dst']for r in network['routes']if r.get('dst')!='default'])
final=B/'source';runtime=B/'runtime-tasks-r1';assert not runtime.exists();runtime.mkdir();adapters=[];rows=[];subnets=list(pool.subnets(new_prefix=28))
from harbor.models.task.task import Task
for i,item in enumerate(original):
 original_task=final/'tasks'/item['id'];p=runtime/item['id'];shutil.copytree(original_task,p,copy_function=shutil.copy2)
 before=tomllib.loads((p/'task.toml').read_text());name=before.get('task',{}).get('name');change=None
 if name and '/'not in name:
  old=(p/'task.toml').read_text();match=re.search(r'(?ms)^\[task\]\s*\n.*?(?=^\[|\Z)',old);assert match
  block=match.group();new_name='taskgent/'+name;new_block,count=re.subn(r'(?m)^name\s*=.*$',lambda _: 'name = '+json.dumps(new_name),block,count=1);assert count==1
  new=old[:match.start()]+new_block+old[match.end():];(p/'task.toml').write_text(new)
  after=tomllib.loads(new);after['task']['name']=name;assert after==before
  change=dict(task_id=item['id'],field='task.name',original=name,runtime=new_name,source_task_toml_sha256=sha(original_task/'task.toml'),runtime_original_task_toml_sha256=sha(original_task/'task.toml'),runtime_task_toml_sha256=sha(p/'task.toml'),metadata_adapter=change,patch=''.join(difflib.unified_diff(old.splitlines(keepends=True),new.splitlines(keepends=True),fromfile='original/task.toml',tofile='runtime/task.toml')));adapters.append(change)
 assert sha(p/'instruction.md')==sha(original_task/'instruction.md')
 for f in (original_task/'tests').rglob('*'):
  if f.is_file():assert sha(f)==sha(p/'tests'/f.relative_to(original_task/'tests'))
 task=Task(p);assert not task.has_steps and task.config.environment.gpus==0
 env=p/'environment';assert(env/'Dockerfile').is_file();data=tomllib.loads((p/'task.toml').read_text());tree=[x for x in manifest['files']if x['path'].startswith('tasks/'+item['id']+'/')];tree_sha=hashlib.sha256(json.dumps(tree,sort_keys=True,separators=(',',':')).encode()).hexdigest()
 public=B/'public-deployment-r2'/(item['id']+'-'+tree_sha[:12]);public.mkdir(parents=True);context=public/('context-'+tree_sha[:16]);shutil.copytree(env,context,copy_function=shutil.copy2)
 for f in env.rglob('*'):
  if f.is_file():assert sha(f)==sha(context/f.relative_to(env))
 overlays={}
 for stage,index in [('prep',i),('eval',32+i)]:
  overlay=public/(stage+'.compose.json');overlay.write_text(json.dumps(dict(services=dict(main=dict(build=dict(context=str(context),dockerfile='Dockerfile'))),networks=dict(default=dict(ipam=dict(config=[dict(subnet=str(subnets[index]))])))),indent=2)+'\n');overlays[stage]=dict(path=str(overlay),sha256=sha(overlay),subnet=str(subnets[index]))
 rows.append(dict(task_id=item['id'],source_original_path=item['path'],runtime_task_path=str(p),publisher_declared_sha256=item['sha256'],publisher_digest_algorithm_not_assumed=True,file_manifest_tree_sha256=tree_sha,original_task_toml_sha256=sha(original_task/'task.toml'),runtime_task_toml_sha256=sha(p/'task.toml'),metadata_adapter=change,instruction_sha256=sha(p/'instruction.md'),dockerfile_sha256=sha(env/'Dockerfile'),official_for_this_user_dataset_tests=[dict(path=str(f.relative_to(p)),sha256=sha(f))for f in sorted((p/'tests').rglob('*'))if f.is_file()],original_environment=data['environment'],original_agent=data.get('agent',{}),original_verifier=data.get('verifier',{}),seed=item['seed'],public_context=str(context),overlays=overlays))
freeze=dict(at=time.time(),dataset='USER_SYNTHETIC32_SEED15_OH_LOOP01_ACCEPTED',not_official_tb21=True,source_node='aibox-167',source_path=manifest['source_path'],source_manifest_sha256=sha(B/'FILE_MANIFEST_SOURCE167_R1.json'),original_tasks_json_sha256=sha(final/'tasks.json'),files=480,bytes=sum(x['bytes']for x in manifest['files']),tasks=rows,unique_variants=32,unique_seed_families=len({x['seed']['sha256']for x in original}),model='NEW-M1 Epoch3',model_manifest_sha256='2e02fec581cbb3c802cd1e0e80ac2c9568bead3a9002338f4d661ea6ac94053d',model_repetitions=1,no_model_training=True,separate_from_common30_and_full267=True,raw_source_files_unchanged=True,runtime_only_task_name_normalizations=adapters,all_instructions_tests_dockerfiles_rewards_and_resources_unchanged=True,network_preallocation=network,source_sha256=sha(Path(__file__)))
(B/'FROZEN_USER_SYNTHETIC32_SOURCE_R2.json').write_text(json.dumps(freeze,indent=2)+'\n');(C/'USER_SYNTHETIC32_SOURCE_DISCOVERY_R2.json').write_text(json.dumps(dict(at=time.time(),status='SOURCE_BYTES_FROZEN_ENVIRONMENT_CHECKS_PENDING',source_node='aibox-167',actual_variants=32,seed_families=freeze['unique_seed_families'],manifest=str(B/'FROZEN_USER_SYNTHETIC32_SOURCE_R2.json'),sha256=sha(B/'FROZEN_USER_SYNTHETIC32_SOURCE_R2.json')),indent=2)+'\n');print(json.dumps(dict(frozen=True,variants=32,seed_families=freeze['unique_seed_families'],files=480,bytes=freeze['bytes'],source_manifest_sha256=sha(B/'FROZEN_USER_SYNTHETIC32_SOURCE_R2.json'))))
