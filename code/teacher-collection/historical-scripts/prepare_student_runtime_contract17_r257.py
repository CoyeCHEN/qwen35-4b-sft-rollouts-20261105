"""Prepare inactive student bindings to the already live-validated eleven tools."""
import datetime
import hashlib
import json
from pathlib import Path
import sys

S=Path('/ssd/chenkeyi/qwen35-new-cf500-tmax500-20261029')
D=S/'student-protocol-r257'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
EXPECTED=['read','bash','edit','write','grep','find','ls','edit_patch','trajectory_read','bash_job','finish']


def main():
    payload=json.load(sys.stdin);D.mkdir(exist_ok=False)
    teacher_blob=payload['teacher_config'].encode();offline_blob=payload['offline_proof'].encode()
    assert hashlib.sha256(teacher_blob).hexdigest()=='bf9069d53ec81d6f53a1a93f35bd61a0a8eadb42deafb4fc1c6540bf10afba2c'
    assert hashlib.sha256(offline_blob).hexdigest()==payload['offline_proof_sha256']
    teacher=json.loads(teacher_blob);compiled=json.loads(offline_blob)
    assert compiled['passed'] and compiled['tool_names']==EXPECTED
    assert teacher['tools']+['finish']==EXPECTED and teacher['finish']['enabled']
    assert compiled['tool_schema_sha256']=='89ad662f58c4fe4df97187bae2c84ada041a8195b3ba9bfc0a6eccc909b66bfe'
    assert compiled['system_prompt_sha256']=='400cd2a6498f6f0b33dea4b15cdc6c2e8c75b450017aca7ea7e6045041fb6958'
    assert teacher['toolResultBudget']['enabled'] and teacher['backgroundJobs']['enabled']
    assert not teacher['enableAgentTool'] and not teacher['enableSkillTool'] and teacher['toolSearch']=='off' and teacher['timeBudget']['seconds']==0
    policy_file=S/'student-protocol-r256/STUDENT_DATA_AND_SERVING_POLICY_LOCK_R256.json'
    policy=json.loads(policy_file.read_text())
    assert sha(policy_file)=='86a11f1e1612b772ff4499a0327d80be7447270b268450659e3abdbb61065482'
    assert policy['canonical_backend_semantics_sha256']=='027a3f1c30acd5438805f34bb427a99772640beba2a4e5153ada9c90fc259281'
    base=S/'workspace/configs';old_contract=base/'public-tool-contract.json';old_runtime=base/'runtime.json'
    assert sha(old_contract)=='6885ba747506891076ef53350961aac0fd2e08c2066df7de2bf5d1e18605d134'
    assert sha(old_runtime)=='2e36fafdadd0201de9ccef257ae84fcc657ba254ddfe1881bb8bbee6c3aaca84'
    previous={str(p):sha(p) for p in [old_contract,old_runtime]}
    (D/'frozen-teacher-config-source.json').write_bytes(teacher_blob)
    (D/'frozen-offline-compiled-contract-source.json').write_bytes(offline_blob)
    tool_options={k:teacher[k] for k in ['tools','enableAgentTool','enableSkillTool','toolSearch','resources','persist','recording','backgroundJobs','finish','timeBudget','compaction','branchSummary']}
    tool_options['toolResultBudget']=compiled['effective_tool_result_budget']
    contract=dict(status='FROZEN_PENDING_STUDENT_LIVE_VALIDATION',finish=True,tools=EXPECTED,
        schema_sha256=[compiled['tool_schema_sha256']],system_prompt_sha256=compiled['system_prompt_sha256'],
        teacher_config_sha256=compiled['teacher_config_sha256'],offline_proof_sha256=payload['offline_proof_sha256'],
        harness_wheel_sha256='c686ba3f429d8257a060cf6b6a6e4c5aa7d740f33b2d59180d9a2717b55d0db8',
        tool_options=tool_options,native_token_observation_enabled=True,
        teacher_live_evidence=payload['teacher_live_evidence'],
        student_template_prefix_evidence=payload['student_template_prefix_evidence'],
        student_model_live_validation_pending=True,real_runtime_proof=None,
        data_and_serving_policy=dict(path=str(policy_file),sha256=sha(policy_file)),
        old_ten_tool_candidate_unchanged=True)
    p=base/'public-tool-contract-r2.json';assert not p.exists();p.write_text(json.dumps(contract,indent=2))
    runtime=json.loads(old_runtime.read_text())
    runtime.update(model_path=policy['canonical_tokenizer_resource'],tokenizer_path=policy['canonical_tokenizer_resource'],
        tool_contract=str(p),data_and_serving_policy=str(policy_file),data_and_serving_policy_sha256=sha(policy_file),
        prepared_training_configs=policy['configs'],training_recipe='user_b32_e5_canonical_r2',
        hot_root=str(S/'student-training-r2'),service_prefix='openharness-cf-tmax-r2',
        formal_training_authorized=False,formal_authorized_stage=None,
        superseded_runtime=str(old_runtime),superseded_runtime_sha256=previous[str(old_runtime)])
    rp=base/'runtime-r2.json';assert not rp.exists();rp.write_text(json.dumps(runtime,indent=2))
    assert json.loads(rp.read_text())['tool_contract']==str(p)
    assert json.loads(Path(json.loads(rp.read_text())['tool_contract']).read_text())['tools']==EXPECTED
    assert all(sha(Path(p))==h for p,h in previous.items())
    proof=dict(passed=True,checked_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        scope='Inactive candidate wiring and identity only; no student server or training started; actual student live acceptance remains pending',
        runtime=dict(path=str(rp),sha256=sha(rp)),tool_contract=dict(path=str(p),sha256=sha(p)),
        data_and_serving_policy=dict(path=str(policy_file),sha256=sha(policy_file)),
        expected_tools=EXPECTED,finish=True,teacher_config_sha256=compiled['teacher_config_sha256'],
        original_runtime_and_tool_contract_unchanged=previous,model_weights_modified=False,
        teacher_controller_or_trials_changed=False,new_gpu_processes=0,training_started=False,
        source_sha256=sha(Path(__file__)))
    target=D/'STUDENT_RUNTIME_WIRING_ACCEPTANCE.json';target.write_text(json.dumps(proof,indent=2))
    print(json.dumps(dict(proof=str(target),sha256=sha(target),runtime=str(rp),tools=len(EXPECTED),finish=True,training_started=False)))


if __name__=='__main__':main()
