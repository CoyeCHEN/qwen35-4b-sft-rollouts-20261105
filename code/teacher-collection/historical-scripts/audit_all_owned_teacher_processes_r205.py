"""Count actual Teacher CLIs in every running campaign container, including orphans."""
import datetime
import hashlib
import json
from pathlib import Path
import shlex
import subprocess

R=Path('/home/chenkeyi/.local/share/harbor-rsi/qwen35-new-cf500-tmax500-20261029')
S=R/'stream/collection-r4'
deployment=json.loads((R/'configs/campaign-deployment17-r17.json').read_text())


def active():
    value={}
    for line in (S/'teacher-lifecycle.jsonl').open():
        event=json.loads(line);name=event['trial_name']
        if event['event']=='TEACHER_ADMITTED':value[name]=event
        elif event['event'] in ['TEACHER_AGENT_ENDED','TEACHER_FINALIZED']:value.pop(name,None)
    return value


began=active()
identities={}
for name,event in began.items():
    compose,=(S/'trials'/name).glob('remote-docker-*.compose.json')
    identities[compose.name.removeprefix('remote-docker-').removesuffix('.compose.json')]=dict(trial=name,task_id=event['task_id'])
code=r'''import datetime,json,shlex,subprocess,sys
from pathlib import Path
value=json.load(sys.stdin);d=value['runtime'];cli=['docker','--host','unix://'+d['socket']]
def run(args):return subprocess.run(cli+args,capture_output=True,text=True,check=True,timeout=20).stdout
assert run(['info','--format','{{.ID}}']).strip()==d['engine_id']
ids=run(['ps','-q']).split();containers=[];teachers=[]
for cid in ids:
 item,=json.loads(run(['inspect',cid]));identity=item['Config']['Labels'].get('io.harbor.remote-docker.identity')
 if not identity:continue
 matches=[]
 for line in run(['top',cid,'-eo','pid,stat,args']).splitlines()[1:]:
  fields=line.split(None,2)
  if len(fields)!=3:continue
  try:argv=shlex.split(fields[2])
  except ValueError:continue
  if argv[:1]==['{open-harness}']:argv=argv[1:]
  direct=bool(argv and argv[0].endswith('/bin/open-harness'))
  interpreted=bool(len(argv)>1 and Path(argv[0]).name.startswith('python') and argv[1].endswith('/bin/open-harness'))
  if (direct or interpreted) and '--prompt-file' in argv:
   matches.append(dict(pid=int(fields[0]),state=fields[1],active=fields[1][0] not in ['Z','T','t'],
    native_admission=value['active'].get(identity)))
 containers.append(dict(id=item['Id'],identity=identity,teacher_cli_processes=matches))
 teachers.extend(dict(container=item['Id'],identity=identity,**match) for match in matches if match['active'])
print(json.dumps(dict(checked_at_node17=datetime.datetime.now(datetime.timezone.utc).isoformat(),engine_id=d['engine_id'],
 running_owned_containers=len(containers),containers=containers,actual_active_teacher_clis=len(teachers),
 active_teachers=teachers,unmatched_active_teacher_clis=[item for item in teachers if item['native_admission'] is None],
 task_executables_or_model_calls_by_observer=0)))
'''
reply=subprocess.run([*deployment['ssh'],deployment['host'],shlex.join(['python3','-c',code])],
    input=json.dumps(dict(runtime=deployment['runtime'],active=identities)),capture_output=True,text=True,check=True,timeout=120)
value=json.loads(reply.stdout)
value.update(checked_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    stable_admission_set_during_all_container_probe=set(began)==set(active()),scope='All owned running containers in private17 Engine, not just admitted Trial list',
    model_calls=0,signals=0,unknown_private_orphan_is_not_silently_ignored=True)
stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
path=R/'checks'/('all-owned-teacher-processes-r205-'+stamp+'.json')
with path.open('x') as stream:json.dump(value,stream,indent=2)
print(json.dumps(dict(proof=str(path),actual_teacher_clis=value['actual_active_teacher_clis'],
    unmatched=value['unmatched_active_teacher_clis'],owned_running_containers=value['running_owned_containers'],
    stable_set=value['stable_admission_set_during_all_container_probe'])))
