"""Independent native NOP identities for explicitly registered failed environments."""
import asyncio, importlib, json, os, sys, time
from pathlib import Path
R=Path('/ssd/chenkeyi/qwen35-sft-772-20261101'); B=R/'environment-preflight30'; E=R/'formal-native-eval-r1'; C=Path('/data/chenkeyi/qwen35-sft-772-20261101/control')
sys.path[:0]=[str(R),str(E/'scripts')]
from harbor.job import Job
from harbor.models.job.config import JobConfig
from environment_evidence_audit_r3 import read,write,sha
native=importlib.import_module('run-formal-native-tb2118-r2'); prep=importlib.import_module('evaluation-preparation18-r1')
async def main():
    admission=read(B/'RECHECK_ADMISSION_R5.json'); assert admission['unique_controller_owner']==read(C/'NATIVE_ADVANCE_OWNER.json') and admission['source_sha256']==sha(Path(__file__))
    cfg=JobConfig.model_validate_json(native.selected_config(read(E/'manifests/FORMAL_801_TRIAL_PLAN.json')).read_text()); cfg.tasks=[t for t in cfg.tasks if t.path.name in admission['tasks']]
    assert len(cfg.tasks)==len(admission['tasks']); cfg.agents=[cfg.agents[0]]; cfg.agents[0].name=None; cfg.agents[0].import_path='env_preflight_shared_agent_r2:OpenHarnessPreflightNopAgent'
    cfg.job_name='qwen35-env-preflight30-native-recheck-20261102-r5'; cfg.jobs_dir=B/'jobs'; cfg.n_attempts=1; cfg.n_concurrent_trials=2; cfg.retry.max_retries=0
    os.environ['PATH']=native.D['transport']['private_client_bin']+':'+os.environ['PATH']; os.environ['OPENAI_API_KEY']='node18-local'; os.environ['TMPDIR']=str(R/'tmp'); os.environ['RSI_ENV_PREFLIGHT_SPEC_BASE']=str(B/'public-cache-recheck-r4')
    assert set(admission['tasks'])=={'torch-tensor-parallelism'}
    # Root authorized GPU0/5 to M1E3; freeze the current eight effective metadata
    # bindings before the independent NOP, preserving the old spec as history.
    import urllib.request
    deployment=read(R/'configs/diagnostic150-five-model-r1.json');models={m['tag']:m for m in deployment['models']}
    assignments={18300:'new-m1-e3-diag',18301:'new-m2-e1-diag',18302:'new-m2-e5-diag',18303:'new-m1-e3-diag',18306:'new-m1-e5-diag',18307:'new-m2-e3-diag',18308:'new-m2-e5-diag',18309:'new-m1-e3-diag'}
    gpu={18300:0,18301:1,18302:2,18308:3,18303:4,18309:5,18306:6,18307:7};opener=urllib.request.build_opener(urllib.request.ProxyHandler({}));endpoints=[];observed=[]
    for port,tag in assignments.items():
        model=models[tag]
        with opener.open('http://127.0.0.1:'+str(port)+'/model_info',timeout=5)as response:live=json.load(response)
        assert live['model_path']==model['model_path']and live['weight_version']==model['weight_version'],(port,tag,live)
        endpoints.append(dict(url='http://172.17.0.1:'+str(port)+'/model_info',model_path=live['model_path'],weight_version=live['weight_version']))
        observed.append(dict(port=port,gpu_index=gpu[port],model_tag=tag,model_info=live))
    specbase=B/'public-cache-recheck-r4';(specbase/'specs').mkdir(parents=True,exist_ok=True)
    original=B/'specs/torch-tensor-parallelism.json';specfile=specbase/'specs/torch-tensor-parallelism.json';spec=read(specfile);baseline=read(original);restored=dict(spec,model_endpoints=baseline['model_endpoints']);assert restored==baseline,'Frozen Task/public assets changed'
    assert sha(specfile)==admission['public_cache_runtime_spec_sha256'],'Frozen future runtime spec SHA changed'
    assert sorted(spec['model_endpoints'],key=lambda x:x['url'])==sorted(endpoints,key=lambda x:x['url']),'Eight endpoint roles differ from authorized current deployment'
    write(specbase/'GPU_ROLE_DEPLOYMENT_R5.json',dict(at=time.time(),source_original_spec_sha256=sha(original),current_config_sha256=sha(R/'configs/diagnostic150-five-model-r1.json'),effective_metadata=observed,approved_change='GPU0/GPU5 cold M1E3 replicas; common30 M2E1 uses18301, M2E5 uses18302/18308',metadata_only_model_generation_calls=0))
    assert not(cfg.jobs_dir/cfg.job_name).exists(); job=await Job.create(cfg)
    plan=[dict(x,trial_name=x['task_id']+'__env-preflight30-nop-r5') for x in read(E/'manifests/FORMAL_801_TRIAL_PLAN.json')['trials'] if x['model_name']=='openai/qwen35-new772-m0' and x['repetition']==1 and x['task_id'] in admission['tasks']]
    profiles=read(B/'environment-profiles-recheck-r2.json'); native.apply_trial_overrides(job._trial_configs,dict(trials=plan),profiles,namespace='q35envpreflight30r5')
    for t in job._trial_configs: prep.append_ipam(t,'selected267',t.task.path.name,3)
    async def public_cache(event):
        assert event.config.task.path.name=='torch-tensor-parallelism'
        assert event.result.agent_setup is not None and event.result.agent_setup.finished_at is not None
        assert event.result.agent_execution is None and event.result.agent_result is None
        d=Path(event.config.trials_dir)/event.trial_name;files=list(d.glob('remote-docker-*.jsonl'));assert len(files)==1
        events=[json.loads(s)for s in files[0].read_text().splitlines()];record=events[0]
        import shlex
        cmd=['python3','/home/chenkeyi/.local/share/harbor-rsi/qwen35-new772-tb21-20261101/scripts/materialize-public-verifier-cache149-r1.py','--identity',record['identity'],'--workspace',record['workspace'],'--receipt-sha256',admission['public_cache_archive_receipt_sha256']]
        output=await asyncio.create_subprocess_exec('ssh','-p','18449','chenkeyi@127.0.0.1',shlex.join(cmd),stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE)
        out,err=await asyncio.wait_for(output.communicate(),timeout=600);assert output.returncode==0,err.decode(errors='replace')[-3000:]
        proof=json.loads(out);assert proof['actual_private_cache']['passed']and proof['model_generation_calls']==0
        assert proof['source_sha256']==admission['public_cache_materializer_sha256']
        proof.update(runtime_spec_path=str(specbase/'specs/torch-tensor-parallelism.json'),runtime_spec_sha256=sha(specbase/'specs/torch-tensor-parallelism.json'),gpu_role_deployment_path=str(specbase/'GPU_ROLE_DEPLOYMENT_R5.json'),gpu_role_deployment_sha256=sha(specbase/'GPU_ROLE_DEPLOYMENT_R5.json'))
        write(d/'PUBLIC_DEPENDENCY_CACHE_PREPARATION_R1.json',proof)
    job.on_agent_started(public_cache)
    job._remaining_trial_configs=job._trial_configs
    actual=B/'ACTUAL_NATIVE_TRIALS_RECHECK_R5.json'; write(actual,dict(at=time.time(),native_job_id=str(job.id),trials=[t.model_dump(mode='json') for t in job._trial_configs],model_generation_calls=0,independent_recheck=True,source_sha256=sha(Path(__file__)),runtime_spec_base=str(specbase),runtime_deployment_sha256=sha(specbase/'GPU_ROLE_DEPLOYMENT_R5.json'),admission_sha256=sha(B/'RECHECK_ADMISSION_R5.json')))
    registry=B/'RECHECK_REGISTRY_R1.json'; previous=read(registry) if registry.exists() else dict(actual_trial_manifests=[]); assert str(actual) not in previous['actual_trial_manifests']; previous['actual_trial_manifests'].append(str(actual)); write(registry,previous)
    result=await job.run(); write(B/'RECHECK_ALL_TERMINAL_R5.json',dict(at=time.time(),terminal=len(result.trial_results),model_generation_calls=0))
if __name__=='__main__': asyncio.run(main())
