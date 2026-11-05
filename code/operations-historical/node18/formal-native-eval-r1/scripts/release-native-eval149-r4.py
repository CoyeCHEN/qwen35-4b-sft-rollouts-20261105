import hashlib,json,py_compile,time
from pathlib import Path
R=Path('/home/chenkeyi/.local/share/harbor-rsi/qwen35-new772-tb21-20261101')
O=R.parent/'qwen35-old-m2-four-arm-20261101'
EXPECTED={'run-formal-native-tb21149-r4.py': '4d7f4264240368ccbe3609c7ca48262e3f100e6c55576a30f16fb49d70f4aea6', 'compare-formal801-readonly-r4.py': '69b5a12746df30ee9f36bb8891ef021963403527b3e310ba45b3b9d5b8884b77', 'audit_trial_behavior_new772_r3.py': 'e83d2b027c648a480d06b1e1943953aefc1fe33c5c1e4c5626ba271c765c034b', 'native-handoff149-r4.py': '0af656e19b5c0012aadf245a0c907e72cab55fe9ccf1bb9d6bdd5d9295949486', 'run-epoch3-native-tb21149-r1.py': 'fee9f687af296a855ff9e8e62a6d5a4155e60fd52a2267ec0e41ac3144a46841', 'eval_audit_new772.py': '9f6d8eb31bd6da42d5a3cdd929c169c04b9496796a81f49e4b292889418f8bcf'}
OLD={'run-old112-native149-r1.py': '8eb6140b03cda53a0eaf04d9304718642f41b1dd4c171067d115082f67c1011b', 'audit-old112-behavior149-r1.py': 'd8de2b97872a50819a6e08fb0187d3e2ddfc1dfa462119ccffb36d73d08a1a1c'}
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
for root,items in [(R,EXPECTED),(O,OLD)]:
 for name,value in items.items():
  p=root/'scripts'/name
  if sha(p)!=value:raise ValueError('Source mismatch: '+name)
  py_compile.compile(str(p),doraise=True)
if (R/'jobs/qwen35-new772-tb21-n3').exists():raise ValueError('Formal Job has already started')
if list((O/'jobs').iterdir()):raise ValueError('Old behavior has already started')
behavior=json.loads((O/'checks/OLD112_NATIVE_BEHAVIOR_READER_ACCEPTANCE_R2.json').read_text())
if not behavior['passed']or behavior['old_behavior_reader_sha256']!=OLD['audit-old112-behavior149-r1.py']:
 raise ValueError('Current real long/short native recorder audit has not passed')
previous=R/'checks/NATIVE_EVAL149_DEPLOYMENT_RELEASE_R3.json'
release=json.loads(previous.read_text());release.update(kind='NATIVE_EVAL149_FIXED_DEPLOYMENT_RELEASE_R4',sources=EXPECTED,
 old_study_sources=OLD,previous_deployment_release_sha256=sha(previous),
 old112_deployment_plan_sha256=sha(O/'manifests/OLD112_NATIVE_DEPLOYMENT_PLAN_R1.json'),
 old112_all_native_configs_acceptance_sha256=sha(O/'checks/OLD112_NATIVE_ALL_CONFIGS_ACCEPTANCE_R2.json'),
 old112_real_recorders_acceptance_sha256=sha(O/'checks/OLD112_NATIVE_BEHAVIOR_READER_ACCEPTANCE_R2.json'),
 native_artifact_reader_acceptance_sha256=sha(R/'checks/NATIVE_ARTIFACT_BEHAVIOR_READER_ACCEPTANCE_R3.json'),
 native_801_config_preflight_sha256=sha(R/'checks/NATIVE_801_TRIAL_CONFIG_PREFLIGHT.json'),
 old_original_auditor_sha256=sha(R.parent/'qwen35-m1-m2-tb21-20261026/scripts/eval_audit.py'),
 original_old_wheel_sha256='f84f810e8a61545d685fb6722593886a0c88cc829b2ab9ca7c3476fe11e1209e',
 actual_old_trials_started=0,actual_formal_trials_started=0,native_artifact_resolution_used=True)
p=R/'checks/NATIVE_EVAL149_DEPLOYMENT_RELEASE_R4.json';encoded=json.dumps(release,ensure_ascii=False,indent=2)+'\n'
if p.exists():
 if p.read_text()!=encoded:raise ValueError('Preserve existing release R4')
else:p.write_text(encoded)
a=Path.home()/'.ssh/authorized_keys';raw=a.read_text();lines=raw.splitlines(keepends=True)
key='AAAAC3NzaC1lZDI1NTE5AAAAIFcjadVwf3U53fNy6PlY3PVSgxVJMf2+0DwtG98ZuRTy'
indices=[i for i,v in enumerate(lines)if key in v]
if len(indices)!=1 or 'native-handoff149-r3.py'not in lines[indices[0]]:raise ValueError('Unexpected previous restricted command')
backup=a.with_name('authorized_keys.before-native-eval-r4-'+str(int(time.time())));backup.write_text(raw);backup.chmod(0o600)
i=indices[0];lines[i]=lines[i].replace('native-handoff149-r3.py','native-handoff149-r4.py')
tmp=a.with_name('authorized_keys.native-eval-r4.tmp');tmp.write_text(''.join(lines));tmp.chmod(0o600);tmp.replace(a)
proof=dict(passed=True,release_sha256=sha(p),own_restricted_command_updated_only=True,
 other_authorized_keys_unchanged=True,original_801_and_old112_plans_unchanged=True,
 actual_formal_or_old_trials_started=0,backup=str(backup))
(R/'checks/NATIVE_EVAL149_R4_RESTRICTED_HANDOFF_ACTIVATION.json').write_text(json.dumps(proof,indent=2)+'\n');print(json.dumps(proof))
