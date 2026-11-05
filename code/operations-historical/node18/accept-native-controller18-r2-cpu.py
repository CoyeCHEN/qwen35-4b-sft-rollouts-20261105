"""Compare all801 native configs and source boundaries without dispatching Tasks."""
import ast
from collections import Counter
import importlib
import inspect
import json
import hashlib
import os
from pathlib import Path
import subprocess
import sys
import time

R=Path('/ssd/chenkeyi/qwen35-sft-772-20261101')
E=R/'formal-native-eval-r1'
sys.path.insert(0,str(E/'scripts'))
from harbor.models.job.config import JobConfig
from harbor.models.trial.config import TrialConfig
from harbor_remote_docker import RemoteDockerEnvironment


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def function(path,name):
    source=path.read_text()
    tree=ast.parse(source)
    node=next(n for n in tree.body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef))and n.name==name)
    return ast.get_source_segment(source,node)


def differences(a,b,path=()):
    if isinstance(a,dict)and isinstance(b,dict):
        result=[]
        for key in a.keys()|b.keys():
            if key not in a or key not in b:
                result.append(path+(key,))
            else:result.extend(differences(a[key],b[key],path+(key,)))
        return result
    return [path]if a!=b else []


def main():
    old=importlib.import_module('run-formal-native-tb21149-r9')
    new=importlib.import_module('run-formal-native-tb2118-r2')
    plan=old.read(old.R/'manifests/FORMAL_801_TRIAL_PLAN.json')
    cfg=JobConfig.model_validate_json(old.selected_config(plan).read_text())
    trials=[TrialConfig(task=t,agent=a,environment=cfg.environment,verifier=cfg.verifier,
        trials_dir=old.R/'diagnostics/native-preview')for _ in range(cfg.n_attempts)for t in cfg.tasks for a in cfg.agents]
    original=old.apply_trial_overrides(trials,plan,old.read(old.R/'configs/environment-profiles-agent-deps-r2.json'))
    preview=E/'checks/NATIVE_801_TRIAL_CONFIG_PREFLIGHT_NODE18_R2.json'
    candidate=json.loads(preview.read_text())['native_trial_configs']
    assert len(original)==len(candidate)==801
    allowed={('trials_dir',),('environment','kwargs','endpoint'),('environment','kwargs','transfer_timeout_sec')}
    counts=Counter()
    for before,after in zip(original,candidate):
        diff=differences(before,after);assert set(diff)==allowed,diff
        counts.update('.'.join(p)for p in diff)
        assert after['environment']['kwargs']['transfer_timeout_sec']==3600
        assert after['trials_dir']==str(E/'diagnostics/native-preview')
    assert inspect.signature(RemoteDockerEnvironment).parameters['transfer_timeout_sec'].default==600
    assert (R/'run-native772-advance-r14.py').read_text()==(R/'run-native772-advance-r13.py').read_text().replace('phase_progression18_r10','phase_progression18_r11').replace('r13-native-formal-e3-e5-lineage-readout','r14-native-formal-controller18-ssd')
    for name in ['remote','request','continue_original_e3','diagnostics','advance_old_study']:
        assert function(R/'phase_progression18_r11.py',name)==function(R/'phase_progression18_r10.py',name).replace('NATIVE_EVAL149_DEPLOYMENT_RELEASE_R10.json','NATIVE_EVAL149_DEPLOYMENT_RELEASE_R11.json'),name
    assert (R/'read-only-monitor18-r20.py').read_text()==(R/'read-only-monitor18-r19.py').read_text().replace('OBSERVATION_V19','OBSERVATION_V20').replace('node18-20261101-r13.service','node18-20261102-r14.service')
    guard=subprocess.run([sys.executable,str(R/'native-handoff149-r11.py')],input='',capture_output=True,text=True,
        env=os.environ|dict(SSH_ORIGINAL_COMMAND='formal-n3'),timeout=10)
    assert guard.returncode!=0 and 'Formal801 write authority moved to the sole node18 controller'in guard.stderr
    assert not(E/'jobs/qwen35-new772-tb21-n3').exists()
    assert not(Path('/data/chenkeyi/qwen35-sft-772-20261101/control')/'native-phase-requests/formal-n3.json').exists()
    sources=['run-native772-advance-r14.py','phase_progression18_r11.py','read-only-monitor18-r20.py',
        'native-handoff149-r11.py','sync-closed-e3-evidence18-r1.py',
        'preflight-formal-controller18-m0-native-joint-r1.py','formal-native-eval-r1/scripts/run-formal-native-tb2118-r2.py']
    value=dict(passed=True,at=time.time(),native_configs=801,changed_native_trial_fields=dict(counts),
        original_agent_verifier_resources_models_sampling_wheel_and_seeds_unchanged=True,
        original_12000_sec_preserved=sum(t['agent']['override_timeout_sec']==12000 for t in candidate),
        original_provider_transfer_timeout_sec=600,proposed_transfer_timeout_sec=3600,
        existing_training_and_e3_source_boundaries_unchanged=True,legacy149_formal_write_rejected=True,
        new_sources_sha256={n:sha(R/n)for n in sources},native_preview_sha256=sha(preview),
        deployment_sha256=sha(new.DEPLOYMENT),actual_tasks_or_model_calls=0,activated=False,
        real_joint_and_eight_transfer_acceptance_still_required=True,source_sha256=sha(Path(__file__)))
    p=R/'checks/FORMAL_CONTROLLER18_ALL801_CONFIG_DELTA_ACCEPTANCE_R2.json';assert not p.exists()
    p.write_text(json.dumps(value,indent=2)+'\n');print(json.dumps(value))


if __name__=='__main__':main()
