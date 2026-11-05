"""Time the exact frozen readiness scan in an isolated metadata-only replica."""
import ast
import datetime
import hashlib
import json
from pathlib import Path
import time

import collection_readiness_r14 as n
from collection_attempts_r8 import attempt_counts
from collection_selection_r7 import active_rows


def main():
    source=n.R/'scripts/run_collection_stream_r14.py';raw=source.read_bytes();tree=ast.parse(raw)
    parent=next(x for x in tree.body if isinstance(x,ast.AsyncFunctionDef) and x.name=='main')
    funcs=[x for x in parent.body if isinstance(x,ast.FunctionDef) and x.name in ['ready_paths','refresh']]
    if len(funcs)!=2:raise ValueError('Frozen readiness functions changed')
    namespace=dict(read=lambda p:json.loads(p.read_text()),sha=n.sha,blocking_review=n.blocking_review,
        normalize_ready=n.normalize_ready,CONFIG_SHA=n.CONFIG_SHA,DEPLOYMENT=n.DEPLOYMENT,
        readiness_roots=n.readiness_roots,Path=Path,outcomes={},blocked_ready_receipts={})
    module=ast.Module(body=funcs,type_ignores=[]);ast.fix_missing_locations(module);exec(compile(module,str(source),'exec'),namespace)
    rows=active_rows(attempt_counts());times=[]
    for iteration in range(4):
        wall=time.monotonic();cpu=time.process_time();namespace['refresh'](rows)
        times.append(dict(iteration=iteration,seconds=time.monotonic()-wall,cpu_seconds=time.process_time()-cpu,accepted_tasks=len(namespace['outcomes'])))
    value=dict(checked_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),frozen_controller_sha256=hashlib.sha256(raw).hexdigest(),measurements=times,
        scope='Exact ready_paths/refresh functions copied by AST into isolated metadata dictionaries; first pass warms existing immutable placement/normalization caches. No active controller state changed.',
        model_calls=0,teacher_dispatches=0,task_containers_created=0,task_or_reward_changes=0,
        source_sha256=n.sha(Path(__file__)))
    with (n.R/'checks/native-readiness-scan-profile-r125.json').open('x') as f:json.dump(value,f,indent=2)
    print(json.dumps(value),flush=True)


if __name__=='__main__':main()
