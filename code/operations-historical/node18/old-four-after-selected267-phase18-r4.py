"""Existing unique advance leaf: audited267, idle owned SGL release, native old four."""
import hashlib,importlib,json,subprocess,time
from pathlib import Path
phase=importlib.import_module('diagnostic150-phase18-r1');handoff=importlib.import_module('start-priority32-cold-replicas18-r3');worker=importlib.import_module('resume-old-four-native18-r3')
R=phase.R;E=phase.E;C=phase.C;P=R/'old-four-arm';read=phase.read;sha=phase.sha;save=phase.save;props=phase.props

def selected267_gate():
 required=[E/'checks/SELECTED267_COMPARISON_R1.json',E/'checks/SELECTED267_AUDIT_COMPLETE_R1.json',E/'checks/SELECTED267_NATIVE_ALL_TERMINAL_R1.json',E/'checks/SELECTED267_ROWS_R1.jsonl',E/'manifests/SELECTED267_ACTUAL_TRIALS_R1.json',E/'manifests/SELECTED267_BOUND_TRIAL_PLAN_R1.json',R/'checks/SELECTED267_MODEL_BINDING_R1.json']
 missing=[str(p)for p in required if not p.exists()]
 if missing:return dict(passed=False,reason='WAIT_SELECTED267_NATIVE_AND_RECORDER_AUDIT',missing=missing,formal801_required=False)
 comparison,audit,terminal,rows_path,actual_path,plan_path,binding_path=required;done=read(comparison);audited=read(audit);closed=read(terminal);actual=read(actual_path);plan=read(plan_path);binding=read(binding_path)
 assert done['complete'] and done['expected']==done['terminal']==267 and audited['terminal']==closed['terminal']==267
 assert done['rows_sha256']==audited['rows_sha256']==sha(rows_path) and audited['native_job_id']==closed['native_job_id']==actual['native_job_id']
 rows=[json.loads(line)for line in rows_path.read_text().splitlines()];declared={x['trial_name']:x for x in plan['trials']};configs={x['trial_name']:x for x in actual['trials']}
 assert len(rows)==len(declared)==len(configs)==267 and len({r['trial_id']for r in rows})==267 and {r['trial_name']for r in rows}==set(declared)==set(configs)
 assert len({x['task_id']for x in plan['trials']})==89 and all(sum(x['task_id']==task for x in plan['trials'])==3 for task in {x['task_id']for x in plan['trials']})
 for row in rows:
  cfg=configs[row['trial_name']];item=declared[row['trial_name']];p=Path(cfg['trials_dir'])/cfg['trial_name']/'result.json'
  assert p.exists()and sha(p)==row['result_sha256'] and read(p)['id']==row['trial_id']
  assert row['task_id']==item['task_id']==Path(cfg['task']['path']).name and row['repetition']==item['repetition']
 unit=props(binding['job_unit'])
 if unit['ActiveState']in['active','activating','deactivating']:return dict(passed=False,reason='WAIT_SELECTED267_WORKER_CLOSED',unit=unit,formal801_required=False)
 for name in ['new-m1-cf416-128k-e5','new-m2-tmax356-128k-e5']:assert read(R/'runs'/name/'FINAL_HF_ADMISSION.json')['passed']
 return dict(passed=True,actual_terminal=267,actual_native_job_id=actual['native_job_id'],comparison_sha256=sha(comparison),rows_sha256=sha(rows_path),actual_mapping_sha256=sha(actual_path),plan_sha256=sha(plan_path),binding_sha256=sha(binding_path),formal801_required=False,unknowns_remain_explicit=True)

def freeze_equal(path,value):
 if path.exists():
  expected=hashlib.sha256((json.dumps(value,indent=2)+'\n').encode()).hexdigest()
  assert read(path)==value and sha(path)==expected,'Frozen evidence identity/SHA changed: '+str(path)
 else:save(path,value)
 return path

def proc_identity(pid):
 p=Path('/proc')/str(pid)
 try:return dict(pid=pid,start_ticks=(p/'stat').read_text().rsplit(')',1)[1].split()[19],cgroup=(p/'cgroup').read_text())
 except FileNotFoundError:return None

def gpu_state(index):
 uuid=subprocess.check_output(['nvidia-smi','-i',str(index),'--query-gpu=uuid','--format=csv,noheader'],text=True,timeout=10).strip()
 pids=[int(x)for x in subprocess.check_output(['nvidia-smi','-i',str(index),'--query-compute-apps=pid','--format=csv,noheader,nounits'],text=True,timeout=10).split()]
 return uuid,pids

