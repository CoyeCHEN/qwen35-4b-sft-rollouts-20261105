"""Freeze a finite preservation/cleanup plan for five already-ended native scopes."""
import hashlib
import json
from pathlib import Path
import shlex
import subprocess

R = Path('/home/chenkeyi/.local/share/harbor-rsi/qwen35-new-cf500-tmax500-20261029')
source = R / 'checks/remaining-network-block-inventory-r181.json'
inventory = json.loads(source.read_text())
sha = lambda path:hashlib.sha256(path.read_bytes()).hexdigest()
tasks = []
for item in inventory['tasks']:
    match, = item['matches']
    identity = match['identity']
    if not identity:
        raise ValueError('Do not touch a network without exact native ownership')
    if match['containers']:
        container, = match['containers']
        if container['terminal_identity_status'] != 'NATIVE_TERMINAL_RESULT_BOUND':
            raise ValueError('Preserve an unclosed or unbound native scope')
        result = Path(container['original_result'])
        expected = container['original_result_sha256']
    else:
        compose, = R.glob('stream/*/trials/*/remote-docker-' + identity + '.compose.json')
        result = compose.parent / 'result.json'
        expected = sha(result)
    if sha(result) != expected:
        raise ValueError('Original native Result changed')
    native = json.loads(result.read_text())
    if not native.get('finished_at') or Path(native['config']['task']['path']).name != item['task_id']:
        raise ValueError('Original native Trial is not terminal for this Task')
    tasks.append(dict(task_id=item['task_id'], identity=identity, original_trial=result.parent.name,
        original_result=str(result), original_result_sha256=expected, original_native_id=native['id'],
        original_finished_at=native['finished_at'], original_exception_type=(native.get('exception_info') or {}).get('exception_type'),
        original_agent_execution=native.get('agent_execution'),
        original_container_ids=[x['id'] for x in match['containers']],
        original_container_images=[x['image'] for x in match['containers']],
        previous_attempt_budget_used=item['previous_attempt_budget_used'],
        source_setup_failure=item['precheck_failure'], source_setup_failure_sha256=item['precheck_failure_sha256']))
assert len(tasks) == 5
plan = dict(tasks=tasks, engine_id=inventory['engine_id'], source_inventory_sha256=sha(source),
    source_sha256=sha(Path(__file__)), native_scope_concurrency=1,
    original_results_or_rewards_rewritten=False, teacher_attempts_restarted=0, new_model_calls=0,
    preservation='Full remaining container filesystem, all named-volume contents and bind inputs before exact owned resource removal; pause only a verified terminal scope during filesystem snapshot')
path = R / 'checks/terminal-network-preservation-plan-r182.json'
with path.open('x') as stream:
    json.dump(plan, stream, indent=2)
deployment = json.loads((R / 'configs/campaign-deployment17-r16.json').read_text())
destination = deployment['runtime']['ssd_root'] + '/terminal-network-preservation-r182'
code = "import sys;from pathlib import Path;p=Path(sys.argv[1]);p.mkdir(parents=True,exist_ok=False);(p/'PLAN.json').write_bytes(sys.stdin.buffer.read())"
subprocess.run([*deployment['ssh'], deployment['host'], shlex.join(['python3', '-c', code, destination])],
    input=path.read_bytes(), capture_output=True, check=True, timeout=30)
print(json.dumps(dict(plan=str(path), tasks=[x['task_id'] for x in tasks], destination=destination, model_calls=0)))
