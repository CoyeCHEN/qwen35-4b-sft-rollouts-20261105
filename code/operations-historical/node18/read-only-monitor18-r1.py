import pathlib,json,subprocess,time,os
R=pathlib.Path('/ssd/chenkeyi/qwen35-sft-772-20261101')
def cmd(a):
 r=subprocess.run(a,capture_output=True,text=True,timeout=15)
 return dict(returncode=r.returncode,stdout=r.stdout,stderr=r.stderr[:400])
def events_tail(p):
 if not p.exists():return []
 with p.open('rb')as f:
  size=p.stat().st_size;start=max(0,size-512*1024);f.seek(start);data=f.read()
 lines=data.splitlines()
 if start and lines:lines=lines[1:]
 out=[]
 for line in lines:
  try:out.append(json.loads(line))
  except json.JSONDecodeError:continue
 return out
state=dict(kind='READ_ONLY_NODE18_TRAINING_OBSERVATION_V1',checked_at=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),execution_node='18',automatic_dispatch=False,collection_closed=True)
state['native_sequence']=cmd(['systemctl','--user','show','qwen35-old-four-node18-20261101-r1','-p','ActiveState','-p','MainPID','-p','Result'])
state['gpu']=cmd(['nvidia-smi','--query-gpu=index,uuid,name,memory.total,memory.used,utilization.gpu','--format=csv,noheader,nounits'])
state['gpu_processes']=cmd(['nvidia-smi','--query-compute-apps=gpu_uuid,pid,process_name,used_memory','--format=csv,noheader,nounits'])
state['arms']={}
for arm in ['A','B','C','D']:
 out=R/'runs/old-four-arm'/arm;rows=events_tail(out/'preflight-evidence-rank0.jsonl')
 steps=[r for r in rows if r['event']=='optimizer_step'];last=steps[-1]if steps else {}
 metrics=[r for r in rows if r['event']=='metrics'];r=dict(actual_optimizer_step=last.get('global_step',0),last_optimizer_step_at=last.get('time'),peak_allocated_bytes=last.get('peak_allocated_bytes'),peak_reserved_bytes=last.get('peak_reserved_bytes'),gradients=last.get('gradients'),optimizer_moment_dtypes=last.get('optimizer_moment_dtypes'),latest_metrics=metrics[-1].get('metrics')if metrics else None,complete_native_checkpoints=sorted(p.name for p in out.glob('checkpoint-*')if(p/'CHECKPOINT_COMPLETE.json').exists()))
 if(out/'trainer_state.json').exists():
  t=json.loads((out/'trainer_state.json').read_text());r['saved_trainer_state']=dict(global_step=t.get('global_step'),max_steps=t.get('max_steps'),epoch=t.get('epoch'))
 state['arms'][arm]=r
state['native_loader_gate']=(R/'frozen-data-772-r1/DATA_AUDIT_NATIVE_LOADER.json').exists()
sg=pathlib.Path('/data/chenkeyi/qwen35-sft-772-20261101/control/NATIVE_SGLANG_PREFIX_PROGRESS.json')
state['sglang_all_target_gate'] = json.loads(sg.read_text()) if sg.exists() else {'status':'RUNNING_ON17; shared progress pending'}
state['formal_new_m1_m2_started']=False
p=pathlib.Path('/data/chenkeyi/qwen35-sft-772-20261101/control/CURRENT_EXECUTION_STATUS.json');q=p.with_suffix('.tmp');q.write_text(json.dumps(state));q.replace(p)
print(json.dumps(state))
