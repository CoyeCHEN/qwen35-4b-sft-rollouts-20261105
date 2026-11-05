"""Reconnect exactly three detached sandboxes; never start or rerun an Agent."""
import asyncio,fcntl,json,os,shlex,subprocess,time,uuid
from pathlib import Path,PurePosixPath
from harbor.environments.factory import EnvironmentFactory
from harbor.models.task.task import Task
from harbor.models.trial.config import TrialConfig
from harbor.models.trial.paths import TrialPaths
from harbor.verifier.verifier import Verifier
from environment_evidence_audit_r3 import read,write,sha
R=Path('/ssd/chenkeyi/qwen35-sft-772-20261101'); E=R/'formal-native-eval-r1'; B=R/'detached-native-recovery-r1'; C=Path('/data/chenkeyi/qwen35-sft-772-20261101/control')
PROBE=r'''import pathlib,json,time,os,signal,hashlib
rows=[];signalled=[];budget=float(__import__('sys').argv[1]); do_signal=__import__('sys').argv[2]=='enforce'
for p in pathlib.Path('/proc').iterdir():
 if not p.name.isdigit():continue
 try:
  argv=[s.decode(errors='replace')for s in(p/'cmdline').read_bytes().split(b'\x00')if s]
  if not any(pathlib.Path(s).name=='open-harness'for s in argv):continue
  st=(p/'stat').read_text().rsplit(')',1)[1].split();elapsed=float(pathlib.Path('/proc/uptime').read_text().split()[0])-int(st[19])/os.sysconf('SC_CLK_TCK')
  config=argv[argv.index('--config')+1]if'--config'in argv else None
  row=dict(pid=int(p.name),start_ticks=st[19],elapsed_seconds=elapsed,config=config);rows.append(row)
  if do_signal and config and config.startswith('/harbor/agent-runtime/harbor-open-harness-')and elapsed>budget:
   assert(p/'stat').read_text().rsplit(')',1)[1].split()[19]==row['start_ticks'];os.kill(int(p.name),signal.SIGTERM);signalled.append(row)
 except(FileNotFoundError,ProcessLookupError):pass
p=pathlib.Path('/logs/agent/open-harness.complete.json')
print(json.dumps(dict(at=time.time(),processes=rows,completion=json.loads(p.read_text())if p.exists()else None,deadline_budget_sec=budget,graceful_sigterm=signalled,no_sigkill=True)))'''
async def recover(item):
    ident=item['identity'];folder=B/ident;folder.mkdir(parents=True,exist_ok=True);status=folder/'RECOVERY_EVIDENCE.json'
    if status.exists() and read(status).get('terminal'):return read(status)
    value=dict(at=time.time(),original_identity=ident,original_trial_path=item['original_trial_path'],original_trial_uuid=None,original_uuid_not_reconstructed=True,recovery_record_id=str(uuid.uuid4()),original_result_unchanged=True,new_agent_runs=0,new_model_attempts=0,source_sha256=sha(Path(__file__)),terminal=False)
    try:
        source=Path(item['source_directory']);cfg=TrialConfig.model_validate_json((source/'config.json').read_text());assert sha(source/'config.json')==item['config_sha256']
        task=Task(cfg.task.path); paths=TrialPaths(folder/'collected');paths.mkdir()
        eventfile=source/('remote-docker-'+ident+'.jsonl');events=[json.loads(s)for s in eventfile.read_text().splitlines()];first=events[0];assert first['identity']==ident
        compose=source/('remote-docker-'+ident+'.compose.json');doc=read(compose);assert doc['services']['main']['labels']['io.harbor.remote-docker.identity']==ident
        # Restore provider HANDLE DATA from immutable evidence. No environment.start,
        # Agent.setup/run, live-process memory change, or Trial UUID fabrication.
        cfg.environment.kwargs['endpoint']='ssh://chenkeyi@127.0.0.1:18449'
        env=EnvironmentFactory.create_environment_from_config(cfg.environment,environment_dir=task.paths.environment_dir,environment_name=task.short_name,session_id='recovery-record-'+value['recovery_record_id'],trial_paths=paths,task_env_config=task.config.environment)
        env.identity=ident;env.project=first['project'];env.workspace=PurePosixPath(first['workspace']);env.root=env.workspace.parent;env._remote_compose=compose;env._prepared=True;env._workspace_created=True;env._agent_runtime_dir=PurePosixPath('/harbor/agent-runtime');env._agent_runtime_volume_key='agent-runtime';env._verifier_test_volume_key='verifier-tests';env.evidence=folder/('remote-docker-'+ident+'.jsonl')
        env._read_only_services={k for k,v in doc['services'].items()if v.get('read_only')};await env._connect();await env._shell(env._marker_guard()+'true')
        ids=await env._resources();assert len(ids['container'])==1
        inspected=json.loads((await env._run(env._docker('inspect',ids['container'][0]))).stdout)[0];assert inspected['Image']==item['expected_image_id'] and inspected['Config']['Labels']['io.harbor.remote-docker.identity']==ident
        value.update(status='RECONNECTED_ORIGINAL_AGENT_WATCHED',provider_identity_verified=True,container_id=inspected['Id'],image_id=inspected['Image'],container_oom_flag=inspected['State']['OOMKilled'],engine_id='c6e16cdf-e878-4cc5-84c8-78a56c54b5c5',original_config_sha256=item['config_sha256']);write(status,value)
        budget=(cfg.agent.override_timeout_sec or task.config.agent.timeout_sec)*(cfg.agent_timeout_multiplier if cfg.agent_timeout_multiplier is not None else cfg.timeout_multiplier)
        signalled=False
        while True:
            command=shlex.join(['/harbor/agent-runtime/harbor-open-harness-venv/bin/python','-c',PROBE,str(budget),'observe'if signalled else'enforce'])
            result=await env.exec(command,cwd='/',timeout_sec=20,user='root');assert result.return_code==0;observed=json.loads(result.stdout)
            write(folder/('observation-'+str(time.time_ns())+'.json'),observed);value['last_observation']=observed
            if observed['graceful_sigterm']:
                signalled=True;value['original_deadline_reinstated_with_sigterm']=observed;value['operator_controller_loss_caused_deadline_overrun']=True
            write(status,value)
            if not observed['processes'] and observed['completion'] is not None:break
            if signalled and time.time()-value['original_deadline_reinstated_with_sigterm']['at']>60:
                value.update(status='INFRASTRUCTURE_INTERRUPTED_CORE_DID_NOT_CLOSE_AFTER_GRACEFUL_DEADLINE',terminal=True,workspace_retained=True);write(status,value);return value
            await asyncio.sleep(10)
        value.update(status='ORIGINAL_AGENT_CLOSED_VERIFIER_PENDING',original_cli_completion=observed['completion']);write(status,value)
        marker=folder/'OFFICIAL_VERIFIER_STARTED.json'
        if marker.exists():raise RuntimeError('Prior verifier dispatch ambiguous; do not repeat it')
        write(marker,dict(at=time.time(),original_identity=ident,original_test_sha256=sha(task.paths.tests_dir/'test.sh')))
        verifier=Verifier(task=task,trial_paths=paths,environment=env,override_env=cfg.verifier.env)
        timeout=(cfg.verifier.override_timeout_sec or task.config.verifier.timeout_sec)*(cfg.verifier_timeout_multiplier if cfg.verifier_timeout_multiplier is not None else cfg.timeout_multiplier)
        with env.with_default_user(task.config.verifier.user):result=await asyncio.wait_for(verifier.verify(),timeout=timeout)
        value.update(status='OFFICIAL_VERIFIER_COMPLETE_COLLECTING_ORIGINAL_RECORDER',official_verifier=result.model_dump(mode='json'),verifier_finished_at=time.time());write(status,value)
        await env.download_dir(PurePosixPath('/logs/agent'),paths.agent_dir)
        files=[dict(path=str(p.relative_to(paths.trial_dir)),bytes=p.stat().st_size,sha256=sha(p))for p in paths.trial_dir.rglob('*')if p.is_file()];write(folder/'COLLECTED_FILE_SHA256.json',dict(files=files,at=time.time()))
        value.update(status='ORIGINAL_AGENT_AND_OFFICIAL_VERIFIER_RECONNECTED_COMPLETE',terminal=True,workspace_retained=True,original_raw_result_remains_infrastructure_unknown=True,not_claimed_normal_original_trial_success=True,recorder_semantic_audit_still_required=True,collected_file_manifest_sha256=sha(folder/'COLLECTED_FILE_SHA256.json'));write(status,value);return value
    except Exception as exc:
        value.update(status='INFRASTRUCTURE_INTERRUPTED_RECOVERY_BLOCKED',terminal=True,blocker=repr(exc),workspace_retained=True);write(status,value);return value
async def main():
    admission=read(B/'ADMISSION_R1.json');assert admission['unique_controller_owner']==read(C/'NATIVE_ADVANCE_OWNER.json')and admission['source_sha256']==sha(Path(__file__))
    os.environ['PATH']=str(R/'formal-controller18-client-bin-r1')+':'+os.environ['PATH'];os.environ['TMPDIR']=str(R/'tmp')
    with(B/'original-three-lifecycle.lock').open('a')as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        results=await asyncio.gather(*(recover(x)for x in admission['trials']));write(B/'ALL_RECOVERY_TERMINAL.json',dict(at=time.time(),trials=results,original_results_unchanged=True,new_agent_runs=0))
if __name__=='__main__':asyncio.run(main())
