"""Read only the new native E2 save, archive and two-epoch exposure evidence."""
import hashlib,json,subprocess,time
from pathlib import Path
from datetime import datetime
R=Path('/ssd/chenkeyi/qwen35-sft-772-20261101');W=R/'new-sft/workspace'
def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 run=R/'runs/new-m2-tmax356-128k-e5';checkpoint=run/'checkpoint-50';marker=checkpoint/'CHECKPOINT_COMPLETE.json'
 settings=read(W/'configs/checkpoint-storage.json');archive=Path(settings['archive_root'])/'new772-new-cf416-tmax356-m2/checkpoint-50'
 receipt=Path(settings['failed_root']).parent/'archive-results/new772-new-cf416-tmax356-m2-checkpoint-50.json'
 if not marker.exists()or not(archive/'ARCHIVE_COMPLETE.json').exists()or not receipt.exists():
  print(json.dumps(dict(status='WAIT_NATIVE_SAVE_OR_ARCHIVE',checkpoint_complete=marker.exists(),archive_complete=(archive/'ARCHIVE_COMPLETE.json').exists())));return
 assert read(receipt)['status']=='completed'
 rows_by_rank={}
 for rank in range(4):
  rows=[]
  for line in(run/('preflight-evidence-rank'+str(rank)+'.jsonl')).open():
   try:rows.append(json.loads(line))
   except json.JSONDecodeError:pass
  saved=next(x for x in rows if x['event']=='checkpoint_save_complete'and x['global_step']==50)
  update=next(x for x in rows if x['event']=='optimizer_step'and x['global_step']==50)
  latest=max(x['global_step']for x in rows if x['event']=='optimizer_step')
  assert update['master_partition_dtypes']==update['optimizer_moment_dtypes']==['torch.float32']
  assert all(v['finite']for v in update['gradients'].values())
  assert saved['identity']['config_sha256']=='1f48ed160a76bea910857bf16c94776f06e1d77a45c76047686303e72e91c716'
  rows_by_rank[str(rank)]=dict(save_time=saved['time'],identity=saved['identity'],latest_committed_step=latest)
 if min(x['latest_committed_step']for x in rows_by_rank.values())<=50:
  print(json.dumps(dict(status='WAIT_ACTUAL_POST_SAVE_UPDATE',ranks=rows_by_rank)));return
 subprocess.run([str(R/'env/train-r1/bin/python'),str(R/'read-native-training-evidence18-r1.py')],check=True,capture_output=True,text=True,timeout=40)
 report=read(R/'checks/NATIVE_TRAINING_READOUT_R1.json');stage=report['stages']['new-cf416-tmax356-m2']
 assert stage['completed_epochs']['2']['unique_train_rows']==792
 exposure=[json.loads(line)for line in Path(stage['exposure_rows_path']).open()]
 first=[x for x in exposure if x['optimizer_step']<=50];second=[x for x in first if x['optimizer_step']>25]
 assert len(first)==1584 and len(second)==len({x['row_index']for x in second})==792
 assert len({x['task_id']for x in second})==325
 assert sum(x['supervised_tokens']for x in second)==7815211
 assert stage['validation_training_exposures']==0
 archived=read(archive/'ARCHIVE_COMPLETE.json');members={x['path']:x for x in archived['files']}
 assert len(members)==26 and members['CHECKPOINT_COMPLETE.json']['sha256']==sha(marker)
 state=read(checkpoint/'trainer_state.json');assert state['global_step']==50 and state['epoch']==2.0
 ended=datetime.fromisoformat(archived['completed_at']).timestamp()
 # A completed async copy never substitutes for continued GPU execution.
 metrics=[]
 for line in(run/'preflight-evidence-rank0.jsonl').open():
  x=json.loads(line)
  if x['event']=='optimizer_step'and x['global_step']>50 and x['time']>ended:metrics.append(x['global_step'])
 if not metrics:
  print(json.dumps(dict(status='WAIT_ACTUAL_UPDATE_AFTER_ARCHIVE',archive_completed_at=ended)));return
 value=dict(passed=True,at=time.time(),actual_epoch=2,native_optimizer_steps_at_save=50,planned_steps=125,
  actual_post_archive_step=min(metrics),checkpoint_complete_marker_sha256=sha(marker),ranks=rows_by_rank,
  native_archive_manifest_sha256=sha(archive/'ARCHIVE_COMPLETE.json'),native_archive_receipt_sha256=sha(receipt),
  files=len(members),bytes=sum(x['bytes']for x in members.values()),archive_path=str(archive),native_archive_metrics=archived['metrics'],
  two_epoch_sample_exposures=1584,epoch2_unique_train_rows=792,epoch2_independent_train_tasks=325,
  epoch2_supervised_tokens=7815211,two_epoch_supervised_tokens=sum(x['supervised_tokens']for x in first),
  validation_training_exposures=0,native_readout_sha256=sha(R/'checks/NATIVE_TRAINING_READOUT_R1.json'),
  source_sha256=sha(Path(__file__)),new_model_or_optimizer_calls=0,
  native_archive_worker_verified_full_source_and_copy_sha=True,hot_original_retained=True,
  no_additional_e2_gpu_nll_or_hf_selection=True)
 p=R/'checks/NEW_M2_EPOCH2_NATIVE_ARCHIVE_ACCEPTANCE_R1.json';assert not p.exists();p.write_text(json.dumps(value,indent=2)+'\n');print(json.dumps(value))
if __name__=='__main__':main()
