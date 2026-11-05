"""Read-only, one labelled resource inventory per Engine and resource type."""
import concurrent.futures, hashlib, json, os, re, subprocess, time
from pathlib import Path
R = Path('/ssd/chenkeyi/qwen35-sft-772-20261101')
LABEL = 'io.harbor.remote-docker.identity'
def read(p): return json.loads(p.read_text())
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p, value):
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + '.' + str(os.getpid()) + '.tmp')
    tmp.write_text(json.dumps(value, indent=2) + '\n'); tmp.replace(p)
def inventory(endpoint):
    start = time.monotonic()
    def query(kind):
        args = ['docker', '--host', endpoint]
        if kind == 'engine': args += ['info', '--format', '{{json .}}']
        else:
            args += [kind, 'ls'] + (['-a'] if kind == 'container' else [])
            args += ['--filter', 'label=' + LABEL, '--format', '{{json .}}']
        began = time.monotonic()
        try:
            p = subprocess.run(args, capture_output=True, text=True, timeout=18)
            if p.returncode: raise RuntimeError(p.stderr[-1000:])
            data = json.loads(p.stdout) if kind == 'engine' else [json.loads(s) for s in p.stdout.splitlines() if s.strip()]
            # An invalid/truncated label representation must never imply clean.
            if kind != 'engine':
                for row in data:
                    labels = row.get('Labels')
                    if isinstance(labels, str): labels = dict(v.split('=', 1) for v in labels.split(',') if '=' in v)
                    if not isinstance(labels, dict) or LABEL not in labels: raise ValueError('Missing identity label in inventory')
                    row['identity'] = labels[LABEL]
            return dict(ok=True, data=data, seconds=time.monotonic()-began, command=args)
        except Exception as exc: return dict(ok=False, error=repr(exc), seconds=time.monotonic()-began, command=args)
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        result = dict(zip(['engine','container','network','volume'], pool.map(query, ['engine','container','network','volume'])))
    return dict(endpoint=endpoint, checked_at=time.time(), seconds=time.monotonic()-start, queries=result)
