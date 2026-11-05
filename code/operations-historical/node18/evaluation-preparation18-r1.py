"""Campaign Compose IPAM and strict, pre-model environment recovery evidence."""
import hashlib,importlib,ipaddress,json,subprocess,time
from pathlib import Path
R=Path('/ssd/chenkeyi/qwen35-sft-772-20261101');E=R/'formal-native-eval-r1'
C=Path('/data/chenkeyi/qwen35-sft-772-20261101/control')
def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,v):
    t=p.with_name(p.name+'.tmp');t.write_text(json.dumps(v,indent=2)+'\n');t.replace(p)
def identity_key(tag,task,repetition=1):return f'{tag}/{task}/{repetition}'
def ensure_ipam_manifest():
    path=E/'manifests/EVALUATION417_EXPLICIT_IPAM_R1.json'
    if path.exists():return read(path)
    diag=read(E/'manifests/DIAGNOSTIC150_TRIAL_PLAN_R1.json')['trials']
    formal=[dict(x,tag='selected267')for x in read(E/'manifests/FORMAL_801_TRIAL_PLAN.json')['trials']if x['model_name']=='openai/qwen35-new772-m0']
    entries=diag+formal;assert len(entries)==417
    networks=list(ipaddress.ip_network('10.247.64.0/18').subnets(new_prefix=28));rows={}
    for i,item in enumerate(entries):
        key=identity_key(item['tag'],item['task_id'],item['repetition']);assert key not in rows
        p=E/'configs/evaluation-ipam-r1'/f'{i:03}.compose.json';p.parent.mkdir(exist_ok=True)
        v=dict(networks=dict(default=dict(ipam=dict(config=[dict(subnet=str(networks[i]))]))))
        if p.exists():assert read(p)==v
        else:p.write_text(json.dumps(v,indent=2)+'\n')
        rows[key]=dict(subnet=str(networks[i]),compose=str(p),sha256=sha(p))
    value=dict(at=time.time(),kind='COMPOSE_ONLY_EXPLICIT_PER_TRIAL_IPAM',entries=rows,
        campaign_cidr='10.247.64.0/18',official_task_service_resources_unchanged=True,
        shared_daemon_unchanged=True,engine_id='c6e16cdf-e878-4cc5-84c8-78a56c54b5c5')
    save(path,value);return value

def append_ipam(trial,tag,task,repetition=1):
    record=ensure_ipam_manifest()['entries'][identity_key(tag,task,repetition)]
    assert sha(Path(record['compose']))==record['sha256']
    assert all('evaluation-ipam-r1'not in str(p)for p in trial.environment.extra_docker_compose)
    trial.environment.extra_docker_compose.append(Path(record['compose']))
    return record

def pre_model_failure(directory):
    """No retry eligibility from reward, score, length, or model quality."""
    p=directory/'result.json'
    if not p.exists():return None
    v=read(p)
    if v.get('failure_phase')!='environment_setup' or v.get('agent_execution')is not None or v.get('agent_setup')is not None or v.get('agent_result')is not None:return None
    exception=v.get('exception_info')or{}
    if exception.get('exception_type')not in ['RemoteDockerError','ValueError']:return None
    text=str(exception.get('exception_message',''))
    if not('all predefined address pools have been fully subnetted'in text or 'Remote input is outside declared task/Compose directories'in text):return None
    if any(p.is_file()and p.stat().st_size for folder in ['agent','agent-logs']for p in (directory/folder).rglob('*')):return None
    def declared_settings_match(declared,effective):
        if isinstance(declared,dict):return isinstance(effective,dict)and all(k in effective and declared_settings_match(value,effective[k])for k,value in declared.items())
        return declared==effective
    assert declared_settings_match(read(directory/'config.json'),v['config'])
    return dict(original_trial_path=str(directory),original_trial_id=v['id'],original_trial_name=v['trial_name'],
        result_sha256=sha(p),config_sha256=sha(directory/'config.json'),failure_phase=v['failure_phase'],
        exception_type=exception['exception_type'],exception_message=text,
        no_agent_setup=True,no_agent_execution=True,no_agent_result=True,no_agent_artifact_bytes=True,
        actual_model_attempts=0,original_config=v['config'])

def resolve_original(item,models):
    if item.get('reuse_existing_trial'):
        original=E/'jobs/qwen35-new772-new-m1-epoch3-fixed-diagnostic'/item['trial_name']
        proof=E/'manifests/E3_ORIGINAL_UNSTARTED_ACTUAL_NATIVE_TRIALS_R1.json'
        if not proof.exists():return original
        manifest=read(proof);assert manifest['original_started_trials_rerun']==0
        if item['task_id']not in manifest['original_unstarted_tasks']:return original
        selected=[x for x in manifest['actual_trials']if Path(x['task']['path']).name==item['task_id']]
        assert len(selected)==1 and not original.exists()
        return Path(manifest['native_continuation_job'])/selected[0]['trial_name']
    return E/'jobs'/models[item['tag']]['job_name']/item['trial_name']
