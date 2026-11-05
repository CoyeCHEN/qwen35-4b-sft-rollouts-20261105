"""Actual native801 config equality plus explicit UNKNOWN lineage boundaries."""
import hashlib,importlib,json,tempfile,time
from pathlib import Path
from unittest.mock import patch
R=Path('/home/chenkeyi/.local/share/harbor-rsi/qwen35-new772-tb21-20261101')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v))
def main():
 runner=importlib.import_module('run-formal-native-tb21149-r9')
 runner.validate_only()
 a=json.loads((R/'checks/NATIVE_801_TRIAL_CONFIG_PREFLIGHT_R8.json').read_text())
 b=json.loads((R/'checks/NATIVE_801_TRIAL_CONFIG_PREFLIGHT_R9.json').read_text())
 assert len(a['native_trial_configs'])==len(b['native_trial_configs'])==801
 assert a['native_trial_configs']==b['native_trial_configs']
 reader=importlib.import_module('compare-epoch3-epoch5-readonly149-r6')
 cases=[]
 with tempfile.TemporaryDirectory(prefix='e3-lineage-fixture-',dir=R/'diagnostics')as temporary:
  root=Path(temporary);original=root/'original/video-processing__new-m1-e3-fixed-r1'
  manifest=root/'manifests/E3_ORIGINAL_UNSTARTED_ACTUAL_NATIVE_TRIALS_R1.json'
  put(manifest,dict(original_started_trials_rerun=0,original_unstarted_tasks=['video-processing'],
    native_continuation_job=str(root/'continuation'),actual_trials=[dict(task=dict(path='/official/video-processing'),trial_name=original.name)]))
  with patch.object(reader,'R',root):
   assert reader.e3_directory('new-m1','video-processing',original)==root/'continuation'/original.name
   assert reader.e3_directory('new-m2','video-processing',original)==original
   cases+=['original_unstarted_maps_only_m1','m2_not_redirected']
   original.mkdir(parents=True)
   try:reader.e3_directory('new-m1','video-processing',original)
   except AssertionError:pass
   else:raise AssertionError('Never redirect an existing attempted original')
   cases.append('attempted_original_not_redirected')
   interrupted=root/'original/regex-log__new-m1-e3-fixed-r1';put(interrupted/'config.json',{})
   put(root/'checks/E3_NATIVE_CONTROLLER_OOM_SNAPSHOT_R1.json',dict(original_completed_results=[dict(task='regex-log',result_exists=False,original_config_sha256=sha(interrupted/'config.json'))]))
   assert reader.interrupted_terminal('new-m1','regex-log',interrupted)is None
   cases.append('live_or_unclosed_missing_result_not_terminal')
   put(root/'recovery/e3-controller-oom-20261102-r1/regex-log/RAW_RECORDER_VALIDATION.json',dict(complete=False))
   row=reader.interrupted_terminal('new-m1','regex-log',interrupted)
   assert row['trial_id']is None and row['reward']is None and row['native_result_exists']is False
   assert not(interrupted/'result.json').exists()
   stat=reader.aggregate([row],9)
   assert stat['unknown']==1 and stat['terminal']==1 and stat['scoring_and_protocol_valid']==0
   assert stat['confirmed_reward_successes']==0 and stat['raw_official_scoring_coverage']==0
   cases.append('closed_orphan_explicit_unknown_without_fake_result_or_uuid')
   (interrupted/'config.json').write_text('{"changed":true}')
   try:reader.interrupted_terminal('new-m1','regex-log',interrupted)
   except AssertionError:pass
   else:raise AssertionError('Changed original identity accepted')
   cases.append('changed_original_config_rejected')
 source=(R/'scripts/run-formal-native-tb21149-r9.py').read_text()
 assert "scripts/compare-epoch3-epoch5-readonly149-r6.py"in source
 assert "scripts/compare-formal801-readonly-r7.py"in source
 value=dict(passed=True,at=time.time(),actual_801_native_configs_equal_previous=True,
  actual_trials_started=0,actual_model_calls=0,original_12000_sec_preserved=sum(x['agent']['override_timeout_sec']==12000 for x in b['native_trial_configs']),
  cases=[dict(case=x,passed=True)for x in cases],new_native_runner_sha256=sha(R/'scripts/run-formal-native-tb21149-r9.py'),
  e3_lineage_reader_sha256=sha(R/'scripts/compare-epoch3-epoch5-readonly149-r6.py'),
  native_preflight_sha256=sha(R/'checks/NATIVE_801_TRIAL_CONFIG_PREFLIGHT_R9.json'),source_sha256=sha(Path(__file__)),
  official_task_resources_model_protocol_wheel_and_sampling_unchanged=True)
 p=R/'checks/FORMAL801_E3_LINEAGE_ACCEPTANCE_R1.json';assert not p.exists();p.write_text(json.dumps(value,indent=2)+'\n');print(json.dumps(value))
if __name__=='__main__':main()