def attempt(cfg, base, snapshots):
    d = Path(cfg['trials_dir'])/cfg['trial_name']; result = d/'result.json'
    if not result.exists(): return dict(status='RUNNING' if d.exists() else 'PENDING', trial_path=str(d))
    raw=read(result); reasons=[]; unknown=[]; proof=d/'agent/ENV_PREFLIGHT_RUNTIME.json'
    runtime=read(proof) if proof.exists() else None
    if not runtime or not runtime.get('passed'): reasons.append('actual_cli_runtime_probe_not_passed')
    verifier=raw.get('verifier_result') or {}; reward=(verifier.get('rewards') or {}).get('reward')
    if raw.get('exception_info'): reasons.append('native_exception:'+str(raw['exception_info'].get('exception_type')))
    if raw.get('infrastructure_errors'): reasons.append('native_infrastructure_errors')
    if not (raw.get('verifier') or {}).get('finished_at'): reasons.append('official_verifier_not_completed')
    if verifier.get('return_code')!=0 or reward not in [0,1]: reasons.append('official_verifier_missing_or_invalid_reward')
    logs=[]
    for p in (d/'verifier').rglob('*'):
        if not p.is_file(): continue
        logs.append(dict(path=str(p),bytes=p.stat().st_size,sha256=sha(p)))
        if p.suffix in ['.txt','.log'] or any(s in p.name for s in ['output','stdout','stderr']):
            if re.search(r'(Temporary failure in name resolution|Could not resolve host|curl: \((6|7|18|22|28|35|60)\)|Failed to download|Failed to fetch|No matching distribution found|Could not fetch URL|SSL certificate problem)',p.read_text(errors='replace'),re.I): reasons.append('verifier_download_or_network_failure:'+p.name)
    if not logs: reasons.append('verifier_logs_not_collected')
    artifact=d/'artifacts/manifest.json'
    if not artifact.exists(): reasons.append('artifact_manifest_not_collected')
    cleanup=None
    cleanup_identity=runtime
    if cleanup_identity is None:
        records=list(d.glob('remote-docker-*.jsonl'))
        if len(records)==1:
            source_events=[json.loads(s) for s in records[0].read_text().splitlines()]
            connected=next((e for e in source_events if e.get('action')=='connected'),None)
            if connected:
                cleanup_identity=dict(identity=connected['identity'],endpoint=connected['endpoint'],engine_id=connected['daemon_id'])
    if runtime:
        task=Path(cfg['task']['path']).name; spec=read(base/'specs'/(task+'.json'))
        for asset in spec['public_files']:
            target=Path(asset['target']); mounts=[m for m in runtime['mounts'] if target==Path(m['Destination']) or Path(m['Destination']) in target.parents]
            if not mounts or max(mounts,key=lambda m:len(m['Destination']))['RW']: reasons.append('public_mount_not_read_only:'+str(target))
    if cleanup_identity:
        snap=snapshots[cleanup_identity['endpoint']]; queries=snap['queries']; found={}
        engine=queries['engine']
        if not engine['ok']: unknown.append('cleanup_engine_identity_query_failed:'+engine['error'])
        elif engine['data']['ID']!=cleanup_identity['engine_id']: reasons.append('cleanup_engine_identity_mismatch')
        for kind in ['container','network','volume']:
            query=queries[kind]
            if not query['ok']: unknown.append('cleanup_'+kind+'_query_failed:'+query['error']); found[kind]=None
            else: found[kind]=[v.get('ID',v.get('Name')) for v in query['data'] if v['identity']==cleanup_identity['identity']]
        complete=not unknown and not any(found.values()) and engine['ok'] and engine['data']['ID']==cleanup_identity['engine_id']
        cleanup=dict(checked_at=snap['checked_at'],resources=found,complete=complete,identity=cleanup_identity['identity'],engine_id=cleanup_identity['engine_id'],batch_inventory=True)
        if any(v for v in found.values() if v is not None): reasons.append('owned_resources_remain_after_native_cleanup')
    return dict(status='FAIL' if reasons else ('UNKNOWN' if unknown else 'PASS'),native_trial_id=raw['id'],native_job_id=raw['config'].get('job_id'),trial_path=str(d),result_sha256=sha(result),runtime_proof_path=str(proof) if runtime else None,runtime_proof_sha256=sha(proof) if runtime else None,actual_runtime=runtime,official_verifier=verifier,verifier_timing=raw.get('verifier'),verifier_logs=logs,artifact_manifest_sha256=sha(artifact) if artifact.exists() else None,cleanup=cleanup,failures=reasons,unknown_reasons=unknown,model_generation_calls=0,official_verifier_reward_not_a_model_score=True)
