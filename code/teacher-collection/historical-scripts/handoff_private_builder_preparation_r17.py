"""Retire only finite zero-model preparers after their current native work ends."""
import datetime
import fcntl
import hashlib
import json
import os
from pathlib import Path
import signal
import time

import prepare_unstarted_direct17_r17 as target

n=target.n
R=n.R
PIDS={'r13':35765,'r14':1182007}
OUT=R/'checks/direct17-build-preparation-handoff-r17.json'
PROGRESS=R/'checks/direct17-build-preparation-handoff-r17-progress.json'


def state(proc):
    return next(s.split(':',1)[1].strip().split()[0] for s in (proc/'status').read_text().splitlines() if s.startswith('State:'))


def children(proc):
    return sorted({int(x) for p in (proc/'task').glob('*/children') for x in p.read_text().split()})


def identity(pid):
    p=Path('/proc')/str(pid)
    return dict(pid=pid,start_ticks=(p/'stat').read_text().rsplit(')',1)[1].split()[19],argv=(p/'cmdline').read_bytes().split(b'\0'))


def main():
    lock=(R/'checks/direct17-build-preparation-handoff-r17.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    if OUT.exists():raise FileExistsError('Observe completed preparation handoff')
    acceptance=R/'checks/private17-buildkit-r16-acceptance.json'
    accepted=json.loads(acceptance.read_text())
    if not accepted['passed'] or accepted['builder_engine_id']!=n.NODE['engine_id']:raise ValueError('Private native builder acceptance differs')
    plan=R/'manifests/TMAX_UNSTARTED_DIRECT_SSD17_R13.json'
    old={};paused=set();retired=[];began=time.monotonic()
    def progress(stage,**extra):
        value=dict(stage=stage,checked_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),pid=os.getpid(),paused_preparer_pids=sorted(paused),retired_preparer_pids=retired,teacher_or_verifier_signals=0,**extra)
        temporary=PROGRESS.with_suffix('.tmp');temporary.write_text(json.dumps(value,indent=2));temporary.replace(PROGRESS)
    def same(version):
        pid=PIDS[version];p=Path('/proc')/str(pid)
        if not p.exists():return False
        info=identity(pid)
        if info['start_ticks']!=old[version]['start_ticks'] or str(R/('scripts/prepare_unstarted_direct17_'+version+'.py')).encode() not in info['argv']:
            raise ValueError('Preparer PID identity changed')
        return True
    def check_time():
        if time.monotonic()-began>7200:raise TimeoutError('Current native work preserved; no forced cleanup')
    def native_results(version):
        scope=R/('stream/direct17-native-source-'+version);complete=[]
        for p in (scope/'trials').glob('*'):
            result=p/'result.json'
            if result.exists():
                data=json.loads(result.read_text())
                cfg=data.get('config',{})
                if cfg.get('agent',{}).get('name') not in ['nop','open-harness']:
                    raise ValueError('Unexpected native precheck agent')
                complete.append(dict(path=str(result),sha256=n.sha(result)))
            elif any(x.is_file() for x in p.rglob('*')):
                raise ValueError('Unfinished native precheck has durable lifecycle files')
        return complete
    def pause_idle(version):
        allowed={'r14':{'WAITING_FOR_EXISTING_FINITE17_SOURCE_BUILD_AND_INITIAL_CLEANUP','TASK_PREPARATION_TERMINAL'},'r13':{'BUILDING_UNCHANGED_CONTEXT_ON17','TASK_PREPARATION_TERMINAL'}}[version]
        pid=PIDS[version];proc=Path('/proc')/str(pid);scope=R/('stream/direct17-native-source-'+version)
        while same(version):
            check_time();before=json.loads((scope/'state.json').read_text())
            if before['stage'] not in allowed:
                progress('WAITING_FOR_NATIVE_BOUNDARY',preparer=version,observed=before);time.sleep(1);continue
            os.kill(pid,signal.SIGSTOP);paused.add(pid)
            until=time.monotonic()+1
            while state(proc) not in ['T','t'] and time.monotonic()<until:time.sleep(.01)
            after=json.loads((scope/'state.json').read_text())
            if state(proc) not in ['T','t'] or after['stage'] not in allowed or (version=='r14' and children(proc)):
                os.kill(pid,signal.SIGCONT);paused.remove(pid);time.sleep(1);continue
            native_results(version)
            old[version]['boundary']=after;old[version]['children_at_pause']=[]
            for child in children(proc):
                cp=Path('/proc')/str(child)
                try:old[version]['children_at_pause'].append(dict(pid=child,argv=(cp/'cmdline').read_bytes().replace(b'\0',b' ').decode()))
                except FileNotFoundError:pass
            progress('PREPARER_PAUSED_NATIVE_CHILDREN_ALLOWED_TO_FINISH',preparer=version,observed=after)
            return
        retired.append(pid)
    try:
        for version,pid in PIDS.items():
            old[version]=identity(pid)
            old[version]['argv']=[x.decode() for x in old[version]['argv'] if x]
            source=R/('scripts/prepare_unstarted_direct17_'+version+'.py')
            old_plan=R/('stream/direct17-native-source-'+version+'/PLAN.json')
            if n.sha(source)!=json.loads(old_plan.read_text())['source_sha256']:raise ValueError('Frozen old preparer source changed')
            old[version].update(source=str(source),source_sha256=n.sha(source))
        pause_idle('r14');pause_idle('r13')
        for version,pid in PIDS.items():
            if pid in retired:continue
            proc=Path('/proc')/str(pid)
            while True:
                check_time();same(version)
                pending=[]
                for child in children(proc):
                    cp=Path('/proc')/str(child)
                    try:
                        if state(cp)!='Z':pending.append(child)
                    except FileNotFoundError:pass
                if not pending:break
                progress('WAITING_FOR_EXISTING_NATIVE_CHILD_EXIT',preparer=version,children=pending);time.sleep(1)
            old[version]['native_results']=native_results(version)
        boundary=old['r13'].get('boundary',{});ident=boundary.get('current_task_id')
        if ident:
            path=n.NODE['ssd_root']+'/buildkit-rootless-r2/archives/'+ident+'/client-proxy-r3/build.json'
            observe="import json,sys,hashlib;from pathlib import Path;p=Path(sys.argv[1]);print(json.dumps({'path':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'receipt':json.loads(p.read_text())}) if p.exists() else json.dumps({'absent':True}))"
            previous_build=target.remote(observe,path)
            # A captured native builder must finish its receipt before retirement.
            if any('build_tmax_native_oci_ssd17_r3.py' in x['argv'] for x in old['r13'].get('children_at_pause',[])) and previous_build.get('absent'):
                raise ValueError('Existing native build ended without its receipt; preserve parent for investigation')
        else:previous_build=None
        for version,pid in PIDS.items():
            if pid in retired:continue
            same(version);os.kill(pid,signal.SIGTERM);os.kill(pid,signal.SIGCONT);paused.remove(pid)
            deadline=time.monotonic()+10
            while (Path('/proc')/str(pid)).exists() and time.monotonic()<deadline:time.sleep(.05)
            if (Path('/proc')/str(pid)).exists():raise RuntimeError('Preparer has not exited; no duplicate started')
            retired.append(pid)
        value=dict(status='OLD_PREPARERS_NATIVE_WORK_FINISHED_NEW_PRIVATE_BUILDER_AUTHORIZED',checked_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
            retired_preparer_pids=retired,old_preparers=old,last_original_build=previous_build,
            source_plan=str(plan),source_plan_sha256=n.sha(plan),builder_acceptance=str(acceptance),builder_acceptance_sha256=n.sha(acceptance),
            new_preparer_source_sha256=n.sha(R/'scripts/prepare_unstarted_direct17_r17.py'),new_builder_source_sha256=n.sha(R/'scripts/build_tmax_native_oci_ssd17_r17.py'),
            builder_runtime_engine_id=n.NODE['engine_id'],model_calls=0,teacher_or_verifier_signals=0,healthy_trials_cancelled=0,
            old_results_and_prequeue_rejections_preserved=True,new_teacher_controller_started=False)
        n.freeze(OUT,value);progress('OLD_PREPARERS_RETIRED_NEW_PRIVATE_BUILDER_AUTHORIZED');print(json.dumps(value),flush=True)
    finally:
        for pid in paused:
            if (Path('/proc')/str(pid)).exists():os.kill(pid,signal.SIGCONT)


if __name__=='__main__':main()
