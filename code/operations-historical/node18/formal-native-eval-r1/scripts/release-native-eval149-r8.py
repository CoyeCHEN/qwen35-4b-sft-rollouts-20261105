"""Accept versioned read-only qualification before switching the unused formal entry."""
import copy
import hashlib
import importlib
import json
from pathlib import Path
import subprocess
import time

R=Path('/home/chenkeyi/.local/share/harbor-rsi/qwen35-new772-tb21-20261101')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_text())
def unit(name):return dict(x.split('=',1)for x in subprocess.check_output(['systemctl','--user','show',name,'-p','MainPID','-p','ActiveState','-p','LoadState'],text=True).splitlines())
EXPECTED={'run-formal-native-tb21149-r8.py': '4f0ae1ec6e472444e54f9b5fbd8eb1932bb29112618b1ef0471a1f63ff379519', 'native-handoff149-r8.py': '342d895af8f139ba0be10edf9c2041de1427374ad041ffe2a8545519224b7b67', 'audit-native-response-qualification-r1.py': '6d3f5b10a84a6d7ef815f92aea8627def677a6b1025b2a445f96bb534292481e', 'compare-formal801-readonly-r7.py': 'f73b3d5a256aa432f2f8b02792d91a22ef3946f874a8669d05b73ee1409be8e7', 'compare-epoch3-epoch5-readonly149-r5.py': '53d87a1ea9b03ea10981419cbc41d4d3db8ca2dc2343e035d6ca13c3fa28c20a'}


