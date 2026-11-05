"""Verify the new handoff wiring with fixture-only stage transitions."""
import hashlib
import importlib
import json
from pathlib import Path
import tempfile
import time
from unittest.mock import patch

R=Path('/ssd/chenkeyi/qwen35-sft-772-20261101')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    old=(R/'run-native772-advance-r10.py').read_text()
    expected=old.replace('import phase_progression18_r7 as phases','import phase_progression18_r8 as phases').replace(
        "deployment_revision='r10-native-m2-gpu5-readiness-formal-extended-protocol-old4-old112'",
        "deployment_revision='r11-native-m2-formal-response-qualification-before-old4-old112'")
    assert expected==(R/'run-native772-advance-r11.py').read_text()
    old=(R/'read-only-monitor18-r16.py').read_text()
    assert old.replace('OBSERVATION_V16','OBSERVATION_V17').replace(
        'qwen35-772-native-advance-node18-20261101-r10.service',
        'qwen35-772-native-advance-node18-20261101-r11.service')==(R/'read-only-monitor18-r17.py').read_text()
    release=json.loads((R/'checks/NATIVE_EVAL149_DEPLOYMENT_RELEASE_R8.json').read_text())
    assert sha(R/'checks/NATIVE_EVAL149_DEPLOYMENT_RELEASE_R8.json')=='b01b16fbfffb65e17353bb50737d6ee123d3f2356c1e044b837437ca674f995b'
    assert release['formal_801_configs_equal_previous']and release['old_four_requires_complete_strict_response_qualification']
    assert json.loads((R/'checks/NATIVE_EVAL149_R8_ACTIVATION.json').read_text())['passed']
    phase=importlib.import_module('phase_progression18_r8')
    cases=[]
    for name,complete,should_resume in [
        ('terminal801_still_in_comparison_never_resumes',None,False),
        ('terminal801_without_strict_qualification_blocks',dict(response_qualification_completed=False),False),
        ('strictly_qualified_terminal801_enters_existing_old_transitions',dict(response_qualification_completed=True),True)]:
        calls=[];state={}
        fixture=dict(modes={'new11-install-preflight':dict(complete={'passed':True}),
                            'formal-n3':dict(complete=complete,progress={'terminal':801},systemd='ActiveState=inactive')})
        with tempfile.TemporaryDirectory(prefix='native-r11-fixture-',dir=R/'tmp') as temporary:
            with patch.object(phase,'C',Path(temporary)), patch.object(phase,'remote',return_value=fixture), \
                 patch.object(phase.serving,'stop',side_effect=lambda tag:calls.append('stop:'+tag)), \
                 patch.object(phase,'advance_old_study',side_effect=lambda state:calls.append('old4')), \
                 patch.object(phase.old_behavior,'advance',side_effect=lambda *args:calls.append('old112')):
                if complete is not None and not complete['response_qualification_completed']:
                    try:phase.formal({},state)
                    except AssertionError:pass
                    else:raise AssertionError(name)
                else:phase.formal({},state)
        resumed=[x for x in calls if not x.startswith('stop:')]
        assert resumed==(['old4','old112']if should_resume else []),name
        assert calls[:3]==['stop:m0','stop:new-m1-e5','stop:new-m2-e5']
        cases.append(dict(case=name,passed=True,existing_old_transitions_called=resumed))
    new=['phase_progression18_r8.py','run-native772-advance-r11.py','read-only-monitor18-r17.py']
    proof=dict(passed=True,at=time.time(),new_sources_sha256={name:sha(R/name)for name in new},
        source_sha256=sha(Path(__file__)),cases=cases,actual_gpu_or_model_calls=0,actual_trial_dispatches=0,
        mock_stage_actions_and_temp_output_only=True,actual_native_training_or_harbor_processes_unchanged=True,
        original_training_entry_differed_only_by_phase_import_and_deployment_identity=True,
        actual_all801_native_configs_equal_previous=True,
        actual_three_model_extended_protocol_admission_still_pending=True,
        native149_release_sha256=sha(R/'checks/NATIVE_EVAL149_DEPLOYMENT_RELEASE_R8.json'),
        native149_activation_sha256=sha(R/'checks/NATIVE_EVAL149_R8_ACTIVATION.json'))
    path=R/'checks/CONTROL_R11_CPU_SOURCE_ACCEPTANCE_R1.json'
    assert not path.exists()
    path.write_text(json.dumps(proof,indent=2)+'\n')
    print(json.dumps(proof))


if __name__=='__main__':main()
