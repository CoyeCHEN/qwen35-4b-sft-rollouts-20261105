"""Stop only this campaign's obsolete environment-only worker at a safe point."""
import json,os,signal,time
from pathlib import Path
R=Path('/home/chenkeyi/.local/share/harbor-rsi/qwen35-new-cf500-tmax500-20261029')
pid=893753
assert json.loads((R/'checks/CANARY_GATE.json').read_text())['passed']
assert len((R/'indexes/TMAX_SUCCESS_INDEX.jsonl').read_text().splitlines())==8
assert (Path('/proc/3447295/cmdline').read_bytes().split(b'\0')[1].decode()==str(R/'scripts/prepare_original_tmax_pool.py'))
args=(Path('/proc')/str(pid)/'cmdline').read_bytes().decode().strip('\0').split('\0')
assert args[1:]==[str(R/'scripts/prepare_tmax_images_v2.py')]
os.kill(pid,signal.SIGSTOP)
try:
 children=[]
 for p in Path('/proc').iterdir():
  if not p.name.isdigit():continue
  try:
   stat=(p/'stat').read_text().rsplit(')',1)[1].split()
   if int(stat[1])==pid:
    child_args=(p/'cmdline').read_bytes().decode().strip('\0').split('\0');children.append((int(p.name),child_args))
  except (OSError,ValueError):pass
 safe=all(a and a[0]=='docker' and (a[1:2]==['build'] and any(x.startswith(str(R/'build-contexts')+'/') for x in a) or a[1:3]==['image','inspect']) for _,a in children)
 if not safe:
  print(json.dumps(dict(status='DEFERRED_UNTIL_BUILD_SAFE_POINT',children=[x for x,_ in children])));raise SystemExit
 for child,_ in children:
  try:os.kill(child,signal.SIGTERM)
  except ProcessLookupError:pass
 os.kill(pid,signal.SIGTERM)
 report=dict(status='OBSOLETE_ENVIRONMENT_ONLY_PREBUILDER_TERMINATED',pid=pid,child_pids=[x for x,_ in children],
  reason='Correct original-runtime preparation is live and validated; obsolete simultaneous preflights collided by container name and duplicated native builds',
  canonical_preparation_pid=3447295,teacher_trials_cancelled=0,model_calls=0,official_files_changed=False,
  global_docker_cleanup=False,all_preparation_receipts_preserved=True)
 (R/'checks/obsolete-tmax-prebuilder-termination.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))
finally:
 try:os.kill(pid,signal.SIGCONT)
 except ProcessLookupError:pass