def stop_intent_closed(intent):
 unit=props(intent['unit']);assert unit['ActiveState']in['inactive','failed']and int(unit['MainPID'])==0,'Original service closure is not confirmed'
 original=intent['main_process'];current=proc_identity(original['pid']);assert current is None or current['start_ticks']!=original['start_ticks'],'Original main PID identity is still alive'
 for owned in intent['gpu_processes']:
  live=proc_identity(owned['pid']);assert live is None or live['start_ticks']!=owned['start_ticks'],'Original GPU process identity is still alive'
 uuid,pids=gpu_state(intent['gpu_index']);assert uuid==intent['gpu_uuid'];observed=[]
 for pid in pids:
  live=proc_identity(pid)
  if live is None:continue
  assert live['cgroup']and live['cgroup']!=original['cgroup']and('/'+intent['unit'])not in live['cgroup'],'Original unit still owns a GPU process'
  assert not any(live['pid']==old['pid']and live['start_ticks']==old['start_ticks']for old in intent['gpu_processes'])
  observed.append(live)
 return dict(unit=unit,original_main_and_gpu_pid_identities_closed=True,current_gpu_processes=observed,other_gpu_owners_preserved=True)

def release_idle_selected(binding,gate):
 marker=R/'checks/SELECTED267_IDLE_SGL_SERVICES_RELEASED_R1.json'
 if marker.exists():
  frozen=read(marker);assert frozen['selected267_gate']==gate and frozen['all_project_cli_leases_closed'];return marker
 leases=handoff.leases();assert leases['complete']and not leases['active_cli_leases'],'Preserve active or unknown project CLI leases'
 directory=R/'checks/selected267-old-four-release-r1';directory.mkdir(exist_ok=True);released=[]
 for replica in binding['replicas']:
  unit=replica['unit'];saved=directory/('gpu'+str(replica['gpu_index'])+'.json');intent_path=directory/('gpu'+str(replica['gpu_index'])+'-stop-intent.json')
  if saved.exists():
   row=read(saved);assert row['unit']==unit and row['gpu_uuid']==replica['gpu_uuid']and row['stop_intent_sha256']==sha(intent_path)
   assert props(unit)['ActiveState']not in['active','activating','deactivating'];released.append(row);continue
  if not intent_path.exists():
   live=props(unit);assert live['ActiveState']=='active';pid=int(live['MainPID']);original=proc_identity(pid);assert original and original['cgroup']and('/'+unit)in original['cgroup']
   uuid,pids=gpu_state(replica['gpu_index']);assert uuid==replica['gpu_uuid']and pids and all(pid in handoff.ancestors(p)for p in pids),'Preserve another GPU owner'
   processes=[proc_identity(p)for p in pids];assert all(processes),'GPU process changed while admitting a stop'
   info=handoff.get(replica['port'],'/model_info');assert info['model_path']==binding['model_path']and info['weight_version']==binding['weight_version']
   load=handoff.get(replica['port'],'/get_load');assert load and all(x['num_reqs']==x['num_waiting_reqs']==0 for x in load)
   current=handoff.leases();assert current['complete']and not current['active_cli_leases']
   assert props(unit)['MainPID']==str(pid)and proc_identity(pid)==original
   freeze_equal(intent_path,dict(at=time.time(),gpu_index=replica['gpu_index'],gpu_uuid=uuid,unit=unit,main_process=original,gpu_processes=processes,model_path=binding['model_path'],weight_version=binding['weight_version'],port=replica['port'],model_info=info,load=load,cli_lease_evidence=current,selected267_gate=gate))
  intent=read(intent_path);assert intent['unit']==unit and intent['gpu_uuid']==replica['gpu_uuid']and intent['gpu_index']==replica['gpu_index']and intent['model_path']==binding['model_path']and intent['weight_version']==binding['weight_version']and intent['selected267_gate']==gate
  live=props(unit)
  if live['ActiveState']=='active':
   assert int(live['MainPID'])==intent['main_process']['pid']and proc_identity(int(live['MainPID']))==intent['main_process'],'A different service process replaced the frozen stop owner'
   uuid,pids=gpu_state(replica['gpu_index']);assert uuid==intent['gpu_uuid']and pids and all(intent['main_process']['pid']in handoff.ancestors(p)for p in pids)
   assert all(any(proc_identity(p)==old for old in intent['gpu_processes'])for p in pids),'GPU ownership changed after the stop intent'
   info=handoff.get(replica['port'],'/model_info');assert info['model_path']==intent['model_path']and info['weight_version']==intent['weight_version']
   load=handoff.get(replica['port'],'/get_load');assert load and all(x['num_reqs']==x['num_waiting_reqs']==0 for x in load)
   current=handoff.leases();assert current['complete']and not current['active_cli_leases']
   subprocess.run(['systemctl','--user','stop',unit],check=True,timeout=60)
  closed=stop_intent_closed(intent)
  row=dict(at=time.time(),gpu_index=replica['gpu_index'],gpu_uuid=replica['gpu_uuid'],unit=unit,stop_intent_path=str(intent_path),stop_intent_sha256=sha(intent_path),closure=closed,actual_selected267_terminal=267)
  freeze_equal(saved,row);released.append(row)
 freeze_equal(marker,dict(released=released,selected267_gate=gate,only_owned_idle_services_stopped=True,all_project_cli_leases_closed=True));return marker

