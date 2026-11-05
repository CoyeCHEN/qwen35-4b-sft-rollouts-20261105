"""One original NOP with bounded live reads before native120s verifier cleanup."""
import asyncio
import ast
import datetime
import fcntl
import json
import os
from pathlib import Path
import shlex
import subprocess

from harbor.models.job.config import RetryConfig
from harbor.trial.queue import TrialQueue
from collection_attempts_r8 import attempt_counts
from collection_selection_r7 import active_rows
import collection_readiness_r21 as n

IDENT = 'task_008794_911eb529'
S = n.R / 'stream/official-nop-stall-diagnostic17-r450'

NODE_READ = r'''
import json,sys,subprocess,datetime
v=json.load(sys.stdin);d=v['deployment'];cli=['docker','-H','unix://'+d['socket']]
def run(args):
 p=subprocess.run(args,capture_output=True,text=True,timeout=20)
 return dict(returncode=p.returncode,stdout=p.stdout,stderr=p.stderr[:2000])
assert run(cli+['info','--format','{{.ID}}'])['stdout'].strip()==d['engine_id']
ids=run(cli+['ps','--filter','label=io.harbor.remote-docker.identity='+v['identity'],'--format','{{.ID}}'])['stdout'].split()
out=dict(checked_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),engine_id=d['engine_id'],identity=v['identity'],container_ids=ids,read_only=True)
if len(ids)==1:
 cid=ids[0]
 out['process_threads']=run(cli+['exec','-u','0',cid,'sh','-c','ps -eLo pid,tid,ppid,stat,etime,comm,wchan:32'])
 out['process_commands']=run(cli+['top',cid,'-eo','pid,ppid,stat,args'])
 out['official_verifier_stdout']=run(cli+['exec','-u','0',cid,'sh','-c','if test -f /logs/verifier/test-stdout.txt; then head -c 262144 /logs/verifier/test-stdout.txt; fi'])
 out['official_verifier_stderr']=run(cli+['exec','-u','0',cid,'sh','-c','if test -f /logs/verifier/test-stderr.txt; then head -c 16384 /logs/verifier/test-stderr.txt; fi'])
print(json.dumps(out))
'''


def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def snapshot(identity):
    request = dict(deployment=n.NODE, identity=identity)
    reply = subprocess.run([*n.DEPLOYMENT['ssh'], n.DEPLOYMENT['host'],
        shlex.join([n.DEPLOYMENT['python17'], '-c', NODE_READ])], input=json.dumps(request),
        text=True, capture_output=True, check=True, timeout=100)
    return json.loads(reply.stdout)


