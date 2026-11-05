"""Stop this campaign's obsolete public-cache caller; preserve all archive evidence."""
from pathlib import Path
import json,os,signal
R=Path('/home/chenkeyi/.local/share/harbor-rsi/qwen35-new-cf500-tmax500-20261029');pid=911024
assert json.loads((R/'checks/cf-public-oci-native-import-proof.json').read_text())['passed']
assert json.loads((R/'checks/cf-environments-oci-r5/mathematics_20260509_111805_003.json').read_text())['status']=='IMAGE_IDENTITY_AND_BASIC_SETUP_PASSED'
a=(Path('/proc')/str(pid)/'cmdline').read_bytes().decode().strip('\0').split('\0');assert a[1:]==[str(R/'scripts/prepare_cf_cached_images.py')]
os.kill(pid,signal.SIGSTOP)
try:
 children=[]
 for p in Path('/proc').iterdir():
  if not p.name.isdigit():continue
  try:
   stat=(p/'stat').read_text().rsplit(')',1)[1].split()
   if int(stat[1])==pid:children.append((int(p.name),(p/'cmdline').read_bytes().decode().strip('\0').split('\0')))
  except (OSError,ValueError):pass
 if not all(a and a[0]=='ssh' and any('cache_public_cf_17.py' in v for v in a) for _,a in children):
  print(json.dumps(dict(status='DEFERRED_UNTIL_PUBLIC_DOWNLOAD_SAFE_POINT',children=[p for p,_ in children])));raise SystemExit
 for child,_ in children:
  try:os.kill(child,signal.SIGTERM)
  except ProcessLookupError:pass
 os.kill(pid,signal.SIGTERM)
 report=dict(status='OBSOLETE_PUBLIC_CACHE_CALLER_TERMINATED',pid=pid,child_pids=[p for p,_ in children],
  reason='Native OCI transport and original-resource preparation are live; old17Docker route is unresponsive',
  teacher_trials_cancelled=0,model_calls=0,archives_and_receipts_preserved=True,global_daemon_changes=False)
 (R/'checks/obsolete-cf-cache-route-termination.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))
finally:
 try:os.kill(pid,signal.SIGCONT)
 except ProcessLookupError:pass
