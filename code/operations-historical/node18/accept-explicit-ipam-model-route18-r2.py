"""Actual explicit-subnet container to authorized18 serving; GET only, no generation."""
import asyncio,importlib,json,os,time
from pathlib import Path
from harbor.models.trial.config import TrialConfig
from harbor.trial.trial import Trial
m=importlib.import_module('run-user-evaluation-native18-r1');prep=importlib.import_module('evaluation-preparation18-r1');R=m.R;E=m.E
async def main():
 os.environ['OPENAI_API_KEY']='node18-local';os.environ['PATH']=m.native.D['transport']['private_client_bin']+':'+os.environ['PATH'];os.environ['TMPDIR']=str(R/'tmp')
 rows=prep.read(E/'manifests/DIAGNOSTIC30_ACTUAL_TRIALS_new-m2-e5-diag.json')['trials'];cfg=TrialConfig.model_validate(next(x for x in rows if Path(x['task']['path']).name=='regex-log'))
 cfg.trials_dir=E/'diagnostics'/('explicit-ipam-model-route-'+str(time.time_ns()));cfg.trial_name='no-agent-model-info-only';cfg.job_id=None
 network=prep.append_ipam(cfg,'selected267','regex-log',3);trial=await Trial.create(cfg);env=trial.agent_environment;started=False
 try:
  await env.start(force_build=False);started=True
  res=await env.exec("python3 -c 'import urllib.request,json; p=urllib.request.build_opener(urllib.request.ProxyHandler({})); print(json.dumps(json.load(p.open(\"http://172.17.0.1:18303/model_info\",timeout=5))))'",timeout_sec=15)
  prep.save(R/'checks/EVALUATION_EXPLICIT_IPAM_MODEL_ROUTE_EXEC_R2.json',dict(at=time.time(),return_code=res.return_code,stdout=res.stdout[:6000],stderr=res.stderr[:6000],actual_generation_calls=0))
  assert res.return_code==0
  info=json.loads(res.stdout);assert info['model_path']==str(R/'epoch-models/new-m1-epoch3')and info['weight_version']=='2e02fec581cbb3c802cd1e0e80ac2c9568bead3a9002338f4d661ea6ac94053d'
 finally:
  if started:await env.stop(delete=True)
 proof=dict(passed=True,at=time.time(),actual_container_project=env.project,network=network,actual_get_model_info=info,actual_model_generation_calls=0,agent_setup=False,official_verifier_run=False,source_sha256=prep.sha(Path(__file__)))
 prep.save(R/'checks/EVALUATION_EXPLICIT_IPAM_MODEL_ROUTE_ACCEPTANCE_R2.json',proof);print(json.dumps(dict(passed=True,actual_model_generation_calls=0,network=network)))
if __name__=='__main__':asyncio.run(main())
