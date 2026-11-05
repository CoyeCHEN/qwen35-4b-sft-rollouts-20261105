"""Finish the current CPU scan, move only this audit cache, then exec one writer."""
import datetime,fcntl,hashlib,json,os,shlex,signal,subprocess,time
from pathlib import Path
R=Path('/home/chenkeyi/.local/share/harbor-rsi/qwen35-new-cf500-tmax500-20261029')
PID=309628;PROC=Path('/proc')/str(PID)
OLD=R/'scripts/audit_stream_data_worker149_r4.py';NEW=R/'scripts/audit_stream_data_worker149_r5.py'
PY='/home/chenkeyi/.local/share/harbor-rsi/qwen35-m1-m2-tb21-20261026/venv/bin/python'
ALLOWED={str(R/'scripts'/n) for n in ['audit_collection_results.py','audit_native_canary_protocol.py','export_native_canary_calls.py']}
REMOTE="""import datetime,hashlib,json,os,shutil,stat
from pathlib import Path
r=Path('/home/chenkeyi/workspace/RSI/runtime-evidence/qwen35-new-cf500-tmax500-20261029')
s=Path('/ssd/chenkeyi/qwen35-new-cf500-tmax500-20261029')
old=r/'validation/stream-r3';dest=s/'student-target-audit-cache-r5';backup=old.with_name('stream-r3-system-before-r5')
for p in Path('/proc').iterdir():
 if not p.name.isdigit():continue
 try:
  args=(p/'cmdline').read_bytes().split(bytes([0]))
  if str(r/'scripts/audit_stream_data_17.py').encode() in args:raise RuntimeError('An actual target audit remains active; no move')
 except OSError:pass
assert old.is_dir() and not old.is_symlink() and not dest.exists() and not backup.exists()
def manifest(root):
 records=[]
 for p in sorted(root.rglob('*')):
  mode=stat.S_IMODE(p.lstat().st_mode);rel=str(p.relative_to(root))
  if p.is_symlink():
   link=os.readlink(p)
   if not Path(link).is_absolute() and not p.resolve().is_relative_to(root):raise ValueError('Escaping relative audit symlink; inspect before moving')
   records.append(dict(path=rel,link=link,mode=mode))
  elif p.is_file():
   with p.open('rb') as f:digest=hashlib.file_digest(f,'sha256').hexdigest()
   records.append(dict(path=rel,sha256=digest,bytes=p.stat().st_size,mode=mode))
 return records
before=manifest(old);shutil.copytree(old,dest,symlinks=True);after=manifest(dest);assert before==after
old.rename(backup);old.symlink_to(dest,target_is_directory=True)
assert manifest(old)==before
proof=dict(checked_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),source=str(old),ssd_destination=str(dest),preserved_system_backup=str(backup),files=len(before),regular_bytes=sum(x.get('bytes',0) for x in before),all_file_bytes_modes_and_links_identical=True,model_calls=0,teacher_or_verifier_actions=0)
with (s/'student-target-audit-storage-migration-r5.json').open('x') as f:json.dump(dict(proof,files_manifest=before),f,indent=2)
print(json.dumps(proof))
"""
def now():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def state(stage,**fields):
 p=R/'checks/data-audit-idle-handoff-r5.json';t=p.with_suffix('.tmp')
 t.write_text(json.dumps(dict(status=stage,checked_at=now(),pid=os.getpid(),old_pid=PID,teacher_actions=0,**fields),indent=2));t.replace(p)
def child_ids():
 ids=set()
 for p in (PROC/'task').glob('*/children'):
  try:ids.update(int(x) for x in p.read_text().split())
  except FileNotFoundError:pass
 return sorted(ids)
def phase(pid):
 p=Path('/proc')/str(pid)
 if not p.exists():return 'GONE'
 return next(x.split()[1] for x in (p/'status').read_text().splitlines() if x.startswith('State:'))
