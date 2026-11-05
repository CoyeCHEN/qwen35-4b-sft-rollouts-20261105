"""Native candidate for one unattempted Task's diagnosed public APT timeout.

Use the existing verifier-only public dependency proxy. No teacher environment
proxy, original Task/test changes, automatic Ready publication or model calls.
"""
import asyncio
import json
import os
from pathlib import Path
from uuid import uuid4
from harbor.models.job.config import RetryConfig
from harbor.trial.queue import TrialQueue
from collection_attempts_r8 import attempt_counts
from collection_selection_r7 import active_rows
import collection_readiness_r16 as n

S=n.R/'stream/verifier-public-proxy-candidate17-r203'
IDENT='data-processing_20260420_020307_002'


async def main():
    S.mkdir(exist_ok=False)
    if attempt_counts().get(IDENT,0):raise ValueError('Task already attempted; preserve it')
    prior=n.R/'stream/public-setup-timeout-diagnostics17-r191/TERMINAL.json'
    diagnosis=json.loads(prior.read_text())
    case=next(x for x in diagnosis['outcomes'] if x['task_id']==IDENT)
    if case['steps'][0]['return_code']!=124:raise ValueError('Public bootstrap timeout was not reproduced')
    proxy_path=n.R/'manifests/VERIFIER_PUBLIC_PROXY_CANDIDATES_R55.json'
    proxy=json.loads(proxy_path.read_text())['verifier_public_dependency_env']
    if not proxy or any(k.lower() not in ['http_proxy','https_proxy','no_proxy','all_proxy'] for k in proxy):
        raise ValueError('Unexpected public dependency proxy contract')
    row=next(x for x in active_rows(attempt_counts()) if x['task_id']==IDENT)
    admitted=n.prepare_identity(row)
    n.freeze(S/'PLAN.json',dict(task_id=IDENT,source_sha256=n.sha(Path(__file__)),public_diagnosis=str(prior),
        public_diagnosis_sha256=n.sha(prior),existing_proxy_plan=str(proxy_path),existing_proxy_plan_sha256=n.sha(proxy_path),
        candidate_verifier_env=proxy,task_resources_verifier_deadlines_and_tests_unchanged=True,
        deployment_config_sha256=n.CONFIG_SHA,teacher_environment_proxy_changed=False,model_calls=0,
        ready_publication=False,native_concurrency=1))
    queue=TrialQueue(n_concurrent=1,retry_config=RetryConfig(max_retries=0))
    out=dict(task_id=IDENT,status='CANDIDATE_FAILED',native_results={},model_calls=0,ready_publication=False,
        candidate_verifier_env=proxy,original_tests_or_task_changes=0)
    try:
        n.freeze(S/'image.json',await asyncio.to_thread(n.ensure_resident,admitted))
        n.freeze(S/'initial.json',await asyncio.to_thread(n.initial,admitted))
        for kind in ['install','nop']:
            if attempt_counts().get(IDENT,0):raise ValueError('Task admission changed; preserve it')
            cfg=n.native_config(admitted,kind);cfg.trials_dir=S/'trials'
            if kind=='install':cfg.agent.env={}
            if kind=='nop':
                for key,value in proxy.items():
                    if key in cfg.verifier.env and cfg.verifier.env[key]!=value:raise ValueError('Existing verifier env conflict')
                    cfg.verifier.env[key]=value
            directory=S/'dispatches'/str(uuid4());directory.mkdir(parents=True)
            (directory/'trial-config.json').write_text(cfg.model_dump_json(indent=2))
            n.freeze(directory/'dispatch.json',dict(task_id=IDENT,kind=kind,trial_name=cfg.trial_name,
                config_sha256=n.sha(directory/'trial-config.json'),model_calls=0,candidate_only=True))
            result=await queue.submit(cfg);trial=S/'trials'/cfg.trial_name
            out['native_results'][kind]=dict(trial=str(trial),result_sha256=n.sha(trial/'result.json'))
            n.freeze(S/'ssd-trial-archives'/(trial.name+'.json'),await asyncio.to_thread(n.archive_trial,trial))
            if result.exception_info or result.infrastructure_errors:raise ValueError('Original native lifecycle failed: '+str(result.exception_info))
            if kind=='nop':out['native_nop_reward']=n.verify_nop(result,trial,admitted)
        out.update(status='VERIFIER_PUBLIC_PROXY_NATIVE_ACCEPTED_DEPLOYMENT_PENDING',admitted_task=admitted,
            engine_id=n.NODE['engine_id'],existing_paid_attempts=attempt_counts().get(IDENT,0))
    except Exception as error:out.update(error_type=type(error).__name__,reason=str(error)[-1400:])
    finally:
        n.freeze(S/'TERMINAL.json',out)
        try:n.freeze(S/'image-release.json',await asyncio.to_thread(n.release_cold_cache,admitted))
        except Exception as error:n.freeze(S/'image-release-error.json',dict(reason=str(error)[-600:]))
    print(json.dumps(out),flush=True)


if __name__=='__main__':
    os.environ['PATH']=n.DEPLOYMENT['native_client_bin']+':'+str(n.R/'client-bin-v2')+':'+os.environ['PATH']
    os.environ['SSH_AUTH_SOCK']='/home/chenkeyi/.local/share/harbor-rsi/near-r3-20261015/auth.sock'
    for key in ['DEEPSEEK_API_KEY','OPENAI_API_KEY','GH_TOKEN']:os.environ.pop(key,None)
    asyncio.run(main())
