import hashlib,json,py_compile,time
from pathlib import Path
R=Path('/home/chenkeyi/.local/share/harbor-rsi/qwen35-new772-tb21-20261101')
EXPECTED={'run-formal-native-tb21149-r7.py': '686d61a84fb6435b5ec7bbadd4c2e38c77be02c8c52eaeee08434b044c736b6f', 'compare-formal801-readonly-r6.py': '1c78568c9f094ea706b84c86ae2d42ebd026f2069f38eeec9a5fdc36dfb28e36', 'audit-native-context-accounting-r2.py': '5ba9d41b9aa7d59c9934c27a8b9b56a88954db72e848544031122c3cc324d082', 'compare-epoch3-epoch5-readonly149-r4.py': 'e13e141f3e28d5c5be9aabdc70772693d6473cb2386ce6c1d1018d3c3ca0b495', 'native-handoff149-r7.py': 'ecd57358ddf5b09425bf715da3b75590c2182ef39237e606f0d0e6d40908c8bd', 'audit_trial_behavior_new772_r3.py': 'e83d2b027c648a480d06b1e1943953aefc1fe33c5c1e4c5626ba271c765c034b', 'eval_audit_new772.py': '9f6d8eb31bd6da42d5a3cdd929c169c04b9496796a81f49e4b292889418f8bcf', 'run-epoch3-native-tb21149-r1.py': 'fee9f687af296a855ff9e8e62a6d5a4155e60fd52a2267ec0e41ac3144a46841', 'run-fixed-epoch3-native-tb21149-r1.py': '2874c5f759079aa62edcab7cc3f2726edd739e89f0a950fbf95cc5f94e6b63a5', 'run-new11-install-preflight149-r1.py': '4e2773afaf97f891572b183f415996d40afd0781ffaeb8685402a13a29d9d8f6'}
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
for name,expected in EXPECTED.items():
 assert sha(R/'scripts'/name)==expected,name
 py_compile.compile(str(R/'scripts'/name),doraise=True)
assert not(R/'jobs/qwen35-new772-tb21-n3').exists(),'Formal Job already exists; inspect before promotion'
previous=R/'checks/NATIVE_EVAL149_DEPLOYMENT_RELEASE_R6.json'
release=json.loads(previous.read_text())
assert release['formal_801_trial_plan_sha256']==sha(R/'manifests/FORMAL_801_TRIAL_PLAN.json')
assert release['epoch3_preregistration_sha256']==sha(R/'manifests/EPOCH3_DIAGNOSTIC_PREREGISTRATION.json')
student=R/'checks/NEW11_STUDENT_HARNESS_RELEASE_R5.json'
assert json.loads(student.read_text())['installed_tests_passed']==80
accept=R/'checks/CONTEXT_RECOVERY_INSTALLED_WHEEL_ACCEPTANCE_R1.json'
assert json.loads(student.read_text())['acceptance_sha256']==sha(accept)
account=R/'checks/CONTEXT_ACCOUNTING_REAL_TRIAL_ACCEPTANCE_R3.json'
assert json.loads(account.read_text())['passed']
assert json.loads(account.read_text())['source_sha256']==EXPECTED['audit-native-context-accounting-r2.py']
preflight=R/'checks/NATIVE_801_TRIAL_CONFIG_PREFLIGHT_R7.json'
assert json.loads(preflight.read_text())['passed']and len(json.loads(preflight.read_text())['native_trial_configs'])==801
release.update(kind='NATIVE_EVAL149_FIXED_DEPLOYMENT_RELEASE_R7',sources=EXPECTED,
 previous_deployment_release_sha256=sha(previous),new_student_harness_release_sha256=sha(student),
 native_801_config_preflight_sha256=sha(preflight),formal_wheel_only_deployment_sha256=sha(R/'checks/FORMAL801_WHEEL_ONLY_DEPLOYMENT_R2.json'),
 context_accounting_real_trial_acceptance_sha256=sha(account),
 canonical_task_identity_uses_frozen_paths_and_public_sha=True,raw_task_names_preserved=True,
 active_epoch3_jobs_and_original_r4_config_unchanged=True,formal_three_models_share_r5=True,
 epoch3_vs_epoch5_harness_difference_explicit=True,actual_formal_trials_started=0)
e2e=R/'checks/CONTEXT_RECOVERY_FULL_WHEEL_E2E_ACCEPTANCE_R1.json'
assert json.loads(e2e.read_text())['passed']and len(json.loads(e2e.read_text())['cases'])==6
deps=R/'checks/AGENT_PUBLIC_DEPENDENCY_DEPLOYMENT_R1.json'
dep=json.loads(deps.read_text());assert sha(R/'configs/environment-profiles-agent-deps-r2.json')==dep['new_profiles_sha256']
assert sha(R/'configs/agent-deps-r1.compose.json')==dep['compose_sha256']
assert sha(R/'configs/agent-deps/rg')==dep['rg_sha256']
plan=R/'manifests/REPAIRED_EPOCH3_18_TRIAL_PLAN_R1.json';assert len(json.loads(plan.read_text())['trials'])==18
release.update(full_installed_cli_e2e_acceptance_sha256=sha(e2e),
 environment_profiles_sha256=dep['new_profiles_sha256'],original_environment_profiles_sha256=dep['original_profiles_sha256'],
 public_cli_dependency_deployment_sha256=sha(deps),repaired_epoch3_plan_sha256=sha(plan),
 historical_epoch3_r4_diagnostics_excluded_from_comparable_results=True,
 repaired_epoch3_and_epoch5_use_identical_wheel=True,install_only89_readiness_gate_required=True,
 actual_formal_trials_started=0,actual_repaired_epoch3_trials_started=0)
p=R/'checks/NATIVE_EVAL149_DEPLOYMENT_RELEASE_R7.json';assert not p.exists();p.write_text(json.dumps(release,ensure_ascii=False,indent=2)+'\n')
a=Path.home()/'.ssh/authorized_keys';raw=a.read_text();lines=raw.splitlines(keepends=True)
indices=[i for i,x in enumerate(lines)if 'native-handoff149-r6.py'in x];assert len(indices)==1
backup=a.with_name('authorized_keys.before-native-eval-r7-'+str(int(time.time())));backup.write_text(raw);backup.chmod(0o600)
lines[indices[0]]=lines[indices[0]].replace('native-handoff149-r6.py','native-handoff149-r7.py')
tmp=a.with_name('authorized_keys.native-eval-r7.tmp');tmp.write_text(''.join(lines));tmp.chmod(0o600);tmp.replace(a)
proof=dict(passed=True,at=time.time(),release_sha256=sha(p),own_restricted_command_updated_only=True,
 other_authorized_keys_unchanged=True,original_801_plan_and_active_e3_jobs_unchanged=True,
 no_new_trials_dispatched=True,backup=str(backup))
(R/'checks/NATIVE_EVAL149_R7_RESTRICTED_HANDOFF_ACTIVATION.json').write_text(json.dumps(proof,indent=2)+'\n')
print(json.dumps(proof))
