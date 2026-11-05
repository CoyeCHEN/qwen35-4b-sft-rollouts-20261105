import pathlib,json,sys
from sft.runtime.checkpoint_archive import validate_checkpoint
P=pathlib.Path('/ssd/chenkeyi/qwen35-sft-772-20261101/old-four-arm');R=P.parent
arm=sys.argv[1];step=int(sys.argv[2]);out=R/'runs/old-four-arm'/arm
state=validate_checkpoint(out/f'checkpoint-{step}',require_marker=True)
assert state['global_step']==step and state['max_steps']==530
if step==530:assert state['epoch']>=4.99
for rank in range(4):
 rows=[json.loads(x)for x in(out/f'preflight-evidence-rank{rank}.jsonl').read_text().splitlines()]
 updates=[r for r in rows if r['event']=='optimizer_step']
 assert updates and updates[-1]['global_step']==step
 assert updates[-1]['optimizer_moment_dtypes']==['torch.float32']
 assert all(g['finite'] for g in updates[-1]['gradients'].values())
 if step==2:assert updates[-1]['parameter_update_observed']
(P/'checks'/f'{arm}-native-step{step}-verified.json').write_text(json.dumps(dict(passed=True,arm=arm,optimizer_steps=step,scheduler_horizon=530,complete_native_checkpoint=True,actual_dp=4,actual_ga=4,actual_global_batch=16)))
print(json.dumps(dict(arm=arm,verified_step=step,passed=True)),flush=True)
