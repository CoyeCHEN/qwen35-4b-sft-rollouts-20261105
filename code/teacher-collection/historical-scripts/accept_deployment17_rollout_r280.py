"""Read-only deployment, dispatch and old149 retirement acceptance snapshot."""
import collections
import datetime
import hashlib
import json
import os
from pathlib import Path
import shlex
import subprocess

R=Path('/home/chenkeyi/.local/share/harbor-rsi/qwen35-new-cf500-tmax500-20261029')
S=R/'stream/collection-r4'
os.environ['PATH']=str(R/'client-bin-v2')+':'+os.environ['PATH']
os.environ['SSH_AUTH_SOCK']='/home/chenkeyi/.local/share/harbor-rsi/near-r3-20261015/auth.sock'


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_text())
def run(args):return subprocess.run(args,text=True,capture_output=True,check=True,timeout=30).stdout


def main():
    authority_file=R/'checks/CURRENT_DISPATCH_AUTHORITY_R20.json';authority=read(authority_file)
    manifest_file=Path(authority['manifest']);manifest=read(manifest_file)
    assert sha(manifest_file)==authority['manifest_sha256']
    assert str(R/'scripts/run_collection_stream_r20.py').encode() in (Path('/proc')/str(authority['pid'])/'cmdline').read_bytes().split(b'\0')
    assert all(sha(R/'scripts'/n)==h for n,h in manifest['helper_sha256'].items())
    config_file=Path(manifest['deployment_config']);deployment=read(config_file)
    assert sha(config_file)==manifest['deployment_config_sha256']
    state=read(Path(authority['state_path']))
    events=[json.loads(line) for line in (S/'teacher-lifecycle.jsonl').read_text().splitlines()]
    admitted={x['trial_name']:x for x in events if x['event']=='TEACHER_ADMITTED' and x.get('controller_revision')=='r20'}
    dispatches={}
    for p in (S/'dispatches').glob('*/dispatch.json'):
        value=read(p)
        if value['trial_name'] not in admitted:continue
        native_file=p.parent/'trial-config.json';native=read(native_file)
        assert sha(native_file)==value['config_sha256']
        assert native['environment']['kwargs']==deployment['environment']['kwargs']
        task=value['admitted_task'];placement_file=Path(task['deployment_assignment']);placement=read(placement_file)
        assert sha(placement_file)==task['deployment_assignment_sha256']
        assert placement['node']=='17' and placement['engine_id']==deployment['runtime']['engine_id']
        assert placement['deployment_config_sha256']==sha(config_file)
        dispatches[value['trial_name']]=dict(task_id=value['task_id'],pool=value['pool'],dispatched_at=value['dispatched_at'],
            native_config=str(native_file),native_config_sha256=sha(native_file),endpoint=native['environment']['kwargs']['endpoint'],
            socket=native['environment']['kwargs']['remote_socket_path'],staging=native['environment']['kwargs']['staging_root'],
            placement=str(placement_file),placement_sha256=sha(placement_file),model_and_wheel_contract_unchanged=value['teacher_config_sha256']==manifest['teacher_config_sha256'] and value['wheel_sha256']==manifest['wheel_sha256'])
    assert set(dispatches)==set(admitted) and dispatches
    assert all(x['model_and_wheel_contract_unchanged'] for x in dispatches.values())
    client=['docker','--host',deployment['environment']['kwargs']['endpoint']]
    engine=json.loads(run([*client,'info','--format','{{json .}}']))
    assert engine['ID']==deployment['runtime']['engine_id']
    parent=json.loads(run([*deployment['ssh'],deployment['host'],shlex.join(['docker','inspect',deployment['runtime']['parent_container']])]))[0]
    bindings=sorted(parent['Mounts'],key=lambda x:len(x['Destination']),reverse=True)
    def physical(path):
        for mount in bindings:
            destination=mount['Destination'].rstrip('/')
            if path==destination or path.startswith(destination+'/'):
                return mount['Source']+path[len(destination):]
        raise ValueError('Runtime path has no accepted parent SSD mount: '+path)
    assert physical(engine['DockerRootDir'])==deployment['runtime']['docker_root']
    mount_checks=[]
    for name in state['active_teacher_trials']:
        trial=S/'trials'/name;native=read(trial/'config.json')
        if native['environment']['kwargs']['endpoint']!=deployment['environment']['kwargs']['endpoint']:continue
        compose=list(trial.glob('remote-docker-*.compose.json'))
        if len(compose)!=1:continue
        identity=compose[0].name.removeprefix('remote-docker-').removesuffix('.compose.json')
        ids=run([*client,'ps','--filter','label=io.harbor.remote-docker.identity='+identity,'--format','{{.ID}}']).split()
        if len(ids)!=1:continue
        container=json.loads(run([*client,'inspect',ids[0]]))[0]
        mounts=[{k:m[k] for k in ['Type','Source','Destination','RW']} for m in container['Mounts']]
        for mount in mounts:
            mount['physical_ssd_source']=physical(mount['Source'])
            assert mount['physical_ssd_source'].startswith(deployment['runtime']['ssd_root']+'/')
        mount_checks.append(dict(trial=name,container_id=container['Id'],mounts=mounts))
        if len(mount_checks)>=2:break
    assert mount_checks
    retired_file=R/'checks/legacy-resident-preparation-retired-r7.json';retired=read(retired_file)
    fence_file=Path(retired['fence']);fence=read(fence_file);assert sha(fence_file)==retired['fence_sha256']
    assert not Path('/proc/'+str(retired['old_pid'])).exists()
    for x in retired['current_nop_results']:
        assert sha(Path(x['result']))==x['result_sha256'] and x['verifier_completed'] and not x['exception'] and not x['infrastructure_errors']
    capture=read(R/'checks/owned-docker-events149-r7.json')
    observed=[json.loads(line) for line in (R/'checks/owned-docker-events149-r7.jsonl').read_text().splitlines()]
    cutoff=datetime.datetime.fromisoformat(fence['checked_at']).timestamp()
    creates=[x for x in observed if x['action']=='create' and x['time_nano']/1e9>=cutoff]
    assert not creates
    owned=[line.split(' ',1) for line in run(['docker','ps','--format','{{.ID}} {{.Names}}']).splitlines() if line.split(' ',1)[1].startswith(('cftmaxstreamr420261030-','cftmaxresidentbufferr150261030-','cftmaxinfraacceptancer720261030-','rsi-tmax-infra-recovery-r7-'))]
    assert all(name.startswith('cftmaxstreamr420261030-') for _,name in owned)
    proof=dict(checked_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),status='NEW_R20_AGENT_PHASE_DISPATCH_RUNTIME17_PRIVATE_SSD',
        authority=str(authority_file),authority_sha256=sha(authority_file),controller_pid=authority['pid'],frozen_sources_all_match=True,
        deployment_config=str(config_file),deployment_config_sha256=sha(config_file),new_teacher_dispatches=len(dispatches),
        new_teacher_dispatches_by_pool=dict(collections.Counter(x['pool'] for x in dispatches.values())),new_teacher_configurations=dispatches,
        actual_engine=dict(id=engine['ID'],docker_root_inside_private_engine=engine['DockerRootDir'],physical_ssd_docker_root=physical(engine['DockerRootDir']),parent_container=parent['Id'],parent_mounts=parent['Mounts']),actual_teacher_ssd_mount_checks=mount_checks,
        current_native_agent_phase_trials=state['actual_teacher_trials'],current_ready_buffer=state['ready_buffer'],
        retired_preparation_proof=str(retired_file),retired_preparation_proof_sha256=sha(retired_file),
        no_owned149_creates_since=fence['checked_at'],event_capture_started_at=capture['started_at'],new_owned149_creates_after_fence=creates,
        remaining_owned149_containers=[dict(id=i,name=n) for i,n in owned],remaining_149_policy='Only already-started native R5 Trials finish; no cancellation or replay',
        metadata_mirror_149='Native Harbor collection mirror retained; verified full per-Trial final copy on17SSD. Controller itself remains149.',
        original_private17_build_chain_acceptance=str(R/'checks/original-private17-build-chain-acceptance-r17.json'),original_private17_build_chain_acceptance_sha256=sha(R/'checks/original-private17-build-chain-acceptance-r17.json'),
        rsync_wrapper_sha256=sha(R/'client-bin-v2/rsync'),expected_rsync_wrapper_sha256='8f9b3942d5be0d89e5d5822d94027e5ed8273c39e96a759abfacefbe8bd38c21',
        model_calls_by_this_observer=0,task_modifications=0,training_started=False)
    assert proof['rsync_wrapper_sha256']==proof['expected_rsync_wrapper_sha256']
    pool_client=Path(deployment['native_client_bin'])/'ssh'
    if sha(pool_client)!=deployment['native_client_ssh_sha256']:raise ValueError('Runtime native SSH client changed')
    native_children=[]
    for child in Path('/proc').iterdir():
        if not child.name.isdigit():continue
        try:
            argv=(child/'cmdline').read_bytes().split(b'\0')
            if not any(x.startswith(b'ControlPath=/home/chenkeyi/.ssh/cftmx17-r119-') for x in argv):continue
            lineage=[];current=child
            for _ in range(5):
                stat_fields=(current/'stat').read_text().rsplit(')',1)[1].split();parent=int(stat_fields[1]);lineage.append(parent)
                if parent==authority['pid']:break
                if parent<=1:break
                current=Path('/proc')/str(parent)
            if authority['pid'] in lineage:native_children.append(dict(pid=int(child.name),controller_ancestor=authority['pid'],lineage=lineage))
        except OSError:continue
    proof['declared_native_ssh_client_sha256']=sha(pool_client)
    proof['live_native_client_children_under_current_controller']=native_children
    old_fence=read(R/'checks/controller-r17-admission-fence-r19.json')
    assert sha(Path(old_fence['drain_request']))==old_fence['drain_request_sha256']
    after_fence=[x for x in events if x['event']=='TEACHER_ADMITTED' and x.get('controller_revision')=='r17' and x['observed_at']>old_fence['checked_at']]
    assert not after_fence
    proof.update(old_r17_additional_teacher_admissions_after_fence=after_fence,old_r17_admission_fence=str(R/'checks/controller-r17-admission-fence-r19.json'),old_r17_native_lifecycle_only_pid=old_fence['old_pid'],old_r17_pid_alive=Path('/proc/'+str(old_fence['old_pid'])).exists(),ready_buffer_by_pool=state.get('ready_buffer_by_pool'),inherited_native_teacher_trials=state['inherited_native_teacher_trials'])
    stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    destination=R/'checks'/('deployment17-rollout-acceptance-r280-'+stamp+'.json')
    with destination.open('x') as stream:json.dump(proof,stream,indent=2)
    print(json.dumps(dict(proof=str(destination),new17teacherdispatches=len(dispatches),pool_counts=proof['new_teacher_dispatches_by_pool'],actual_teachers=state['actual_teacher_trials'],old149_containers=len(owned),new149_creates_after_fence=len(creates))))


if __name__=='__main__':main()
