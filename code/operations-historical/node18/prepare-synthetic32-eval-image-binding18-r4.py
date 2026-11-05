"""Only derived eval metadata: bind 17 accepted images without rebuilding them."""
import argparse,difflib,hashlib,json,os,re,shutil,subprocess,tomllib
from pathlib import Path
R=Path('/ssd/chenkeyi/qwen35-sft-772-20261101');B=R/'synthetic32'
def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def files(root):return {p.relative_to(root).as_posix():dict(sha256=sha(p),bytes=p.stat().st_size,mode=p.stat().st_mode&0o777)for p in sorted(root.rglob('*'))if p.is_file()}
def directories(root):return {p.relative_to(root).as_posix():p.stat().st_mode&0o777 for p in [root,*sorted(root.rglob('*'))]if p.is_dir()}
def write_new(path,value):
 path.parent.mkdir(parents=True,exist_ok=True);raw=json.dumps(value,indent=2)+'\n'
 if path.exists():assert path.read_text()==raw,str(path)
 else:
  temp=path.with_name(path.name+'.tmp');temp.write_text(raw);temp.replace(path)
def prepare(check_only=False):
 from harbor.environments.definition import should_use_prebuilt_docker_image,should_upload_environment_dir
 from harbor.models.task.config import TaskConfig
 os.environ['PATH']=str(R/'formal-controller18-client-bin-r1')+':'+os.environ['PATH']
 deployment_path=B/'SYNTHETIC32_DEPLOYMENT_R3.json';deployment=read(deployment_path);environment_path=B/'ENV_PREFLIGHT_32_MANIFEST.json';environment=read(environment_path)
 assert environment['frozen']and environment['passed']==32 and all(x['status']=='PASS'for x in environment['tasks'])
 assert environment['deployment_manifest_sha256']==sha(deployment_path)
 originals={x['task_id']:x for x in read(B/'FROZEN_USER_SYNTHETIC32_SOURCE_R2.json')['tasks']};accepted={x['task_id']:x for x in environment['tasks']};selected=[x for x in deployment['tasks']if x['mode']=='ORIGINAL_DOCKERFILE_UNIQUE_CONTEXT'];assert len(selected)==17
 expected={accepted[x['task_id']]['attempts'][-1]['actual_runtime']['actual_image_id']for x in selected}
 p=subprocess.run(['docker','--host',deployment['endpoint'],'image','inspect',*sorted(expected)],capture_output=True,text=True,timeout=25);assert p.returncode==0,p.stderr[-1000:];live={x['Id']:x for x in json.loads(p.stdout)};assert set(live)==expected
 rows=[]
 for item in selected:
  task=item['task_id'];source=Path(item['runtime_task_path']);target=B/'eval-runtime-tasks-r4'/task;runtime=accepted[task]['attempts'][-1]['actual_runtime'];image_id=runtime['actual_image_id'];original=(source/'task.toml').read_bytes();before=tomllib.loads(original.decode());assert 'docker_image'not in before['environment']
  match=re.search(rb'^\[environment\][ \t]*(\r?\n)',original,re.M);assert match,task;newline=match[1];line=b'docker_image = '+json.dumps(image_id).encode()+newline;derived=original[:match.end()]+line+original[match.end():]
  after=tomllib.loads(derived.decode());assert after['environment'].pop('docker_image')==image_id and after==before
  old_model=TaskConfig.model_validate_toml(original.decode()).model_dump(mode='json');new_model=TaskConfig.model_validate_toml(derived.decode()).model_dump(mode='json');assert new_model['environment'].pop('docker_image')==image_id;assert old_model['environment'].pop('docker_image')is None;assert old_model==new_model
  assert should_use_prebuilt_docker_image(source/'environment',docker_image=image_id,force_build=False)
  assert not should_upload_environment_dir(source/'environment',docker_image=image_id),'Never expose build recipe/assets by enabling prebuilt metadata'
  original_files=files(source);assert not any(p.is_symlink()for p in source.rglob('*'));derived_sha=hashlib.sha256(derived).hexdigest();overlay=dict(networks=read(Path(item['overlays']['eval']['path']))['networks']);overlay_path=B/'eval-image-deployment-r4'/task/'ipam.compose.json'
  if not check_only:
   if not target.exists():target.parent.mkdir(parents=True,exist_ok=True);shutil.copytree(source,target);(target/'task.toml').write_bytes(derived)
   actual=files(target);assert actual.keys()==original_files.keys();assert actual['task.toml']['sha256']==derived_sha
   for name,identity in original_files.items():
    if name!='task.toml':assert actual[name]==identity,(task,name)
   assert actual['task.toml']['mode']==original_files['task.toml']['mode'];assert directories(source)==directories(target)
   write_new(overlay_path,overlay)
  proof=Path(accepted[task]['attempts'][-1]['runtime_proof_path']);assert sha(proof)==accepted[task]['attempts'][-1]['runtime_proof_sha256']
  rows.append(dict(task_id=task,source_task_path=str(source),eval_task_path=str(target),publisher_task_toml_sha256=originals[task]['original_task_toml_sha256'],source_runtime_task_toml_sha256=sha(source/'task.toml'),derived_eval_task_toml_sha256=derived_sha,exact_diff=''.join(difflib.unified_diff(original.decode().splitlines(keepends=True),derived.decode().splitlines(keepends=True),fromfile=str(source/'task.toml'),tofile=str(target/'task.toml'))),only_changed_parsed_field='environment.docker_image',accepted_image_id=image_id,accepted_image_repo_digests=live[image_id].get('RepoDigests')or[],accepted_image_rootfs=live[image_id]['RootFS'],accepted_image_labels=live[image_id]['Config'].get('Labels')or{},nop_runtime_proof_path=str(proof),nop_runtime_proof_sha256=sha(proof),nop_result_sha256=accepted[task]['attempts'][-1]['result_sha256'],source_files=original_files,source_directory_modes=directories(source),overlay=dict(path=str(overlay_path),sha256=hashlib.sha256((json.dumps(overlay,indent=2)+'\n').encode()).hexdigest()),native_prebuilt_without_build=True,native_environment_upload_disabled_by_original_dockerfile=True,all_other_parsed_fields_and_all_other_file_bytes_modes_equal=True))
 value=dict(schema='synthetic32-eval-image-metadata-binding-r4',tasks=rows,expected_derived_tasks=17,expected_total_eval_tasks=32,environment_manifest_path=str(environment_path),environment_manifest_sha256=sha(environment_path),deployment_manifest_sha256=sha(deployment_path),original_task_files_untouched=True,original_reward_verifier_and_resources_unchanged=True,no_new_provider_or_scheduler=True,no_docker_builds=True,source_sha256=sha(Path(__file__))if Path(__file__).is_file()else'CHECK_ONLY_STDIN')
 if not check_only:write_new(B/'EVAL_TASK_IMAGE_BINDING_R4.json',value)
 print(json.dumps(value,indent=2));return value
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--check-only',action='store_true');prepare(p.parse_args().check_only)
