"""Identify exact terminal native scopes blocking two zero-model recoveries."""
import datetime
import hashlib
import json
from pathlib import Path
import shlex
import subprocess

R=Path('/home/chenkeyi/.local/share/harbor-rsi/qwen35-new-cf500-tmax500-20261029')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
 d=json.loads((R/'configs/campaign-deployment17-r21.json').read_text())
 desired={}
 root=R/'stream/public-cpython-native-setup-recovery17-r394'
 for p in (root/'environment-outcomes').glob('*.json'):
  x=json.loads(p.read_text())
  if x['status']!='ENV_FAILED' or 'Pool overlaps with other one' not in x.get('reason',''):continue
  t=Path(x['native_install_trial']);c,=t.glob('*.compose.json')
  desired[x['task_id']]=dict(failed_install_trial=str(t),failed_install_result_sha256=sha(t/'result.json'),
   subnet=json.loads(c.read_text())['networks']['default']['ipam']['config'][0]['subnet'])
 assert set(desired)=={'task_001761_0f358e39','task_009183_6590fa3c'}
 code="""import json,subprocess,ipaddress
v=json.loads(PAYLOAD); cli=['docker','--host','unix://'+v['socket']]
engine=subprocess.run(cli+['info','--format','{{.ID}}'],check=True,capture_output=True,text=True,timeout=20).stdout.strip()
ids=subprocess.run(cli+['network','ls','--format','{{.ID}}'],check=True,capture_output=True,text=True,timeout=20).stdout.split()
networks=json.loads(subprocess.run(cli+['network','inspect',*ids],check=True,capture_output=True,text=True,timeout=20).stdout)
out={}
for ident,entry in v['tasks'].items():
 matches=[]
 for n in networks:
  for config in n.get('IPAM',{}).get('Config',[]) or []:
   try:overlaps=ipaddress.ip_network(config['Subnet']).overlaps(ipaddress.ip_network(entry['subnet']))
   except (KeyError,ValueError,TypeError):continue
   if overlaps:matches.append(dict(name=n['Name'],id=n['Id'],subnet=config['Subnet'],identity=n.get('Labels',{}).get('io.harbor.remote-docker.identity'),containers=list((n.get('Containers') or {}))))
 out[ident]=matches
print(json.dumps(dict(engine_id=engine,tasks=out)))""".replace('PAYLOAD',repr(json.dumps(dict(socket=d['runtime']['socket'],tasks=desired))))
 reply=subprocess.run([*d['ssh'],d['host'],shlex.join(['python3','-c',code])],check=True,capture_output=True,text=True,timeout=70)
 live=json.loads(reply.stdout);assert live['engine_id']==d['runtime']['engine_id']
 lifecycle=[json.loads(line) for line in (R/'stream/collection-r4/teacher-lifecycle.jsonl').open()]
 cases=[]
 for ident,matches in live['tasks'].items():
  match,=matches;identity=match['identity'];assert identity and len(identity)==32
  compose,=R.glob('stream/*/trials/*/remote-docker-'+identity+'.compose.json')
  trial=compose.parent;result=trial/'result.json';raw=json.loads(result.read_text())
  assert raw['task_name']=='tmax/'+ident and raw.get('finished_at')
  assert raw.get('agent_execution',{}).get('finished_at') and raw.get('verifier',{}).get('finished_at')
  ended={x['event'] for x in lifecycle if x['trial_name']==trial.name}
  assert {'TEACHER_ADMITTED','TEACHER_AGENT_ENDED','TEACHER_FINALIZED'}<=ended
  recorder=trial/'agent/openharness-rollout/events.jsonl';assert recorder.is_file()
  cases.append(dict(task_id=ident,trial=str(trial),trial_id=raw['id'],result_sha256=sha(result),
   recorder_sha256=sha(recorder),identity=identity,network=match,source_failed_recovery=desired[ident],
   native_trial_finished_at=raw['finished_at'],teacher_agent_and_native_lifecycle_terminal=True))
 report=dict(checked_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),cases=cases,engine_id=live['engine_id'],
  source_sha256=sha(Path(__file__)),read_only=True,cleanup_or_teacher_actions=0)
 p=R/'checks/TERMINAL_SUBNET_LEAK_SCOPES_R399.json'
 with p.open('x') as f:json.dump(report,f,indent=2)
 print(json.dumps(dict(cases=cases,scope_sha256=sha(p))))


if __name__=='__main__':main()
