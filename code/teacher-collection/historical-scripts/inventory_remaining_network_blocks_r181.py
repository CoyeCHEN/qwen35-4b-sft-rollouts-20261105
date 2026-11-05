"""Read-only binding of remaining setup subnet conflicts to exact native scopes."""
import datetime
import hashlib
import json
from pathlib import Path
import shlex
import subprocess

R = Path('/home/chenkeyi/.local/share/harbor-rsi/qwen35-new-cf500-tmax500-20261029')
deployment = json.loads((R / 'configs/campaign-deployment17-r16.json').read_text())
sha = lambda path:hashlib.sha256(path.read_bytes()).hexdigest()
requests = []
for path in (R / 'stream/pre-agent-setup-recheck17-r162/environment-outcomes').glob('*.json'):
    value = json.loads(path.read_text())
    if value['status'] != 'ENV_FAILED' or 'Pool overlaps' not in value.get('reason', ''):
        continue
    if value['task_id'] == 'data-science_20260414_211453_004':
        continue
    trial = Path(value['native_install_trial'])
    config = json.loads((trial / 'config.json').read_text())
    network = Path(config['environment']['extra_docker_compose'][0])
    subnet = json.loads(network.read_text())['networks']['default']['ipam']['config'][0]['subnet']
    requests.append(dict(task_id=value['task_id'], subnet=subnet,
        precheck_failure=str(path), precheck_failure_sha256=sha(path),
        native_failure_result=str(trial / 'result.json'), native_failure_result_sha256=sha(trial / 'result.json'),
        previous_attempt_budget_used=value['existing_attempt_budget_used']))
node_code = '''import json,subprocess,sys,ipaddress
v=json.load(sys.stdin);d=v['deployment'];cli=['docker','--host','unix://'+d['socket']]
def run(args):return subprocess.run(cli+args,capture_output=True,text=True,check=True,timeout=30).stdout
assert run(['info','--format','{{.ID}}']).strip()==d['engine_id']
ids=run(['network','ls','-q']).split();nets=json.loads(run(['network','inspect',*ids]));out=[]
for item in v['tasks']:
 matches=[]
 for network in nets:
  if not any(ipaddress.ip_network(x['Subnet']).overlaps(ipaddress.ip_network(item['subnet'])) for x in network['IPAM'].get('Config',[]) or [] if 'Subnet' in x):continue
  identity=(network.get('Labels') or {}).get('io.harbor.remote-docker.identity');containers=[]
  if identity:
   for cid in run(['ps','-aq','--filter','label=io.harbor.remote-docker.identity='+identity]).split():
    container,=json.loads(run(['inspect',cid]));top=run(['top',cid,'-eo','pid,stat,comm']) if container['State']['Running'] else ''
    containers.append(dict(id=container['Id'],image=container['Config']['Image'],state=container['State'],labels=container['Config']['Labels'],mounts=container['Mounts'],process_commands=[line.split(None,2)[2] for line in top.splitlines()[1:] if len(line.split(None,2))==3]))
  matches.append(dict(id=network['Id'],name=network['Name'],subnets=network['IPAM']['Config'],identity=identity,containers=containers))
 out.append(dict(**item,matches=matches))
print(json.dumps(dict(engine_id=d['engine_id'],tasks=out,model_calls=0,resources_changed=False)))
'''
reply = subprocess.run([*deployment['ssh'], deployment['host'], shlex.join(['python3', '-c', node_code])],
    input=json.dumps(dict(deployment=deployment['runtime'], tasks=requests)), text=True,
    capture_output=True, check=True, timeout=120)
report = json.loads(reply.stdout)
for item in report['tasks']:
    for match in item['matches']:
        for container in match['containers']:
            labels = container['labels']
            files = labels.get('com.docker.compose.project.config_files', '').split(',')
            if len(files) != 1:
                container['terminal_identity_status'] = 'UNREVIEWED_COMPOSE_IDENTITY'
                continue
            compose = Path(files[0])
            result = compose.parent / 'result.json'
            if not result.exists():
                container['terminal_identity_status'] = 'NATIVE_RESULT_NOT_TERMINAL_PRESERVE'
                continue
            native = json.loads(result.read_text())
            if not native.get('finished_at'):
                container['terminal_identity_status'] = 'NATIVE_RESULT_NOT_TERMINAL_PRESERVE'
                continue
            if Path(native['config']['task']['path']).name != item['task_id']:
                raise ValueError('Subnet belongs to a different selected Task')
            if native['config']['environment']['kwargs']['remote_socket_path'] != deployment['runtime']['socket']:
                raise ValueError('Original native scope belongs to another Engine socket')
            container.update(terminal_identity_status='NATIVE_TERMINAL_RESULT_BOUND',
                original_result=str(result), original_result_sha256=sha(result),
                original_compose=str(compose), original_compose_sha256=sha(compose),
                original_native_id=native['id'], original_finished_at=native['finished_at'],
                original_agent_execution=native.get('agent_execution'), original_verifier=native.get('verifier'),
                original_exception_type=(native.get('exception_info') or {}).get('exception_type'),
                recorder_collected_on149=(compose.parent / 'agent/openharness-rollout/events.jsonl').exists())
report.update(checked_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
    source_sha256=sha(Path(__file__)), original_results_or_attempts_modified=False)
target = R / 'checks/remaining-network-block-inventory-r181.json'
with target.open('x') as stream:
    json.dump(report, stream, indent=2)
print(json.dumps(dict(proof=str(target),tasks=[dict(task_id=x['task_id'],matches=[dict(identity=m['identity'],containers=[dict(id=c['id'],status=c['terminal_identity_status'],commands=c['process_commands']) for c in m['containers']]) for m in x['matches']]) for x in report['tasks']])))
