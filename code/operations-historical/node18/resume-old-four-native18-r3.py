"""Original fixed native A/B/C/D loop, admitted after selected267 and owned SGL release."""
import argparse,fcntl,hashlib,json,os,subprocess,sys,time
from pathlib import Path
import yaml
R=Path('/ssd/chenkeyi/qwen35-sft-772-20261101');P=R/'old-four-arm';E=R/'formal-native-eval-r1';C=Path('/data/chenkeyi/qwen35-sft-772-20261101/control');PY=R/'env/train-r1/bin/python'
EXPECTED_MANIFEST='3a3898e48726cb115ced481dd6a8f119c42af8506ee7f958185a7fae9ce3f481'
EXPECTED_A2_SHA_RECEIPT='fd1b95ad73602834017cd97bba70d7540e1b6b380e56625378a54fa85aaf430d'
def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def recipe_and_resume():
 mpath=P/'manifests/experiments.json';assert sha(mpath)==EXPECTED_MANIFEST;m=read(mpath)
 assert set(m['arms'])==set('ABCD') and m['supersedes_all_prior_five_arm_plans']
 for name,digest in m['study_source_sha256'].items():assert sha(P/'source/repository/studies/qwen35_m2_full_causal'/name)==digest
 assert (m['data_parallel'],m['microbatch'],m['gradient_accumulation'],m['global_batch'],m['scheduler_horizon'])==(4,1,4,16,530)
 configs={};plans=[]
 for arm,lr in [('A',2e-6),('B',2e-6),('C',1e-5),('D',5e-7)]:
  p=m['arms'][arm];cfgpath=Path(p['config']);assert sha(cfgpath)==p['config_sha256'];cfg=yaml.safe_load(cfgpath.read_text());configs[arm]=cfg
  assert cfg['learning_rate']==p['learning_rate']==lr and cfg['num_train_epochs']==p['epochs']==5 and p['optimizer_steps']==530
  assert cfg['max_steps']==-1 and cfg['lr_scheduler_type']=='cosine' and cfg['warmup_ratio']==0.03
  assert cfg['gradient_accumulation_steps']==4 and cfg['per_device_train_batch_size']==1 and cfg['seed']==cfg['data_seed']==42
  assert cfg['model_name_or_path']==m['initialization'] and cfg['model_revision']==m['model_revision'] and cfg['tokenized_path']==p['data_path']
  assert cfg['bf16'] and not cfg['pure_bf16'] and cfg['freeze_vision_tower'] and cfg['freeze_multi_modal_projector'] and not cfg['freeze_language_model']
  assert sha(Path(cfg['deepspeed']))==m['deepspeed_sha256']
  output=Path(p['output_dir']);completed=[]
  if output.exists():
   for cp in output.glob('checkpoint-*'):
    if not(cp/'CHECKPOINT_COMPLETE.json').exists():continue
    marker=read(cp/'CHECKPOINT_COMPLETE.json');state=read(cp/'trainer_state.json');step=state['global_step']
    assert state['max_steps']==530 and state['num_train_epochs']==5 and cp.name=='checkpoint-'+str(step)
    assert marker['identity']['config_sha256']==p['config_sha256']
    assert (cp/'latest').read_text().strip()=='global_step'+str(step)
    for item in marker['files']:
     f=cp/item['path'];assert f.is_file() and f.stat().st_size==item['bytes']
    for rank in range(4):
     assert(cp/f'rng_state_{rank}.pth').is_file()
     assert(cp/('global_step'+str(step))/f'zero_pp_rank_{rank}_mp_rank_00_model_states.pt').is_file()
     assert(cp/('global_step'+str(step))/f'bf16_zero_pp_rank_{rank}_mp_rank_00_optim_states.pt').is_file()
    for rank in range(4):
     resolved=[json.loads(line)for line in(output/f'resolved-rank{rank}.jsonl').read_text().splitlines()]
     for value in resolved:
      value.pop('resume_from_checkpoint',None);assert value==cfg
     events=[json.loads(line)for line in(output/f'preflight-evidence-rank{rank}.jsonl').read_text().splitlines()]
     begin=next(x for x in events if x['event']=='train_begin');parallel=begin['parallelism']
     assert(parallel['world_size'],parallel['data_parallel_group_size'],parallel['microbatch_per_gpu'],parallel['gradient_accumulation_steps'],parallel['effective_global_batch'])==(4,4,1,4,16)
     assert begin['training_source_sha256']==m['training_source_sha256'] and begin['identity']['config_sha256']==p['config_sha256']
    completed.append((step,cp))
   assert completed,'Existing output requires a complete native checkpoint; never reinitialize'
  step,resume=max(completed)if completed else(0,None)
  checkpoint_sha_receipt=None
  if arm=='A' and step==2:
   receipt=P/'checks/a2-full-sha-r1/COMPLETE.json';assert sha(receipt)==EXPECTED_A2_SHA_RECEIPT;hashed=read(receipt);assert hashed['status']=='COMPLETE' and hashed['checkpoint_path']==str(resume)
   assert hashed['checkpoint_marker_sha256']==sha(resume/'CHECKPOINT_COMPLETE.json')
   assert {x['path']for x in hashed['files']}=={x['path']for x in read(resume/'CHECKPOINT_COMPLETE.json')['files']}
   for item in hashed['files']:
    f=resume/item['path'];assert f.stat().st_size==item['bytes'] and f.stat().st_mtime_ns==item['mtime_ns'] and len(item['sha256'])==64
   checkpoint_sha_receipt=dict(path=str(receipt),sha256=sha(receipt))
  plans.append(dict(arm=arm,resume=str(resume)if resume else None,optimizer_step=step,config_sha256=p['config_sha256'],output_dir=str(output),checkpoint_sha_receipt=checkpoint_sha_receipt))
 a=configs['A']
 for arm,allowed in [('B',{'tokenized_path','output_dir'}),('C',{'learning_rate','output_dir'}),('D',{'learning_rate','output_dir'})]:
  assert {k for k in set(a)|set(configs[arm])if a.get(k)!=configs[arm].get(k)}==allowed
 return m,plans

