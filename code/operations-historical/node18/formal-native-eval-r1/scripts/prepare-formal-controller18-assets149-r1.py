"""Freeze exact existing CPU runner artifacts; no Job, model or Docker dispatch."""
from pathlib import Path
import hashlib,importlib.metadata as metadata,json,shutil,time,zipfile
R=Path('/home/chenkeyi/.local/share/harbor-rsi/qwen35-new772-tb21-20261101');B=R.parent
OUT=R/'controller18-prep-r1'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 assert not(R/'jobs/qwen35-new772-tb21-n3').exists()
 assert not OUT.exists(),'Preserve an existing replica export'
 OUT.mkdir();(OUT/'wheels').mkdir();(OUT/'replica').mkdir()
 all_packages={d.metadata['Name']:d.version for d in metadata.distributions()if d.metadata.get('Name')}
 (OUT/'constraints-eval149.txt').write_text(''.join(n+'=='+v+'\n'for n,v in sorted(all_packages.items(),key=lambda x:x[0].lower())))
 package_rows=[]
 for name in ['harbor','harbor-remote-docker','open-harness-ai']:
  dist=metadata.distribution(name);url=json.loads(dist.read_text('direct_url.json'))['url'];assert url.startswith('file://')
  path=Path(url.removeprefix('file://'));target=OUT/'wheels'/path.name;shutil.copy2(path,target)
  root=Path(dist.locate_file(''));diff=[];count=0
  with zipfile.ZipFile(path)as z:
   for item in z.namelist():
    if item.endswith('.py')and '.dist-info/'not in item:
     count+=1;local=root/item
     if not local.exists()or hashlib.sha256(z.read(item)).hexdigest()!=sha(local):diff.append(item)
  package_rows.append(dict(name=name,version=dist.version,original_wheel=str(path),file='wheels/'+path.name,sha256=sha(target),python_files=count,installed_differences=diff))
  assert not diff,(name,diff)
 copied=[]
 def copy(path):
  assert path.is_file(),str(path)
  relative=Path(str(path).lstrip('/'));target=OUT/'replica'/relative;target.parent.mkdir(parents=True,exist_ok=True)
  if target.exists():assert sha(path)==sha(target);return
  shutil.copy2(path,target);copied.append(dict(original_path=str(path),replica_path='replica/'+str(relative),sha256=sha(target),bytes=target.stat().st_size))
 for folder in ['configs','manifests','scripts','wheels']:
  for path in sorted((R/folder).rglob('*')):
   if path.is_file()and '__pycache__'not in path.parts:copy(path)
 checks=['FORMAL801_WHEEL_ONLY_DEPLOYMENT_R2.json','OFFICIAL_89_FULL_SOURCE_REVALIDATION_R1.json','CONTEXT_RECOVERY_FULL_WHEEL_E2E_ACCEPTANCE_R1.json','NEW11_INSTALL_PREFLIGHT_ALL_TERMINAL_R1.json','E3_NATIVE_CONTROLLER_OOM_SNAPSHOT_R1.json','NATIVE_801_TRIAL_CONFIG_PREFLIGHT_R9.json','NATIVE_EVAL149_DEPLOYMENT_RELEASE_R10.json']
 for name in checks:copy(R/'checks'/name)
 plan=json.loads((R/'manifests/FORMAL_801_TRIAL_PLAN.json').read_text())
 assert len(plan['trials'])==801
 task_paths=sorted({x['task_path']for x in plan['trials']});assert len(task_paths)==89
 for raw in task_paths:
  task=Path(raw);assert str(task).startswith(str(B)+'/near-r3-20261015/')
  for path in sorted(task.rglob('*')):
   assert not path.is_symlink(),'Explicitly inspect any cross-machine Task symlink'
   if path.is_file():copy(path)
 config=json.loads((R/'configs/formal-native-job.json').read_text())
 for agent in config['agents']:
  for key in ['bootstrap_uv_path','bootstrap_fd_path']:copy(Path(agent['kwargs'][key]))
 compose=json.loads((R/'configs/agent-deps-r1.compose.json').read_text())
 for service in compose['services'].values():
  for volume in service.get('volumes',[]):
   if isinstance(volume,dict)and volume.get('type')=='bind':copy(Path(volume['source']))
 value=dict(kind='FORMAL_CONTROLLER18_CPU_RUNNER_REPLICA_EXPORT',at=time.time(),source_node='149',target_node='18',packages=package_rows,files=copied,
  task_count=89,formal_trial_count=801,total_bytes=sum(x['bytes']for x in copied),
  root_packages_original_versions_preserved=True,pip_constraints_sha256=sha(OUT/'constraints-eval149.txt'),
  source_sha256=sha(Path(__file__)),native_trials_or_model_calls=0,original_files_modified=False,
  existing_native_e3_and_training_untouched=True,not_yet_deployment_accepted=True)
 (OUT/'STAGING_MANIFEST.json').write_text(json.dumps(value,indent=2)+'\n')
 print(json.dumps(dict(passed=True,files=len(copied),bytes=value['total_bytes'],manifest_sha256=sha(OUT/'STAGING_MANIFEST.json'),packages=package_rows)))
if __name__=='__main__':main()
