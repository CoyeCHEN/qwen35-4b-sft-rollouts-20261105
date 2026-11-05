"""Drain finite zero-model preparation with an owned build-directory fence.

tmux resumes a pane leader stopped by SIGSTOP. Keep the shared tmux server and
all existing work untouched; deny only creation of a new cold-build directory.
Existing build directories, native Trials, results and logs remain writable.
"""
import datetime
import fcntl
import json
import os
from pathlib import Path
import time

import prepare_unstarted_direct17_r17 as target

n=target.n
R=n.R
PIDS={'r13':35765,'r14':1182007}
OUT=R/'checks/direct17-build-preparation-handoff-r17.json'
PROGRESS=R/'checks/direct17-build-preparation-handoff-r17-progress.json'


def main():
    lock=(R/'checks/direct17-build-preparation-handoff-r17.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    if OUT.exists():raise FileExistsError('Observe completed native preparation handoff')
    plan_file=R/'manifests/TMAX_UNSTARTED_DIRECT_SSD17_R13.json';plan=json.loads(plan_file.read_text())
    old={}
    for version,pid in PIDS.items():
        p=Path('/proc')/str(pid);source=R/('scripts/prepare_unstarted_direct17_'+version+'.py')
        if str(source).encode() not in (p/'cmdline').read_bytes().split(b'\0'):raise ValueError('Original finite preparer identity changed')
        if n.sha(source)!=json.loads((R/('stream/direct17-native-source-'+version+'/PLAN.json')).read_text())['source_sha256']:raise ValueError('Frozen finite source changed')
        old[version]=dict(pid=pid,start_ticks=(p/'stat').read_text().rsplit(')',1)[1].split()[19],source=str(source),source_sha256=n.sha(source))
    acceptance=R/'checks/private17-buildkit-r16-acceptance.json';accepted=json.loads(acceptance.read_text())
    if not accepted['passed'] or accepted['builder_engine_id']!=n.NODE['engine_id']:raise ValueError('Private native builder acceptance differs')
    code=r'''
from pathlib import Path
import datetime,hashlib,json,os,stat,sys
r=Path(sys.argv[1]);ssd=Path(sys.argv[2]);tasks=json.loads(sys.argv[3]);root=ssd/'buildkit-rootless-r2/archives'
out=r/'checks/private17-cold-build-directory-fence-r20.json'
if out.exists():raise FileExistsError('Cold build fence already exists; inspect it')
active=[];builder=str(r/'scripts/build_tmax_native_oci_ssd17_r3.py').encode()
for p in Path('/proc').iterdir():
 if not p.name.isdigit():continue
 try:args=(p/'cmdline').read_bytes().split(b'\0')
 except OSError:continue
 if builder not in args:continue
 ident=args[args.index(builder)+1].decode();dest=root/ident/'client-proxy-r3'
 if not dest.is_dir():raise ValueError('An existing build has not created its writable directory')
 active.append(dict(pid=int(p.name),task_id=ident,directory=str(dest),argv_sha256=hashlib.sha256((p/'cmdline').read_bytes()).hexdigest()))
mode=stat.S_IMODE(root.stat().st_mode)
if not mode&stat.S_IWUSR:raise ValueError('Unexpected prior build admission fence')
deferred=[ident for ident in tasks if not (root/ident).exists()]
os.chmod(root,mode&~0o222)
probe=root/'.native-admission-fence-probe-r20'
try:
 probe.mkdir()
except PermissionError:denied=True
else:
 probe.rmdir();os.chmod(root,mode);raise ValueError('Owned build admission fence did not deny a new directory')
value=dict(status='ONLY_NEW_COLD_BUILD_DIRECTORIES_FENCED_EXISTING_NATIVE_WORK_WRITABLE',checked_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),directory=str(root),original_mode=mode,fenced_mode=stat.S_IMODE(root.stat().st_mode),active_native_builds_preserved=active,deferred_unbuilt_task_ids=deferred,new_directory_creation_denied=denied,teacher_or_verifier_signals=0,official_task_or_tests_modified=False,reason='tmux server_child_stopped resumes SIGSTOP pane leaders; source-build admission uses owned directories instead',upstream='https://github.com/tmux/tmux/blob/master/server.c')
with out.open('x') as f:json.dump(value,f,indent=2)
print(json.dumps(value))
'''
    fence=target.remote(code,target.E17,n.NODE['ssd_root'],json.dumps([x['task_id'] for x in plan['tasks']]))
    fence_file=R/'checks/private17-cold-build-directory-fence-r20.json';n.freeze(fence_file,fence)
    began=time.monotonic()
    while True:
        states={};alive=[]
        for version,pid in PIDS.items():
            p=Path('/proc')/str(pid)
            if p.exists():
                if (p/'stat').read_text().rsplit(')',1)[1].split()[19]!=old[version]['start_ticks']:raise ValueError('Finite preparer PID reused')
                alive.append(pid)
            states[version]=json.loads((R/('stream/direct17-native-source-'+version+'/state.json')).read_text())
        progress=dict(stage='WAITING_FOR_OWNED_FINITE_PREPARERS_TO_DRAIN_NATURALLY',checked_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),pid=os.getpid(),alive_old_preparer_pids=alive,old_preparer_states=states,teacher_or_verifier_signals=0,build_directory_fence=str(fence_file),build_directory_fence_sha256=n.sha(fence_file))
        temp=PROGRESS.with_suffix('.tmp');temp.write_text(json.dumps(progress,indent=2));temp.replace(PROGRESS)
        if not alive:break
        if time.monotonic()-began>7200:raise TimeoutError('Existing native work preserved; fence retained and no replacement started')
        time.sleep(2)
    for version in PIDS:
        scope=R/('stream/direct17-native-source-'+version)
        if not (scope/'TERMINAL.json').exists():raise ValueError('Finite preparer exited without terminal evidence')
        results=[]
        for p in (scope/'trials').glob('*'):
            result=p/'result.json'
            if result.exists():
                value=json.loads(result.read_text());cfg=value['config']
                if cfg['agent']['name']!='nop' and not cfg['install_only']:raise ValueError('Unexpected actual-model Trial in environment scope')
                results.append(dict(path=str(result),sha256=n.sha(result)))
            elif any(x.is_file() for x in p.rglob('*')):raise ValueError('Native precheck has no terminal Result')
        old[version].update(native_results=results,terminal=str(scope/'TERMINAL.json'),terminal_sha256=n.sha(scope/'TERMINAL.json'))
    restore=r'''
from pathlib import Path
import json,os,stat,sys
f=json.loads(sys.argv[1]);root=Path(f['directory'])
if stat.S_IMODE(root.stat().st_mode)!=f['fenced_mode']:raise ValueError('Owned build admission mode changed')
for row in f['active_native_builds_preserved']:
 result=Path(row['directory'])/'build.json'
 if not result.exists():raise ValueError('Preserved native build has no terminal receipt')
os.chmod(root,f['original_mode'])
print(json.dumps(dict(restored_mode=stat.S_IMODE(root.stat().st_mode),all_old_native_builds_have_terminal_receipts=True)))
'''
    restored=target.remote(restore,json.dumps(fence))
    value=dict(status='OLD_PREPARERS_NATIVE_WORK_FINISHED_NEW_PRIVATE_BUILDER_AUTHORIZED',checked_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        retired_preparer_pids=list(PIDS.values()),old_preparers=old,old_processes_finished_naturally=True,
        source_plan=str(plan_file),source_plan_sha256=n.sha(plan_file),builder_acceptance=str(acceptance),builder_acceptance_sha256=n.sha(acceptance),
        build_admission_fence=str(fence_file),build_admission_fence_sha256=n.sha(fence_file),fence_restoration=restored,
        new_preparer_source_sha256=n.sha(R/'scripts/prepare_unstarted_direct17_r17.py'),new_builder_source_sha256=n.sha(R/'scripts/build_tmax_native_oci_ssd17_r17.py'),
        builder_runtime_engine_id=n.NODE['engine_id'],model_calls=0,teacher_or_verifier_signals=0,healthy_trials_cancelled=0,
        old_results_and_prequeue_rejections_preserved=True,new_teacher_controller_started=False,operator_source_sha256=n.sha(Path(__file__)))
    n.freeze(OUT,value);print(json.dumps(value),flush=True)


if __name__=='__main__':main()