def admitted():
 path=C/'OLD_FOUR_AFTER_SELECTED267_ADMISSION_R1.json'
 if not path.exists():return dict(admitted=False,reason='WAIT_SELECTED267_AUDIT_AND_IDLE_SGL_RELEASE',formal801_required=False)
 a=read(path);assert a['source_sha256']==sha(Path(__file__)) and a['unique_controller_owner']==read(C/'NATIVE_ADVANCE_OWNER.json')
 owner=a['unique_controller_owner'];assert(Path('/proc')/str(owner['pid'])/'stat').read_text().rsplit(')',1)[1].split()[19]==owner['start_ticks']
 for key in ['selected267_gate','sgl_release']:
  p=Path(a[key]['path']);assert sha(p)==a[key]['sha256']
 assert a['actual_selected267_terminal']==267 and a['all_project_cli_leases_closed'] and a['source_manifest_sha256']==sha(P/'manifests/experiments.json')
 return dict(admitted=True,formal801_required=False,source_order='NewM1 -> NewM2 -> selected267 -> old four',admission_sha256=sha(path))

def main(check_only):
 gate=admitted();m,plans=recipe_and_resume()
 if check_only:print(json.dumps(dict(**gate,plans=plans,manifest_sha256=sha(P/'manifests/experiments.json'))));return
 assert gate['admitted'];sys.path.insert(0,str(P/'source/repository'));os.environ['OPENHARNESS_SFT_WORKSPACE']=str(P)
 from sft.runtime.checkpoint_archive import validate_checkpoint
 env=os.environ|dict(PYTHONPATH=str(P/'source/repository'),OPENHARNESS_SFT_WORKSPACE=str(P),PATH=str(PY.parent)+':'+os.environ.get('PATH','/usr/bin:/bin'),OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',MKL_NUM_THREADS='1',HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',HF_DATASETS_OFFLINE='1',TOKENIZERS_PARALLELISM='false',TMPDIR=str(R/'tmp'),TRITON_CACHE_DIR=str(R/'cache/triton'),TORCH_EXTENSIONS_DIR=str(R/'cache/torch_extensions'),HF_HOME=str(R/'cache/hf'))
 with(C/'sequence-writer.lock').open('a')as writer:
  fcntl.flock(writer,fcntl.LOCK_EX|fcntl.LOCK_NB)
  for item in plans:
   arm=item['arm'];resume=item['resume'];step=item['optimizer_step']
   if resume:state=validate_checkpoint(Path(resume),world_size=4,require_marker=True);assert state['global_step']==step and state['max_steps']==530
   if step!=530:
    command=[str(PY),'-m','studies.qwen35_m2_full_causal.launch_arm','--evidence',str(P),'--arm',arm,'--gpu-uuids']+m['authorized_gpu_uuids'][:4]
    if resume:command+=['--resume',resume]
    with(P/'checks/native-resume-r3.jsonl').open('a')as log:log.write(json.dumps(dict(at=time.time(),arm=arm,resume=resume,command=command,original_scheduler_horizon=530,no_updates_replayed=True,acceptance_stop_after_checkpoint_2=False,ignore_data_skip=False))+'\n')
    subprocess.run(command,env=env,check=True)
   subprocess.run([str(PY),str(R/'verify-old-arm-native-r1.py'),arm,'530'],env=env,check=True)
  (P/'checks/FOUR_NATIVE_TRAINING_RUNS_COMPLETED').write_text(str(time.time())+'\n')
if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('--check-only',action='store_true');main(parser.parse_args().check_only)