async def main():
    import run_collection_stream_r21 as controller
    controller.validate_controller_runtime()
    S.mkdir(parents=True, exist_ok=True)
    lock = (S/'worker.lock').open('a')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    assert not (S/'PLAN.json').exists(), 'Inspect the existing diagnostic; never replay implicitly'
    counts = attempt_counts()
    assert counts[IDENT] == 1
    prior = n.R/'stream/public-cpython-native-setup-recovery17-r394/trials/task_008794_911eb529__HQ6jpVH'
    prior_cfg = json.loads((prior/'config.json').read_text())
    original = Path(prior_cfg['task']['path'])
    test = original/'tests/test_final_state.py'
    tree = ast.parse(test.read_text())
    test_function = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'test_git_hook_functionality')
    ast_evidence = dict(function_line=test_function.lineno, function_end_line=test_function.end_lineno,
        assert_lines=[node.lineno for node in ast.walk(test_function) if isinstance(node,ast.Assert)],
        thread_calls=[dict(line=node.lineno,keywords=[key.arg for key in node.keywords]) for node in ast.walk(test_function)
            if isinstance(node,ast.Call) and ast.unparse(node.func)=='threading.Thread'],
        stop_calls=[node.lineno for node in ast.walk(test_function) if isinstance(node,ast.Call) and ast.unparse(node.func)=='smtp_stop.set'],
        cleanup_finally_blocks=[node.lineno for node in ast.walk(test_function) if isinstance(node,ast.Try) and node.finalbody])
    row = next(value for value in active_rows(counts) if value['task_id'] == IDENT)
    admitted = n.prepare_identity(row)
    cfg = n.native_config(admitted, 'nop')
    cfg.trials_dir = S/'trials'
    cfg.agent.env = {}
    assert cfg.agent.name == 'nop' and cfg.verifier.override_timeout_sec is None
    assert __import__('tomllib').loads((original/'task.toml').read_text())['verifier']['timeout_sec'] == 120
    source_hashes = {str(path):n.sha(path) for path in [original/'task.toml',original/'instruction.md',test,original/'tests/test.sh']}
    n.freeze(S/'PLAN.json',dict(checked_at=now(),task_id=IDENT,trial_name=cfg.trial_name,
        deployment_config_sha256=n.CONFIG_SHA,engine_id=n.NODE['engine_id'],runtime_node='17',
        original_verifier_timeout_sec=120,original_sources=source_hashes,static_thread_cleanup_evidence=ast_evidence,
        actual_or_conservative_attempts=sum(counts.values()),model_calls=0,teacher_dispatches=0,
        verifier_or_reward_originals_modified=False,source_sha256=n.sha(Path(__file__))))
    n.freeze(S/'image-materialization.json',await asyncio.to_thread(n.ensure_resident,admitted))
    n.freeze(S/'initial-outcome.json',await asyncio.to_thread(n.initial,admitted))
    (S/'trial-config.json').write_text(cfg.model_dump_json(indent=2))
    queue = TrialQueue(n_concurrent=1,retry_config=RetryConfig(max_retries=0))
    pending = asyncio.create_task(queue.submit(cfg))
    trial = S/'trials'/cfg.trial_name
    observed = 0
    while not pending.done():
        await asyncio.sleep(10)
        compositions = list(trial.glob('remote-docker-*.compose.json'))
        if len(compositions) != 1:
            continue
        identity = compositions[0].name.removeprefix('remote-docker-').removesuffix('.compose.json')
        try:
            value = await asyncio.to_thread(snapshot,identity)
        except Exception as error:
            value = dict(checked_at=now(),error_type=type(error).__name__,reason=str(error)[:1000])
        n.freeze(S/'live-snapshots'/f'{observed:03d}.json',value)
        observed += 1
        n.freeze(S/'observations'/f'{observed:03d}.json',dict(checked_at=now(),snapshots=observed,native_trial=cfg.trial_name,model_calls=0))
    result = await pending
    raw = json.loads((trial/'result.json').read_text())
    n.freeze(S/'ssd-archive.json',await asyncio.to_thread(n.archive_trial,trial))
    assert attempt_counts() == counts
    assert all(n.sha(Path(path)) == digest for path,digest in source_hashes.items())
    terminal = dict(checked_at=now(),native_trial=str(trial),result_sha256=n.sha(trial/'result.json'),
        snapshot_count=observed,verifier=raw.get('verifier'),exception=raw.get('exception_info'),
        infrastructure_errors=raw.get('infrastructure_errors'),verifier_result=raw.get('verifier_result'),
        original_sources_unchanged=True,teacher_budget_unchanged=True,actual_or_conservative_attempts=sum(counts.values()),
        model_calls=0,teacher_dispatches=0,ready_published=False)
    n.freeze(S/'TERMINAL.json',terminal)
    print(json.dumps(dict(terminal=str(S/'TERMINAL.json'),snapshots=observed,
        exception_type=(raw.get('exception_info') or {}).get('exception_type'),model_calls=0,ready_published=False)))


if __name__ == '__main__':
    os.environ['PATH']=n.DEPLOYMENT['native_client_bin']+':'+str(n.R/'client-bin-v2')+':'+os.environ['PATH']
    os.environ['SSH_AUTH_SOCK']='/home/chenkeyi/.local/share/harbor-rsi/near-r3-20261015/auth.sock'
    for key in ['DEEPSEEK_API_KEY','OPENAI_API_KEY','GH_TOKEN']:
        os.environ.pop(key,None)
    asyncio.run(main())
