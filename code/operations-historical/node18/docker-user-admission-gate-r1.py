#!/usr/bin/python3
"""Project-local Docker admission stop; existing scoped operations stay native."""
import json,os,sys,time
from pathlib import Path
R=Path('/ssd/chenkeyi/qwen35-sft-772-20261101');C=Path('/data/chenkeyi/qwen35-sft-772-20261101/control');args=sys.argv[1:]
if 'compose'in args and '--project-name'in args:
 project=args[args.index('--project-name')+1]
 policy=json.loads((C/'ENV_PREFLIGHT30_DOCKER_ADMISSION_POLICY_R1.json').read_text())
 # config is the first environment preparation operation. Cleanup/exec are never held.
 creates=any(x in args for x in ['config','up','create','build','run'])
 allowed=project in policy['inflight_projects']or any(project.startswith(p)for p in policy['preflight_prefixes'])
 release=C/'ENV_PREFLIGHT30_GATE_RELEASE_R1.json'
 if creates and not allowed and not release.exists():
  directory=R/'environment-preflight30/operator-paused-before-environment';directory.mkdir(parents=True,exist_ok=True)
  value=dict(at=time.time(),reason='USER_REQUESTED_NEW_TRIAL_ADMISSION_PAUSE',project=project,actual_container_started=False,actual_model_calls=0,recover_only_after_env30_frozen=True)
  (directory/(project+'-'+str(time.time_ns())+'.json')).write_text(json.dumps(value)+'\n')
  sys.stderr.write('USER_REQUESTED_NEW_TRIAL_ADMISSION_PAUSE: no environment or model attempt started; preserve as operator cancellation, never a model zero\n')
  raise SystemExit(75)
os.execv('/usr/bin/docker',['/usr/bin/docker',*args])
