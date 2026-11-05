import pathlib,json,time,subprocess,fcntl,threading
R=pathlib.Path('/ssd/chenkeyi/qwen35-sft-772-20261101')
P=R/'runs/old-four-arm/A';F=pathlib.Path('/data/chenkeyi/qwen35-sft-772-20261101/control')
done=threading.Event()
def fence():
 with(F/'training.lock').open('a')as f:
  fcntl.flock(f,fcntl.LOCK_EX)
  done.wait(120)
threading.Thread(target=fence,daemon=True).start()
start=time.time()
while time.time()-start<3600:
 checkpoint=P/'checkpoint-2'
 if(checkpoint/'CHECKPOINT_COMPLETE.json').exists():
  ready=True
  for rank in range(4):
   events=[]
   path=P/f'preflight-evidence-rank{rank}.jsonl'
   for line in path.open():
    try:events.append(json.loads(line))
    except json.JSONDecodeError:pass
   ready=ready and any(e['event']=='checkpoint_save_complete'and e['global_step']==2 for e in events)
  if ready:
   result=subprocess.run(['systemctl','--user','stop','qwen35-old-four-node18-20261101-r1.service'],capture_output=True,text=True,timeout=200)
   assert result.returncode==0,result.stderr
   record=dict(status='OLD_FOUR_DEFERRED_BY_LATEST_USER_NEW_TRAINING_PRIORITY',checkpoint=str(checkpoint),retained_optimizer_step=2,original_scheduler_horizon=530,all_four_rank_native_save_callbacks_completed=True,automatic_BCD_not_started=True,no_new_research_gpu_dispatch_allowed_before801_trials=True,stopped_only_project_owned_unit='qwen35-old-four-node18-20261101-r1.service',finished_at=time.time())
   (F/'OLD_FOUR_SAFE_DEFERRAL.json').write_text(json.dumps(record,indent=2));print(json.dumps(record),flush=True)
   done.set();break
 time.sleep(1)
else:
 done.set();raise RuntimeError('Native checkpoint boundary did not arrive within bounded guard time; inspect original process')
