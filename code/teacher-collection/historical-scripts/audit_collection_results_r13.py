"""Read-only qualification and first-success indexes for this fresh campaign."""
from collections import Counter,defaultdict
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import tomllib

ROOT=Path('/home/chenkeyi/.local/share/harbor-rsi/qwen35-new-cf500-tmax500-20261029')
TEACHER_IDENTITIES={
    '47dc9cc9e37370be00589f690d2da7c5a08e964407dac6e94c57a2a2018da95d':
        ('teacher-native-11tools.json','e1cdfee7ac32629a070db50884f8bcc2bd1400d86d2cf781f59c2d6b57300d04'),
    'c686ba3f429d8257a060cf6b6a6e4c5aa7d740f33b2d59180d9a2717b55d0db8':
        ('teacher-native-11tools-summary-r1.json','bf9069d53ec81d6f53a1a93f35bd61a0a8eadb42deafb4fc1c6540bf10afba2c'),
}
sys.path.insert(0,str(ROOT/'wheels/open_harness_ai-0.3.0-py3-none-any.whl'))
from foundation.rollouts.export import RolloutView


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


from audit_collection_results_r7 import validated_recording
from reviewed_verifier_zero_r311 import apply_reviewed_zero
from reviewed_teacher_service_failure_r408 import apply_service_failure


def write_lines(path,rows):
    temporary=path.with_suffix('.tmp')
    with temporary.open('w') as stream:
        for row in rows:stream.write(json.dumps(row)+'\n')
    temporary.replace(path)


def teacher_sources():
    for file in sorted((ROOT/'jobs').glob('*/config.json')):
        config=json.loads(file.read_text())
        if config.get('install_only') or not any(a.get('name')=='open-harness' for a in config.get('agents',[])):continue
        yield file,file.parent.name,config['agents'][0],sorted(file.parent.glob('*/result.json'))
    snapshot_cache={}
    for file in sorted(ROOT.glob('stream/collection-r[34]/dispatches/*/dispatch.json')):
        root=file.parents[2]
        dispatch=json.loads(file.read_text())
        if dispatch['kind']!='teacher':continue
        native=file.parent/'trial-config.json'
        if sha(native)!=dispatch['config_sha256']:raise ValueError('Native queue TrialConfig identity changed')
        config=json.loads(native.read_text())
        if config['agent']['name']!='open-harness' or config['install_only']:raise ValueError('Native teacher dispatch classification differs')
        result=root/'trials'/dispatch['trial_name']/'result.json'
        if root.name=='collection-r4':
            snapshot=Path(dispatch['selection_snapshot'])
            if snapshot not in snapshot_cache:
                raw=snapshot.read_bytes()
                snapshot_cache[snapshot]=(hashlib.sha256(raw).hexdigest(),{x['task_id'] for x in json.loads(raw)})
            snapshot_sha,snapshot_ids=snapshot_cache[snapshot]
            if snapshot_sha!=dispatch['selection_snapshot_sha256']:raise ValueError('Immutable per-dispatch sampling snapshot changed')
            if dispatch['task_id'] not in snapshot_ids:raise ValueError('Teacher task absent from sampling snapshot')
        yield native,'stream-'+root.name,config['agent'],[result] if result.exists() else []


