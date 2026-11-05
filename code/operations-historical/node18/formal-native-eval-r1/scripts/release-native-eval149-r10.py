"""Select lineage-aware readout for the not-yet-started native formal801 Job."""
import hashlib,json,subprocess,time
from pathlib import Path
R=Path('/home/chenkeyi/.local/share/harbor-rsi/qwen35-new772-tb21-20261101')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_text())
def props(unit):return dict(x.split('=',1)for x in subprocess.check_output(['systemctl','--user','show',unit,'-p','MainPID','-p','ActiveState'],text=True).splitlines())
def main():
 previous=R/'checks/NATIVE_EVAL149_DEPLOYMENT_RELEASE_R9.json'
 assert sha(previous)=='17805b042654b1ffb803c9a2c7936a5e0caff08ccf7b95c015e00883af351359'
 old=read(previous)
 for name,digest in old['sources'].items():assert sha(R/'scripts'/name)==digest,name
 proof=R/'checks/FORMAL801_E3_LINEAGE_ACCEPTANCE_R1.json';p=read(proof)
 assert p['passed']and p['actual_801_native_configs_equal_previous']and p['actual_trials_started']==0 and p['actual_model_calls']==0
 assert p['new_native_runner_sha256']==sha(R/'scripts/run-formal-native-tb21149-r9.py')
 assert p['e3_lineage_reader_sha256']==sha(R/'scripts/compare-epoch3-epoch5-readonly149-r6.py')
 assert not(R/'jobs/qwen35-new772-tb21-n3').exists()
 assert not(R/'manifests/THREE_MODEL_COLD_SERVING_ADMISSION.json').exists()
 unit='qwen35-new772-new-m1-e3-original-five-20261102-r1';before=props(unit);assert before['MainPID']=='326945'and before['ActiveState']=='active'
 originals=R/'jobs/qwen35-new772-new-m1-epoch3-fixed-diagnostic'
 original_hashes={str(x.relative_to(R)):sha(x)for x in originals.glob('*/result.json')}
 assert len(original_hashes)==2
 extras={name:sha(R/'scripts'/name)for name in ['native-handoff149-r10.py','run-formal-native-tb21149-r9.py','compare-epoch3-epoch5-readonly149-r6.py']}
 value=dict(old,kind='NATIVE_EVAL149_FIXED_DEPLOYMENT_RELEASE_R10',sources=dict(old['sources'],**extras),
  previous_deployment_release_sha256=sha(previous),formal_e3_lineage_acceptance_sha256=sha(proof),
  formal_qualification_and_e3_e5_readers=['compare-formal801-readonly-r7.py','compare-epoch3-epoch5-readonly149-r6.py'],
  actual_formal_trials_started=0,controller_memory_max_bytes=16*1024**3,
  e3_missing_native_results_explicit_unknown_not_invented=True,
  previous_release_active_native_e3_unit_snapshot=old.get('active_native_e3_unit_preserved'),
  active_native_e3_unit_preserved=before,existing_original_result_sha256=original_hashes,
  actual_801_configs_unchanged=True,release_source_sha256=sha(Path(__file__)))
 out=R/'checks/NATIVE_EVAL149_DEPLOYMENT_RELEASE_R10.json';assert not out.exists();out.write_text(json.dumps(value,indent=2)+'\n')
 authorized=Path.home()/'.ssh/authorized_keys';raw=authorized.read_text();lines=raw.splitlines(keepends=True)
 selected=[i for i,line in enumerate(lines)if 'native-handoff149-r9.py'in line];assert len(selected)==1
 backup=authorized.with_name('authorized_keys.before-native-handoff-r10-'+str(int(time.time())));backup.write_text(raw);backup.chmod(0o600)
 lines[selected[0]]=lines[selected[0]].replace('native-handoff149-r9.py','native-handoff149-r10.py')
 temp=authorized.with_name('authorized_keys.native-handoff-r10.tmp');temp.write_text(''.join(lines));temp.chmod(0o600);temp.replace(authorized)
 assert props(unit)==before
 for name,digest in original_hashes.items():assert sha(R/name)==digest
 activation=dict(passed=True,at=time.time(),release_sha256=sha(out),formal_model_calls_or_trial_dispatches=0,
  preserved_native_e3_unit=before,original_results_unchanged=True,formal_actual801_configs_unchanged=True,
  lineage_reader_sha256=p['e3_lineage_reader_sha256'])
 path=R/'checks/NATIVE_EVAL149_R10_ACTIVATION.json';assert not path.exists();path.write_text(json.dumps(activation,indent=2)+'\n');print(json.dumps(activation))
if __name__=='__main__':main()