def advance(owner,state):
 assert read(C/'NATIVE_ADVANCE_OWNER.json')==owner
 gate=selected267_gate();state['old_four_after_selected267_gate']=gate
 if not gate['passed']:state['old_four']=dict(status=gate['reason']);return
 if(P/'checks/FOUR_NATIVE_TRAINING_RUNS_COMPLETED').exists():state.update(status='OLD_FOUR_NATIVE_TRAINING_COMPLETE_READOUT_PENDING');return
 unit='qwen35-old-four-native18-after-selected267-r3.service';actual=props(unit);admission=C/'OLD_FOUR_AFTER_SELECTED267_ADMISSION_R1.json'
 if actual['ActiveState']in['active','activating']:
  state.update(status='OLD_FOUR_NATIVE_RESEARCH_RUNNING',old_four=dict(unit=actual));return
 if admission.exists()or actual['LoadState']!='not-found':state.update(status='OLD_FOUR_NATIVE_WORKER_REQUIRES_INSPECTION',old_four=dict(unit=actual,no_redispatch_from_unit_gc=True));return
 leases=handoff.leases()
 if not leases['complete']or leases['active_cli_leases']:state.update(status='WAIT_SELECTED267_PROJECT_CLI_LEASES_CLOSED',old_four=dict(cli_lease_evidence=leases));return
 manifest,plans=worker.recipe_and_resume()
 gate_path=R/'checks/OLD_FOUR_SELECTED267_GATE_R1.json';freeze_equal(gate_path,gate)
 release=release_idle_selected(read(R/'checks/SELECTED267_MODEL_BINDING_R1.json'),gate)
 history=[dict(path=str(p),sha256=sha(p))for p in [C/'OLD_FOUR_SAFE_DEFERRAL.json',C/'OLD_FOUR_DEFERRED_USER_PRIORITY_20261101.json']if p.exists()]
 receipt=dict(at=time.time(),unique_controller_owner=owner,source_sha256=sha(R/'resume-old-four-native18-r3.py'),source_manifest_sha256=sha(P/'manifests/experiments.json'),actual_selected267_terminal=267,all_project_cli_leases_closed=True,selected267_gate=dict(path=str(gate_path),sha256=sha(gate_path)),sgl_release=dict(path=str(release),sha256=sha(release)),resume_plans=plans,formal801_required=False,historical_deferral_records_preserved=history,applicable_resume_authorization='latest user selected267 -> old four',acceptance_stop_after_checkpoint_2=False,original_five_epoch_scheduler_preserved=True)
 save(admission,receipt)
 # Original native resource envelope and training entry; this leaf starts no alternate scheduler.
 subprocess.run(['systemd-run','--user','--unit='+unit,'--property=MemoryMax=192G','--property=StandardOutput=append:'+str(R/'logs/old-four-native-r3.log'),'--property=StandardError=append:'+str(R/'logs/old-four-native-r3.log'),str(R/'env/train-r1/bin/python'),str(R/'resume-old-four-native18-r3.py')],check=True,capture_output=True,text=True,timeout=15)
 state.update(status='OLD_FOUR_NATIVE_CHECKPOINT_RESUME_SUBMITTED',old_four=dict(plans=plans,unit=props(unit)))
if __name__=='__main__':raise SystemExit('Only existing unique advance may invoke this phase')