def main():
    previous=R/'checks/NATIVE_EVAL149_DEPLOYMENT_RELEASE_R7.json'
    assert sha(previous)=='1e68d7627813d9002873a952424a4eb6bfecd7f79bcd9b8ff3f0a0158e5f1a76'
    old=read(previous)
    for name,digest in old['sources'].items():assert sha(R/'scripts'/name)==digest,name
    for name,digest in EXPECTED.items():assert sha(R/'scripts'/name)==digest,name
    assert not(R/'jobs/qwen35-new772-tb21-n3').exists()
    assert not(R/'manifests/THREE_MODEL_COLD_SERVING_ADMISSION.json').exists()
    assert unit('qwen35-new772-formal801-20261101')['LoadState']=='not-found'
    pre=read(R/'checks/NATIVE_801_TRIAL_CONFIG_PREFLIGHT_R8.json')
    assert pre['passed']and pre['actual_trials_started']==0
    assert pre['source_sha256']==EXPECTED['run-formal-native-tb21149-r8.py']
    assert pre['native_trial_configs']==read(R/'checks/NATIVE_801_TRIAL_CONFIG_PREFLIGHT_R7.json')['native_trial_configs']
    assert len(pre['native_trial_configs'])==801
    e3unit='qwen35-new772-new-m1-epoch3-fixed-20261102'
    before=unit(e3unit)
    assert before['MainPID']=='2454357'and before['ActiveState']=='active'
    for name in ['RESPONSE_QUALIFICATION_CPU_ACCEPTANCE_R1.json','ACTUAL_RESPONSE_QUALIFICATION_ACCEPTANCE_R1.json']:
        assert read(R/'checks'/name)['passed']
    receiver=importlib.import_module('native-handoff149-r8')
    validate=receiver.validate_formal_protocol
    tags=['m0','new-m1-e5','new-m2-e5']
    valid=dict(models={},native_extended_protocol_admissions={})
    wheel='1d27eef1ca6696275f306d8c653f7a266a4c7aea7321f0d47fd01b739c27fa18'
    for i,tag in enumerate(tags):
        alias='qwen35-new772-'+tag;weight=str(i+1)*64
        valid['models'][alias]=dict(weight_version=weight)
        valid['native_extended_protocol_admissions'][tag]=dict(model_id=alias,weight_version=weight,wheel_sha256=wheel,proof_sha256=str(i+4)*64)
    validate(valid)
    cases=['complete_distinct_fixture_admissions_pass']
    def reject(name,change):
        item=copy.deepcopy(valid);change(item)
        try:validate(item)
        except (ValueError,KeyError):cases.append(name);return
        raise AssertionError(name)
    reject('missing_model_rejected',lambda v:v['native_extended_protocol_admissions'].pop('m0'))
    reject('wrong_wheel_rejected',lambda v:v['native_extended_protocol_admissions']['m0'].update(wheel_sha256='0'*64))
    reject('wrong_weight_rejected',lambda v:v['native_extended_protocol_admissions']['m0'].update(weight_version='a'*64))
    reject('nonhex_proof_rejected',lambda v:v['native_extended_protocol_admissions']['m0'].update(proof_sha256='z'*64))
    reject('short_proof_rejected',lambda v:v['native_extended_protocol_admissions']['m0'].update(proof_sha256='0'))
    reject('duplicate_model_rejected',lambda v:v['native_extended_protocol_admissions']['m0'].update(model_id='qwen35-new772-new-m1-e5'))
    def swapped(v):
        p=v['native_extended_protocol_admissions'];p['m0'],p['new-m1-e5']=p['new-m1-e5'],p['m0']
    reject('swapped_model_tags_rejected',swapped)
    assert len(cases)==8
    value=copy.deepcopy(old)
    value.update(kind='NATIVE_EVAL149_FIXED_DEPLOYMENT_RELEASE_R8',sources=dict(old['sources'],**EXPECTED),
        previous_deployment_release_sha256=sha(previous),native_801_config_preflight_sha256=sha(R/'checks/NATIVE_801_TRIAL_CONFIG_PREFLIGHT_R8.json'),
        formal_response_qualification_source_sha256=EXPECTED['audit-native-response-qualification-r1.py'],
        response_qualification_cpu_acceptance_sha256=sha(R/'checks/RESPONSE_QUALIFICATION_CPU_ACCEPTANCE_R1.json'),
        actual_response_qualification_acceptance_sha256=sha(R/'checks/ACTUAL_RESPONSE_QUALIFICATION_ACCEPTANCE_R1.json'),
        formal_801_configs_equal_previous=True,formal_qualification_and_e3_e5_readers=['compare-formal801-readonly-r7.py','compare-epoch3-epoch5-readonly149-r5.py'],
        old_four_requires_complete_strict_response_qualification=True,
        actual_extended_protocol_still_required_before_formal_dispatch=True,
        receiver_protocol_fixture_cases=cases,fixture_is_not_actual_three_model_admission=True,
        no_new_model_calls_or_trial_dispatch=True,active_native_e3_unit_preserved=before,
        release_source_sha256=sha(Path(__file__)))
    value['previous_release_repaired_epoch3_trials_started_snapshot']=value.pop('actual_repaired_epoch3_trials_started')
    p=R/'checks/NATIVE_EVAL149_DEPLOYMENT_RELEASE_R8.json';assert not p.exists()
    p.write_text(json.dumps(value,indent=2)+'\n')
    a=Path.home()/'.ssh/authorized_keys';raw=a.read_text();lines=raw.splitlines(keepends=True)
    indices=[i for i,x in enumerate(lines)if 'native-handoff149-r7.py'in x];assert len(indices)==1
    backup=a.with_name('authorized_keys.before-native-handoff-r8-'+str(int(time.time())));backup.write_text(raw);backup.chmod(0o600)
    lines[indices[0]]=lines[indices[0]].replace('native-handoff149-r7.py','native-handoff149-r8.py')
    tmp=a.with_name('authorized_keys.native-handoff-r8.tmp');tmp.write_text(''.join(lines));tmp.chmod(0o600);tmp.replace(a)
    after=unit(e3unit);assert after==before
    proof=dict(passed=True,at=time.time(),release_sha256=sha(p),original_formal_trial_plan_sha256=old['formal_801_trial_plan_sha256'],
        formal_configs_compared=801,all_native_configs_equal=True,actual_new_trials=0,actual_model_calls=0,
        existing_e3_unit_identity_unchanged=True,e3_before=before,e3_after=after,receiver_fixture_cases_passed=8,
        actual_three_model_protocol_admission_not_claimed=True,active_native_runner_sources_unchanged=True)
    q=R/'checks/NATIVE_EVAL149_R8_ACTIVATION.json';assert not q.exists();q.write_text(json.dumps(proof,indent=2)+'\n')
    print(json.dumps(proof))


if __name__=='__main__':main()
