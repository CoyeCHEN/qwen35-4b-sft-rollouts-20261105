import hashlib,json,py_compile,time
from pathlib import Path
R=Path('/home/chenkeyi/.local/share/harbor-rsi/qwen35-new772-tb21-20261101')
EXPECTED={'run-formal-native-tb21149-r3.py': '3cbdd39fe2792dfbfe8a89ce14270043c573e9413c500d5c3368d402beba59b1', 'compare-formal801-readonly-r3.py': 'a6a493ae3c94f995def1f6af4cd4dfa9e615026d719ca6c81c40680016f3aa94', 'audit_trial_behavior_new772_r2.py': 'e3566e28e0505b64dbc5c870a0f290a081ce8d0a679a46c31bff3f8ca0007b91', 'native-handoff149-r3.py': '110b972091b2df9926f8556c9a5fc983774418dd89210d6f959deda4bf44360f', 'run-epoch3-native-tb21149-r1.py': 'fee9f687af296a855ff9e8e62a6d5a4155e60fd52a2267ec0e41ac3144a46841', 'eval_audit_new772.py': '9f6d8eb31bd6da42d5a3cdd929c169c04b9496796a81f49e4b292889418f8bcf'}
for name,value in EXPECTED.items():
    p=R/'scripts'/name
    if hashlib.sha256(p.read_bytes()).hexdigest()!=value:raise ValueError('Source mismatch: '+name)
    py_compile.compile(str(p),doraise=True)
if (R/'jobs/qwen35-new772-tb21-n3').exists():raise ValueError('Formal Job has already started')
previous=json.loads((R/'checks/NATIVE_EVAL149_DEPLOYMENT_RELEASE_R2.json').read_text())
release={k:v for k,v in previous.items()if k!='native_801_config_preflight'}
release.update(kind='NATIVE_EVAL149_FIXED_DEPLOYMENT_RELEASE_R3',sources=EXPECTED,
    metric_specifications_sha256=hashlib.sha256((R/'manifests/METRIC_SPECIFICATIONS_R1.json').read_bytes()).hexdigest(),
    formal_posthoc_behavior_comparison=True,original_801_trial_plan_unchanged=True,
    original_epoch3_preregistration_unchanged=True,actual_formal_trials_started=0,
    strict_recorder_unknown_fixture_sha256=hashlib.sha256((R/'checks/STRICT_RECORDER_UNKNOWN_CLASSIFICATION_R3.json').read_bytes()).hexdigest(),
    native_801_config_preflight_sha256=hashlib.sha256((R/'checks/NATIVE_801_TRIAL_CONFIG_PREFLIGHT.json').read_bytes()).hexdigest(),
    incomplete_recorder_audit_is_protocol_unknown_not_confirmed_success=True)
p=R/'checks/NATIVE_EVAL149_DEPLOYMENT_RELEASE_R3.json'
encoded=json.dumps(release,ensure_ascii=False,indent=2)+'\n'
if p.exists():
    if p.read_text()!=encoded:raise ValueError('Preserve existing release R2')
else:p.write_text(encoded)
a=Path.home()/'.ssh/authorized_keys'
text=a.read_text();key='AAAAC3NzaC1lZDI1NTE5AAAAIFcjadVwf3U53fNy6PlY3PVSgxVJMf2+0DwtG98ZuRTy'
lines=text.splitlines(keepends=True);matches=[i for i,v in enumerate(lines)if key in v]
if len(matches)!=1:raise ValueError('Expected exactly one own restricted handoff key')
i=matches[0]
if 'native-handoff149-r2.py'not in lines[i]:raise ValueError('Unexpected original restricted command')
backup=a.with_name('authorized_keys.before-native-eval-r3-'+str(int(time.time())))
backup.write_text(text);backup.chmod(0o600)
lines[i]=lines[i].replace('native-handoff149-r2.py','native-handoff149-r3.py')
replacement=a.with_name('authorized_keys.native-eval-r3.tmp');replacement.write_text(''.join(lines));replacement.chmod(0o600);replacement.replace(a)
proof=dict(passed=True,release_sha256=hashlib.sha256(p.read_bytes()).hexdigest(),
    own_restricted_command_updated_only=True,other_authorized_keys_unchanged=True,
    authorized_keys_backup=str(backup),actual_formal_trials_started=0)
(R/'checks/NATIVE_EVAL149_R3_RESTRICTED_HANDOFF_ACTIVATION.json').write_text(json.dumps(proof,indent=2)+'\n')
print(json.dumps(proof))