def audit(group):
    start=time.monotonic(); os.environ['PATH']=str(R/'formal-controller18-client-bin-r1')+':'+os.environ['PATH']
    E=R/'formal-native-eval-r1'
    if group=='30':
        base=R/'environment-preflight30'; sample=E/'manifests/DIAGNOSTIC30_SAMPLING_MANIFEST_R1.json'; identities=read(sample)['selected_task_identities']; paths=[base/'ACTUAL_NATIVE_TRIALS_R1.json']; out=base/'ENV_PREFLIGHT_30_MANIFEST.json'; key='official_identity'; expected=30
    else:
        base=R/'synthetic32/env-runtime'; sample=R/'synthetic32/FROZEN_USER_SYNTHETIC32_SOURCE_R2.json'; identities=read(sample)['tasks']; paths=[R/'synthetic32/prep-ACTUAL_NATIVE_TRIALS_R1.json']; out=R/'synthetic32/ENV_PREFLIGHT_32_MANIFEST.json'; key='user_dataset_identity'; expected=32
    registry=base/'RECHECK_REGISTRY_R1.json'
    if registry.exists(): paths += [Path(v) for v in read(registry)['actual_trial_manifests']]
    configs=[]
    for p in paths:
        if p.exists(): configs+=read(p)['trials']
    endpoints=set()
    for cfg in configs:
        p=Path(cfg['trials_dir'])/cfg['trial_name']/'agent/ENV_PREFLIGHT_RUNTIME.json'
        if p.exists(): endpoints.add(read(p)['endpoint'])
        else:
            records=list((Path(cfg['trials_dir'])/cfg['trial_name']).glob('remote-docker-*.jsonl'))
            if len(records)==1:
                for line in records[0].read_text().splitlines():
                    event=json.loads(line)
                    if event.get('action')=='connected':endpoints.add(event['endpoint']);break
    if out.exists() and read(out).get('frozen'): return read(out)
    snapshots={e:inventory(e) for e in endpoints}
    inventory_path=base/'engine-inventory-history'/(str(time.time_ns())+'.json'); write(inventory_path,dict(at=time.time(),engines=snapshots))
    rows=[]
    for identity in identities:
        task=identity['task_id']; attempts=[]
        for cfg in configs:
            if Path(cfg['task']['path']).name!=task: continue
            try: attempts.append(attempt(cfg,base,snapshots))
            except Exception as exc: attempts.append(dict(status='UNKNOWN',trial_path=str(Path(cfg['trials_dir'])/cfg['trial_name']),unknown_reasons=['task_audit_failed:'+repr(exc)]))
        last=dict(attempts[-1]) if attempts else dict(status='PENDING')
        historical=[a for a in attempts[:-1] if a.get('cleanup') and not a['cleanup']['complete']]
        if last['status']=='PASS' and historical:
            last.update(status='UNKNOWN',unknown_reasons=['Historical attempt cleanup still unconfirmed'])
        rows.append(dict(task_id=task,status=last['status'],**{key:identity},attempts=attempts,latest_failure_reasons=last.get('failures',[])+last.get('unknown_reasons',[])))
    assert len(rows)==len({r['task_id'] for r in rows})==expected
    value=dict(kind='ACTUAL_SHARED'+group+'_NO_MODEL_ENVIRONMENT_ACCEPTANCE',updated_at=time.time(),frozen=False,sampling_manifest_sha256=sha(sample),tasks=rows,expected_unique_tasks=expected,passed=sum(r['status']=='PASS' for r in rows),failed=sum(r['status']=='FAIL' for r in rows),unknown=sum(r['status']=='UNKNOWN' for r in rows),running=sum(r['status']=='RUNNING' for r in rows),pending=sum(r['status']=='PENDING' for r in rows),actual_model_generation_calls=0,official_tasks_tests_verifiers_unmodified=True,source_sha256=sha(Path(__file__)),batch_inventory_path=str(inventory_path),batch_inventory_sha256=sha(inventory_path),engine_query_count=sum(len(s['queries']) for s in snapshots.values()),audit_seconds=time.monotonic()-start,historical_failed_attempts=sum(a['status']=='FAIL' for r in rows for a in r['attempts']))
    def signature(v): return [(r['task_id'],r['status'],r.get('latest_failure_reasons'),[a.get('result_sha256') for a in r.get('attempts',[])]) for r in v['tasks']]
    if out.exists():
        old=read(out)
        if old.get('frozen'): return old
        if old.get('source_sha256')!=value['source_sha256'] or signature(old)!=signature(value):
            historical=base/'manifest-history'/(str(time.time_ns())+'-'+sha(out)+'.json'); historical.parent.mkdir(exist_ok=True); historical.write_bytes(out.read_bytes())
    write(out,value); print(json.dumps({k:value[k] for k in ['passed','failed','unknown','running','pending','audit_seconds','engine_query_count']}),flush=True); return value