def main():
 lock=(R/'checks/data-audit-idle-handoff-r5.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 assert json.loads((R/'checks/data-audit-queue-r5-offline-acceptance.json').read_text())['passed']
 stopped=False
 try:
  while True:
   assert str(OLD).encode() in (PROC/'cmdline').read_bytes().split(b'\0')
   observed=json.loads((R/'checks/stream-r4-data-audit-worker.json').read_text())
   children=child_ids()
   valid=observed['pid']==PID and not observed['active_trial_ids'] and observed['stage'] in [Path(x).name for x in ALLOWED] and children
   rows=[]
   for pid in children:
    args=(Path('/proc')/str(pid)/'cmdline').read_bytes().decode().split('\0')
    scripts=[x for x in args if x in ALLOWED];valid=valid and len(scripts)==1
    rows.append(dict(pid=pid,script=scripts[0] if scripts else None))
   if not valid:state('WAITING_FOR_GLOBAL_SCAN_WITH_NO_TARGET_FUTURES',observed=observed,children=rows);time.sleep(5);continue
   os.kill(PID,signal.SIGSTOP);stopped=True
   for _ in range(20):
    if phase(PID)=='T':break
    time.sleep(.05)
   if phase(PID)!='T':raise RuntimeError('Actual SIGSTOP predicate did not become T; no handoff')
   latest=json.loads((R/'checks/stream-r4-data-audit-worker.json').read_text())
   assert not latest['active_trial_ids'] and set(child_ids())<=set(children)
   before=dict(checked_at=now(),old_pid=PID,old_source=str(OLD),old_source_sha256=hashlib.sha256(OLD.read_bytes()).hexdigest(),new_source_sha256=hashlib.sha256(NEW.read_bytes()).hexdigest(),actual_parent_state=phase(PID),pending_target_futures=latest['active_trial_ids'],native_cpu_children=rows,old_state=latest,model_calls=0,teacher_or_verifier_signals=0)
   with (R/'checks/data-audit-r5-handoff-start.json').open('x') as f:json.dump(before,f,indent=2)
   while any(phase(pid) not in ['GONE','Z'] for pid in children):
    state('WAITING_ONLY_FOR_EXISTING_GLOBAL_CPU_SCAN_TO_COMPLETE',actual_parent_state=phase(PID),children=[dict(pid=p,state=phase(p)) for p in children]);time.sleep(5)
   os.kill(PID,signal.SIGTERM);os.kill(PID,signal.SIGCONT);stopped=False
   for _ in range(100):
    if not PROC.exists() or phase(PID)=='Z':break
    time.sleep(.1)
   assert not PROC.exists() or phase(PID)=='Z'
   test=(R/'derived/stream-r3-audit-worker.lock').open('a');fcntl.flock(test,fcntl.LOCK_EX|fcntl.LOCK_NB);fcntl.flock(test,fcntl.LOCK_UN);test.close()
   # No derived-data target processes remain while preserving the old path.
   ssh=['ssh','-S','/home/chenkeyi/.ssh/cf17-20261028.sock','-oBatchMode=yes','-oProxyCommand=false','chenkeyi@180.163.192.17']
   py17='/home/chenkeyi/workspace/RSI/runtime-evidence/qwen35-length-lf-audit-20261023/.venv/bin/python'
   reply=subprocess.run([*ssh,shlex.join([py17,'-c',REMOTE])],capture_output=True,text=True,timeout=600,check=True)
   storage=json.loads(reply.stdout)
   with (R/'checks/student-target-audit-storage-migration-r5.json').open('x') as f:json.dump(storage,f,indent=2)
   state('OLD_CPU_SCAN_FINISHED_AND_SINGLE_WRITER_LOCK_RELEASED_EXEC_R5',new_writer_pid=os.getpid(),storage=storage)
   os.execv(PY,[PY,str(NEW)])
 finally:
  if stopped and PROC.exists():os.kill(PID,signal.SIGCONT)
if __name__=='__main__':
 for key in ['DEEPSEEK_API_KEY','GH_TOKEN','OPENAI_API_KEY']:os.environ.pop(key,None)
 os.environ['SSH_AUTH_SOCK']='/home/chenkeyi/.local/share/harbor-rsi/near-r3-20261015/auth.sock'
 main()
