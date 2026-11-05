"""Fixture-only checks of the bounded original-unstarted continuation."""
import hashlib,importlib,json,tempfile,time
from pathlib import Path
from unittest.mock import patch
R=Path('/ssd/chenkeyi/qwen35-sft-772-20261101')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 phase=importlib.import_module('phase_progression18_r9')
 old=(R/'run-native772-advance-r11.py').read_text()
 assert old.replace('import phase_progression18_r8 as phases','import phase_progression18_r9 as phases').replace("deployment_revision='r11-native-m2-formal-response-qualification-before-old4-old112'","deployment_revision='r12-native-e3-original-unstarted-oom-safe-continuation'")==(R/'run-native772-advance-r12.py').read_text()
 assert (R/'read-only-monitor18-r17.py').read_text().replace('OBSERVATION_V17','OBSERVATION_V18').replace('node18-20261101-r11.service','node18-20261101-r12.service')==(R/'read-only-monitor18-r18.py').read_text()
 failure=json.loads((R/'checks/E3_NATIVE_CONTROLLER_OOM_SNAPSHOT_R1.json').read_text())
 release=json.loads((R/'checks/NATIVE_EVAL149_DEPLOYMENT_RELEASE_R9.json').read_text())
 assert release['campaign_controller_memory_max_bytes']==16*1024**3
 cases=[]
 for name,active,complete,chess_closed,requested,expected in [
  ('original_five_only_submitted',False,False,False,False,'submit'),
  ('active_continuation_adopted',True,False,False,True,'observe'),
  ('terminal_five_waits_for_existing_chess',False,True,False,True,'wait'),
  ('terminal_five_and_both_orphans_close_server',False,True,True,True,'closed'),
  ('failed_started_continuation_not_retried',False,False,False,True,'inspect')]:
  calls=[];state={}
  item=dict(original_oom_snapshot_sha256=sha(R/'checks/E3_NATIVE_CONTROLLER_OOM_SNAPSHOT_R1.json'),
   complete=dict(terminal=5,original_started_trials_rerun=0)if complete else None,
   systemd='ActiveState='+('active'if active else'inactive'),
   original_orphans={t:dict(terminal_evidence_exists=v)for t,v in [('regex-log',True),('chess-best-move',chess_closed)]})
  with tempfile.TemporaryDirectory(prefix='native-r12-fixture-',dir=R/'tmp')as temporary:
   c=Path(temporary);(c/'native-phase-requests').mkdir()
   if requested:(c/'native-phase-requests/new-m1-epoch3-unstarted.json').write_text('{}')
   with patch.object(phase,'C',c),patch.object(phase.serving,'stop',side_effect=lambda tag:calls.append(('stop',tag))),patch.object(phase.serving,'info',return_value=dict(model_path='fixture',weight_version='fixture',model_manifest='fixture')),patch.object(phase,'request',side_effect=lambda mode,payload,owner:calls.append(('request',mode,payload))):
    finished=phase.continue_original_e3({},state,dict(modes={'new-m1-epoch3-unstarted':item}),release)
   assert finished==(expected=='closed')
   if expected=='submit':
    assert len(calls)==1 and calls[0][0]=='request'
    payload=calls[0][2];assert payload['original_unstarted_tasks']==failure['unstarted_tasks_in_original_preregistered_order']
    assert payload['original_started_trials_rerun']==0 and payload['new_native_concurrency']==1
   elif expected=='closed':
    assert calls==[('stop','new-m1-epoch3-fixed')]
    marker=json.loads((c/'EPOCH3_FIXED_SERVER_CLOSED_new-m1.json').read_text())
    assert marker['native_results']==7 and marker['original_controller_interrupted_unknown']==2 and marker['denominator']==9
   else:assert calls==[]
  cases.append(dict(case=name,passed=True))
 proof=dict(passed=True,at=time.time(),cases=cases,actual_trials_started=0,actual_model_calls=0,
  new_sources_sha256={n:sha(R/n)for n in ['phase_progression18_r9.py','run-native772-advance-r12.py','read-only-monitor18-r18.py']},
  source_sha256=sha(Path(__file__)),original_training_entry_only_phase_import_and_deployment_identity_changed=True,
  original_attempts_not_rerun=True,original_results_not_fabricated=True,
  native149_release_sha256=sha(R/'checks/NATIVE_EVAL149_DEPLOYMENT_RELEASE_R9.json'))
 path=R/'checks/CONTROL_R12_CPU_SOURCE_ACCEPTANCE_R1.json';assert not path.exists();path.write_text(json.dumps(proof,indent=2)+'\n');print(json.dumps(proof))
if __name__=='__main__':main()
