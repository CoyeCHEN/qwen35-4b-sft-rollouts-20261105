"""Freeze completed native canary capture evidence; training admission is separate.

Reward zero and explicit whole-trace multimodal quarantine are observed outcomes,
not setup failures. No task, reward, attempt, or final environment gate is altered.
"""
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys
import datetime

R=Path('/home/chenkeyi/.local/share/harbor-rsi/qwen35-new-cf500-tmax500-20261029')
sys.path.insert(0,str(R/'wheels/open_harness_ai-0.3.0-py3-none-any.whl'))
from foundation.rollouts.export import RolloutView


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    target=R/'checks/CANARY_GATE.json'
    if target.exists():raise FileExistsError('Canary acceptance already frozen')
    proof_index=R/'checks/STUDENT_AUDIT_TRIALS.json';student_doc=json.loads(proof_index.read_text())
    for proof in student_doc['proofs'].values():assert sha(R/proof['relative_path'])==proof['sha256']
    proofs={p['trial_id']:p for p in student_doc['entries']}
    records=[]
    for pool in ['CALIBFORGE','TMAX']:
        for kind in ['SUCCESS','FAILURE_OR_PENDING']:
            records.extend(json.loads(x) for x in (R/'indexes'/(pool+'_'+kind+'_INDEX.jsonl')).open())
    eligible=[];excluded=[]
    valid_classes={'QUALIFIED_SUCCESS','REWARD_ONE_UNSUPPORTED_MULTIMODAL','OFFICIAL_VERIFIER_ASSERTION_FAILURE'}
    for record in sorted(records,key=lambda r:(r['started_at'],r['trial_id'])):
        if record['classification'] not in valid_classes or record['teacher_contract_status']!='PASSED':
            excluded.append({k:record.get(k) for k in ['pool','task_id','trial_id','classification']});continue
        if any(r['task_id']==record['task_id'] for r in eligible):continue
        trial=Path(record['result_path']).parent;agent=trial/'agent'
        result=json.loads((trial/'result.json').read_text())
        assert result['finished_at'] and result['verifier']['finished_at'] and result['exception_info'] is None
        assert not result.get('infrastructure_errors')
        marker=json.loads((agent/'open-harness.complete.json').read_text());assert marker['exit_code']==0
        artifact=json.loads((agent/'artifact.json').read_text());assert artifact['wheel_sha256']==record['wheel_sha256']
        validation=RolloutView.open(agent/'openharness-rollout').validate()
        assert validation['complete'] and not validation['issues'] and all(r['status']=='completed' for r in validation['runs'])
        session_ids=set()
        for path in (agent/'openharness-sessions').glob('*.jsonl'):
            ids=set()
            for line in path.open():
                item=json.loads(line);assert item['id'] not in ids and (item['parentId'] is None or item['parentId'] in ids)
                ids.add(item['id'])
                if item['type']=='header':session_ids.add(item['data']['sessionId'])
        assert session_ids=={r['session_id'] for r in validation['runs']}
        journal=agent/'openharness-rollout/events.jsonl';proof=proofs[record['trial_id']]
        assert proof['source_journal_sha256']==sha(journal)
        protocol=R/'checks'/(record['job_name']+'-live-protocol.json')
        actual=next(x for x in json.loads(protocol.read_text())['trials'] if x['trial_directory']==str(trial))
        assert not actual['contract_violations']
        assert set(proof['original_call_ids'])=={i for i,c in actual['calls'].items() if c['source']=='agent'}
        if record['classification']=='REWARD_ONE_UNSUPPORTED_MULTIMODAL':
            assert proof['quarantine_class']=='UNSUPPORTED_MULTIMODAL' and proof['partial_text_prefixes_not_admitted']
            disposition='WHOLE_TRACE_UNSUPPORTED_MULTIMODAL_QUARANTINE_TESTED_NO_TRAINING_ADMISSION'
        else:
            assert all(proof[k] for k in ['semantic_projection_passed','native_loader_and_collator_passed','native_streaming_and_nonstreaming_parsers_passed','all_original_targets_once'])
            disposition='QUALIFIED_PRIMARY_SUCCESS' if record['qualified_success'] else 'LEGAL_ZERO_EXCLUDED_FROM_SUCCESS_CORPUS'
        eligible.append(dict(pool=record['pool'],task_id=record['task_id'],trial_id=record['trial_id'],
            raw_reward=record['raw_reward'],classification=record['classification'],training_disposition=disposition,
            result_path=record['result_path'],result_sha256=record['result_sha256'],source_journal_sha256=sha(journal),
            wheel_sha256=record['wheel_sha256'],protocol_sha256=sha(protocol),student_proof_index_sha256=sha(proof_index),
            native_recorder_complete=True,session_references_complete=True,cli_normal_closure=True,
            observed_tool_calls=actual['observed_tool_calls']))
    selected=[]
    for pool in ['calibforge','tmax']:
        rows=[r for r in eligible if r['pool']==pool]
        assert len(rows)>=8
        selected.extend(rows[:8])
    offline=R/'checks/summary-r1-offline-teacher-contract.json';native=R/'checks/native-tool-functional-diagnostics-v2.json'
    config=json.loads(offline.read_text());assert config['passed'] and config['full_raw_preserved']
    assert config['tool_schema_sha256']=='89ad662f58c4fe4df97187bae2c84ada041a8195b3ba9bfc0a6eccc909b66bfe'
    assert config['system_prompt_sha256']=='400cd2a6498f6f0b33dea4b15cdc6c2e8c75b450017aca7ea7e6045041fb6958'
    assert all(x['functional_evidence']['passed'] and x['native_cleanup_confirmed'] for x in json.loads(native.read_text()))
    compaction_job=R/'checks/cf-tmax-original-environment-canary-20261030-live-protocol.json'
    auxiliary=[(t,c) for t in json.loads(compaction_job.read_text())['trials'] for c in t['calls'].values() if c['source']!='agent']
    assert auxiliary and all(c['payload']['thinking']=={'type':'enabled'} and c['payload']['reasoning_effort']=='max' and c['payload']['max_tokens']==65536 for _,c in auxiliary)
    report=dict(passed=True,checked_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        gate_scope='Native task capture, actual provider contract, references, zero classification and whole-trace quarantine handling; not 1000-task environment readiness or 500 successes',
        unique_canary_tasks_by_pool=dict(Counter(r['pool'] for r in selected)),
        teacher_config_sha256='bf9069d53ec81d6f53a1a93f35bd61a0a8eadb42deafb4fc1c6540bf10afba2c',
        wheel_sha256='c686ba3f429d8257a060cf6b6a6e4c5aa7d740f33b2d59180d9a2717b55d0db8',
        selected_native_trials=selected,excluded_trials_preserved=excluded,
        whole_trace_unsupported_multimodal_is_not_qualified_success=True,
        additional_canary_tasks_were_already_inside_original_500=True,
        offline_new_wheel_evidence=dict(path=str(offline),sha256=sha(offline)),
        native_functional_evidence=dict(path=str(native),sha256=sha(native),scope='Synthetic native SDK probes in both actual task images, zero model calls; old wheel tool implementation unchanged by summary-only patch'),
        actual_corrected_auxiliary_calls=len(auxiliary),raw_records_unchanged=True,
        full_collection_requires_separate_all_1000_environment_gate=True)
    with target.open('x') as stream:stream.write(json.dumps(report,indent=2))
    print(json.dumps({k:v for k,v in report.items() if k not in ['selected_native_trials','excluded_trials_preserved']}))


if __name__=='__main__':main()