def main():
    selected={}
    for name in ['CALIBFORGE_500_TASKS.jsonl','TMAX_RUNTIME_CANDIDATES_V2.jsonl']:
        for row in map(json.loads,(ROOT/'manifests'/name).open()):selected[row['task_id']]=row
    from collection_selection_r7 import active_rows
    from collection_attempts_r8 import attempt_counts
    active=active_rows(attempt_counts())
    selected.update({row['task_id']:row for row in active})
    student_file=ROOT/'checks/STUDENT_AUDIT_TRIALS.json'
    student_doc=json.loads(student_file.read_text()) if student_file.exists() else {}
    for proof in student_doc.get('proofs',{}).values():
        relative=Path(proof['relative_path'])
        if relative.is_absolute() or '..' in relative.parts or sha(ROOT/relative)!=proof['sha256']:
            raise ValueError('Student audit proof artifact identity mismatch')
    student={x['trial_id']:x for x in student_doc.get('entries',[])}
    records=[];costs=[];protocol_cache={}
    for config_file,scope,agent_config,result_files in teacher_sources():
        declared=agent_config['kwargs'];wheel_sha=declared['wheel_sha256']
        teacher_name,teacher_sha=TEACHER_IDENTITIES[wheel_sha]
        teacher_file=ROOT/'configs'/teacher_name
        if sha(teacher_file)!=teacher_sha or declared['config']!=json.loads(teacher_file.read_text()):
            raise ValueError('Teacher job configuration is outside the explicitly recorded contract revisions')
        protocol_file=ROOT/'checks'/(scope+'-live-protocol.json')
        if protocol_file not in protocol_cache:
            raw=protocol_file.read_bytes() if protocol_file.exists() else None
            protocol_cache[protocol_file]=({x['trial_directory']:x for x in json.loads(raw)['trials']},hashlib.sha256(raw).hexdigest()) if raw is not None else ({},None)
        protocol_rows,protocol_sha=protocol_cache[protocol_file]
        for file in result_files:
            result=json.loads(file.read_text());ident=Path(result['config']['task']['path']).name
            if ident not in selected:raise ValueError('Teacher task outside the frozen candidate scope')
            row=selected[ident];trial=file.parent;agent=trial/'agent';rewards=(result.get('verifier_result') or {}).get('rewards') or {};reward=rewards.get('reward')
            exception=(result.get('exception_info') or {}).get('exception_type');infrastructure=result.get('infrastructure_errors') or []
            record=dict(pool=row['pool'],task_id=ident,trial_id=result['id'],job_name=scope,
                started_at=result['started_at'],finished_at=result['finished_at'],split=row['split'],family_id=row['family_id'],
                source_revision=row['revision'],result_path=str(file),result_sha256=sha(file),raw_reward=reward,
                coarse_category=row['coarse_category'],native_category=row['native_category'],
                native_difficulty=row['native_difficulty'],skills=row['skills'],subset=row.get('subset','main'),
                wheel_sha256=wheel_sha,teacher_config_sha256=teacher_sha,
                native_exception=exception,failure_phase=result.get('failure_phase'),infrastructure_errors=infrastructure,
                verifier_actually_completed=bool((result.get('verifier') or {}).get('finished_at')),
                qualified_success=False,is_primary_trajectory=False)
            protocol=protocol_rows.get(str(trial));proof=student.get(result['id'])
            record['teacher_contract_status']=('PENDING' if protocol is None else 'FAILED' if protocol['contract_violations'] else 'PASSED')
            record['teacher_contract_violations']=protocol['contract_violations'] if protocol else []
            if proof and proof.get('quarantine_class'):
                record.update(student_quarantine_class=proof['quarantine_class'],student_quarantine_reasons=proof['quarantine_reasons'])
            environment=tomllib.loads((Path(result['config']['task']['path'])/'task.toml').read_text()).get('environment',{})
            original_environment_ok=(row['pool']!='tmax' or
                (environment.get('workdir')=='/home/user' and environment.get('env',{}).get('HOME')=='/home/user'))
            record['original_task_environment_contract_status']='PASSED' if original_environment_ok else 'VARIANT_REQUIRES_EXCLUSION'
            if not original_environment_ok:
                record['environment_variant']=dict(actual_workdir=environment.get('workdir'),actual_HOME=environment.get('env',{}).get('HOME'),
                    required_workdir='/home/user',required_HOME='/home/user',
                    original_runtime_source_sha256='22ff11632c3dc090920cea4315c6e1e2da3e755c90b5752f9dc3766ce2d12919')
            if exception or infrastructure:
                phase=result.get('failure_phase') or ''
                record['classification']=('AGENT_TIMEOUT_REWARD_ONE' if reward==1 and exception=='AgentTimeoutError' else
                    'SETUP_INFRASTRUCTURE_FAILURE' if 'setup' in phase else
                    'VERIFIER_INFRASTRUCTURE_FAILURE' if 'verif' in phase else 'AGENT_OR_LIFECYCLE_FAILURE')
            elif not original_environment_ok:
                record['classification']='TMAX_ORIGINAL_ENVIRONMENT_CONTRACT_VARIANT'
            elif not record['verifier_actually_completed'] or type(reward) not in (int,float) or reward not in (0,1):
                record['classification']='VERIFIER_INCOMPLETE_OR_INVALID_REWARD'
            elif reward==0:
                record['classification']='OFFICIAL_REWARD_ZERO_REQUIRES_VERIFIER_LOG_CLASSIFICATION'
                log=trial/'verifier/test-stdout.txt'
                if log.exists():
                    text=log.read_text(errors='replace')
                    failed=re.findall(r'\b(\d+) failed\b',text)
                    if failed and 'ERROR collecting' not in text and 'ModuleNotFoundError' not in text:
                        record.update(classification='OFFICIAL_VERIFIER_ASSERTION_FAILURE',
                            verifier_log_path=str(log),verifier_log_sha256=sha(log),
                            official_failed_tests=int(failed[-1]))
            else:
                try:
                    marker=json.loads((agent/'open-harness.complete.json').read_text())
                    artifact=json.loads((agent/'artifact.json').read_text())
                    if marker['exit_code']!=0:raise ValueError('CLI did not exit normally')
                    if artifact['wheel_sha256']!=wheel_sha:raise ValueError('Installed wheel differs from the declared reviewed identity')
                    rollout=agent/'openharness-rollout';valid,sessions,structural_cache=validated_recording(agent,result['id'])
                    if not valid['complete'] or valid['issues'] or not valid['runs'] or any(r['status']!='completed' for r in valid['runs']):
                        raise ValueError('Recorder not fully completed')
                    journal=rollout/'events.jsonl';record.update(native_recorder_validation=valid,
                        source_journal_sha256=sha(journal),session_files=sessions,cli_normal_closure=True,native_structural_validation_cache=structural_cache)
                    if protocol is None:record['classification']='REWARD_ONE_PROTOCOL_AUDIT_PENDING'
                    elif protocol['contract_violations']:
                        record['classification']='REWARD_ONE_TEACHER_CONTRACT_VIOLATION'
                    elif proof is None:record['classification']='REWARD_ONE_NATIVE_COMPLETE_STUDENT_AUDIT_PENDING'
                    elif proof['source_journal_sha256']!=record['source_journal_sha256']:
                        raise ValueError('Student audit refers to a different raw journal')
                    elif not(proof['semantic_projection_passed'] and proof['native_loader_and_collator_passed']
                        and proof['native_streaming_and_nonstreaming_parsers_passed'] and proof['all_original_targets_once']):
                        record['classification']=('REWARD_ONE_UNSUPPORTED_MULTIMODAL' if proof.get('quarantine_class')=='UNSUPPORTED_MULTIMODAL'
                            else 'REWARD_ONE_STUDENT_SEMANTICS_NOT_ACCEPTED')
                        record['student_quarantine_reasons']=proof.get('quarantine_reasons',[])
                    else:
                        actual_ids={k for k,c in protocol['calls'].items() if c['source']=='agent'}
                        disposition_file=ROOT/'derived/teacher-call-dispositions'/(result['id']+'.json')
                        if disposition_file.exists():
                            binding=json.loads(disposition_file.read_text())
                            if binding['source_journal_sha256']!=record['source_journal_sha256'] or binding['classifier_sha256']!=sha(ROOT/'scripts/teacher_call_dispositions.py'):
                                raise ValueError('Raw retry disposition evidence identity differs')
                            exempt={x['call_id'] for x in binding['calls'] if x['source']=='agent' and x['disposition']=='RECOVERED_EMPTY_TRANSPORT_CALL_NO_ASSISTANT_TARGET'}
                            if not exempt<=actual_ids:raise ValueError('Retry dispositions contain unknown model call')
                            actual_ids-=exempt
                            record.update(recovered_empty_transport_calls=len(exempt),call_disposition_evidence=str(disposition_file),call_disposition_sha256=sha(disposition_file))
                        if actual_ids!=set(proof['original_call_ids']):raise ValueError('Student target set differs from actual agent calls')
                        record.update(classification='QUALIFIED_SUCCESS',qualified_success=True,student_proof=proof,
                            student_proof_index_sha256=sha(student_file),actual_provider_protocol_evidence=str(protocol_file),
                            actual_provider_protocol_evidence_sha256=protocol_sha)
                except (OSError,KeyError,ValueError) as error:
                    record.update(classification='REWARD_ONE_NATIVE_OR_REFERENCE_AUDIT_FAILED',audit_error=str(error))
            usage=(result.get('agent_result') or {}).get('model_usage') or {}
            costs.append(dict(pool=row['pool'],task_id=ident,trial_id=result['id'],model_usage=usage,
                cost_semantics='Native recorded estimates from frozen descriptor rates, not provider invoices',
                raw_call_usage_and_response_evidence=str(agent/'openharness-rollout/events.jsonl'),
                source_result_sha256=record['result_sha256']))
            record=apply_reviewed_zero(record)
            record=apply_service_failure(record)
            records.append(record)
    grouped=defaultdict(list)
    for record in records:grouped[(record['pool'],record['task_id'])].append(record)
    for values in grouped.values():
        eligible=sorted((r for r in values if r['qualified_success']),key=lambda r:(r['started_at'],r['trial_id']))
        if eligible:eligible[0]['is_primary_trajectory']=True
    out=ROOT/'indexes';out.mkdir(exist_ok=True)
    summaries={}
    for pool in ['calibforge','tmax']:
        rows=[r for r in records if r['pool']==pool]
        successes=[r for r in rows if r['qualified_success']];failures=[r for r in rows if not r['qualified_success']]
        write_lines(out/(pool.upper()+'_SUCCESS_INDEX.jsonl'),successes)
        write_lines(out/(pool.upper()+'_FAILURE_OR_PENDING_INDEX.jsonl'),failures)
        summaries[pool]=dict(planned_unique_tasks=500,terminal_native_trials=len(rows),
            independent_tasks_with_terminal_trials=len({r['task_id'] for r in rows}),
            raw_reward_one=sum(r['raw_reward']==1 for r in rows),qualified_success_trajectories=len(successes),
            qualified_independent_tasks=len({r['task_id'] for r in successes}),
            primary_trajectories=sum(r['is_primary_trajectory'] for r in rows),classifications=dict(Counter(r['classification'] for r in rows)))
        def distribution(items):
            return dict(unique_tasks=len(items),coarse_categories=dict(Counter(x['coarse_category'] for x in items)),
                native_categories=dict(Counter(x['native_category'] for x in items)),
                fixed_splits=dict(Counter(x['split'] for x in items)),
                native_difficulties=dict(Counter(x['native_difficulty'] for x in items)),
                skills=dict(Counter(skill for x in items for skill in set(x['skills']))),
                task_families=len({x['family_id'] for x in items}))
        summaries[pool]['active_sampling_distribution']=distribution([x for x in active if x['pool']==pool])
        summaries[pool]['qualified_primary_distribution']=distribution([x for x in rows if x['is_primary_trajectory']])
    write_lines(out/'NATIVE_TRIAL_COST_TOKEN_LEDGER.jsonl',costs)
    report=dict(status='PARTIAL_COLLECTION_QUALIFICATION_IN_PROGRESS',checked_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        pools=summaries,full_collection_complete=False,remaining_native_or_student_audits_are_not_assumed_success=True)
    (ROOT/'checks/collection-qualification.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))


if __name__=='__main__':main()
