"""Materialize byte-identical trusted Task/assets and a private SSD log root."""
from pathlib import Path
import hashlib,json,os,shutil,time
R=Path('/ssd/chenkeyi/qwen35-sft-772-20261101');S=R/'formal-controller18-source-r1'
LOGICAL=Path('/home/chenkeyi/.local/share/harbor-rsi/qwen35-new772-tb21-20261101');REAL=R/'formal-native-eval-r1'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 assert json.loads((R/'checks/FORMAL_CONTROLLER18_CPU_ENV_ACCEPTANCE_R1.json').read_text())['passed']
 assert not LOGICAL.exists()and not LOGICAL.is_symlink()and not REAL.exists()
 manifest=json.loads((S/'STAGING_MANIFEST.json').read_text());REAL.mkdir(mode=0o700)
 copied=[];reused=[]
 for x in manifest['files']:
  source=S/x['replica_path'];old=Path(x['original_path']);assert sha(source)==x['sha256']
  target=REAL/old.relative_to(LOGICAL)if old.is_relative_to(LOGICAL)else old
  if target.exists():assert target.is_file()and sha(target)==x['sha256'];reused.append(str(target))
  else:target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,target);copied.append(str(target))
  assert sha(target)==x['sha256']
 for folder in ['jobs','logs','diagnostics','staging','recovery']:(REAL/folder).mkdir(exist_ok=True)
 (REAL/'staging').chmod(0o700)
 LOGICAL.parent.mkdir(parents=True,exist_ok=True);LOGICAL.symlink_to(REAL,target_is_directory=True)
 assert LOGICAL.resolve()==REAL and(REAL/'jobs').stat().st_dev==R.stat().st_dev
 client=R/'formal-controller18-client-bin-r1';client.mkdir();p=client/'ssh'
 p.write_text('#!/bin/sh\nexec /usr/bin/ssh -F '+str(R/'control-ssh/formal-engine149-r1.conf')+' "$@"\n');p.chmod(0o700)
 value=dict(passed=True,at=time.time(),logical_root=str(LOGICAL),actual_root=str(REAL),
  hot_jobs_logs_staging_on_ssd=True,source_replica_not_shared_storage=True,
  files=len(manifest['files']),bytes=manifest['total_bytes'],copied=len(copied),reused_identical=len(reused),
  cold_task_and_bootstrap_paths_preserved_for_identity=True,all_original_file_sha_preserved=True,
  ssh_client_wrapper_sha256=sha(p),native_environment_byte_identity_proof='FORMAL_CONTROLLER18_CPU_ENV_ACCEPTANCE_R1.json',
  formal_or_model_trials_started=0,old149_files_or_running_trials_changed=False,
  source_sha256=sha(Path(__file__)))
 out=R/'checks/FORMAL_CONTROLLER18_PATHS_ACCEPTANCE_R1.json';assert not out.exists();out.write_text(json.dumps(value,indent=2)+'\n');print(json.dumps(value))
if __name__=='__main__':main()
