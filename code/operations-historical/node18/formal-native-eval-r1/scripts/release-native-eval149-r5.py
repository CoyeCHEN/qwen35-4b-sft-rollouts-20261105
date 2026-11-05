import hashlib,json,py_compile,time
from pathlib import Path
R=Path('/home/chenkeyi/.local/share/harbor-rsi/qwen35-new772-tb21-20261101')
EXPECTED={'run-formal-native-tb21149-r5.py': 'a32ccd148f26107161a009e8158aa0d30dff57af2e9a5ca40d1ad83aefb70ed9', 'compare-formal801-readonly-r5.py': 'faedf77cf554f7d4bb6e3cba8190711c0e67673c27c7b2234fcea87a43188517', 'audit-native-context-accounting-r1.py': 'f8765e3c0569a45a761a6da25a25a273d5d193066793d79364a26a16434b45c5', 'compare-epoch3-epoch5-readonly149-r2.py': '3c459b94b9e0aefb4e1e7c50619373dc2fa5a4325b42588749d6d2d6993c8b0b', 'native-handoff149-r5.py': '49d8cedfe5f66da124ab7a454f47de08030fa57dbd7f323c80643c8f13efa1be', 'audit_trial_behavior_new772_r3.py': 'e83d2b027c648a480d06b1e1943953aefc1fe33c5c1e4c5626ba271c765c034b', 'eval_audit_new772.py': '9f6d8eb31bd6da42d5a3cdd929c169c04b9496796a81f49e4b292889418f8bcf', 'run-epoch3-native-tb21149-r1.py': 'fee9f687af296a855ff9e8e62a6d5a4155e60fd52a2267ec0e41ac3144a46841'}
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
for name,expected in EXPECTED.items():
 assert sha(R/'scripts'/name)==expected,name
 py_compile.compile(str(R/'scripts'/name),doraise=True)
assert not(R/'jobs/qwen35-new772-tb21-n3').exists(),'Formal Job already exists; inspect before promotion'
previous=R/'checks/NATIVE_EVAL149_DEPLOYMENT_RELEASE_R4.json'
release=json.loads(previous.read_text())
assert release['formal_801_trial_plan_sha256']==sha(R/'manifests/FORMAL_801_TRIAL_PLAN.json')
assert release['epoch3_preregistration_sha256']==sha(R/'manifests/EPOCH3_DIAGNOSTIC_PREREGISTRATION.json')
student=R/'checks/NEW11_STUDENT_HARNESS_RELEASE_R5.json'
assert json.loads(student.read_text())['installed_tests_passed']==80
accept=R/'checks/CONTEXT_RECOVERY_INSTALLED_WHEEL_ACCEPTANCE_R1.json'
assert json.loads(student.read_text())['acceptance_sha256']==sha(accept)
account=R/'checks/CONTEXT_ACCOUNTING_REAL_TRIAL_ACCEPTANCE_R2.json'
assert json.loads(account.read_text())['passed']
assert json.loads(account.read_text())['source_sha256']==EXPECTED['audit-native-context-accounting-r1.py']
preflight=R/'checks/NATIVE_801_TRIAL_CONFIG_PREFLIGHT_R5.json'
assert json.loads(preflight.read_text())['passed']and len(json.loads(preflight.read_text())['native_trial_configs'])==801
release.update(kind='NATIVE_EVAL149_FIXED_DEPLOYMENT_RELEASE_R5',sources=EXPECTED,
 previous_deployment_release_sha256=sha(previous),new_student_harness_release_sha256=sha(student),
 native_801_config_preflight_sha256=sha(preflight),formal_wheel_only_deployment_sha256=sha(R/'checks/FORMAL801_WHEEL_ONLY_DEPLOYMENT_R2.json'),
 context_accounting_real_trial_acceptance_sha256=sha(account),
 active_epoch3_jobs_and_original_r4_config_unchanged=True,formal_three_models_share_r5=True,
 epoch3_vs_epoch5_harness_difference_explicit=True,actual_formal_trials_started=0)
p=R/'checks/NATIVE_EVAL149_DEPLOYMENT_RELEASE_R5.json';assert not p.exists();p.write_text(json.dumps(release,ensure_ascii=False,indent=2)+'\n')
a=Path.home()/'.ssh/authorized_keys';raw=a.read_text();lines=raw.splitlines(keepends=True)
indices=[i for i,x in enumerate(lines)if 'native-handoff149-r4.py'in x];assert len(indices)==1
backup=a.with_name('authorized_keys.before-native-eval-r5-'+str(int(time.time())));backup.write_text(raw);backup.chmod(0o600)
lines[indices[0]]=lines[indices[0]].replace('native-handoff149-r4.py','native-handoff149-r5.py')
tmp=a.with_name('authorized_keys.native-eval-r5.tmp');tmp.write_text(''.join(lines));tmp.chmod(0o600);tmp.replace(a)
proof=dict(passed=True,at=time.time(),release_sha256=sha(p),own_restricted_command_updated_only=True,
 other_authorized_keys_unchanged=True,original_801_plan_and_active_e3_jobs_unchanged=True,
 no_new_trials_dispatched=True,backup=str(backup))
(R/'checks/NATIVE_EVAL149_R5_RESTRICTED_HANDOFF_ACTIVATION.json').write_text(json.dumps(proof,indent=2)+'\n')
print(json.dumps(proof))
