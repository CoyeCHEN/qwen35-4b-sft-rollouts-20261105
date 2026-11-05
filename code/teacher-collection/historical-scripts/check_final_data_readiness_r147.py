"""Fail closed before final corpus assembly; this command never trains or dispatches."""
import argparse
from collections import Counter,defaultdict
import datetime
import hashlib
import json
import os
import subprocess
from pathlib import Path

from collection_attempts_r8 import attempt_counts
from collection_selection_r7 import active_rows
from audit_collection_results_r9 import teacher_sources

R=Path('/home/chenkeyi/.local/share/harbor-rsi/qwen35-new-cf500-tmax500-20261029')
QWEN_REVISION='851bf6e806efd8d0a36b00ddf55e13ccb7b8cd0a'
ENCODER_SHA='8506585c55ea67585d2512a86a45b689f324a766ac1679fb98aba30a6170b947'
sha=lambda path:hashlib.sha256(path.read_bytes()).hexdigest()


def pending_class(value):
    return 'PENDING' in value or 'REQUIRES_VERIFIER_LOG_CLASSIFICATION' in value


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--require-ready',action='store_true');args=parser.parse_args()
    counts=attempt_counts();selected=active_rows(counts);by_id={x['task_id']:x for x in selected}
    if len(by_id)!=1000 or Counter(x['pool'] for x in selected)!={'calibforge':500,'tmax':500}:raise ValueError('Fixed Task scope changed')
    if not set(counts)<=set(by_id):raise ValueError('Reserved attempts outside the active fixed Task scope')
    families={}
    for row in selected:
        key=(row['pool'],row['family_id'])
        if families.setdefault(key,row['split'])!=row['split']:raise ValueError('Frozen Task family crosses splits')
    for pool in ['calibforge','tmax']:
        if Counter(x['split'] for x in selected if x['pool']==pool)!={'train':450,'validation':50}:raise ValueError('Fixed family split changed')
    input_blobs={};records=[]
    for pool in ['CALIBFORGE','TMAX']:
        for kind in ['SUCCESS_INDEX','FAILURE_OR_PENDING_INDEX']:
            path=R/'indexes'/(pool+'_'+kind+'.jsonl');blob=path.read_bytes();input_blobs[str(path)]=hashlib.sha256(blob).hexdigest()
            records += [json.loads(line) for line in blob.splitlines() if line]
    if len({x['trial_id'] for x in records})!=len(records):raise ValueError('Duplicate Trial identity in final index inputs')
    grouped=defaultdict(list);pending=[];index_by_result={};source_unindexed=[]
    for row in records:
        if row['task_id'] not in by_id:raise ValueError('Trial outside fixed Task selection')
        task=by_id[row['task_id']]
        if any(row[key]!=task[key] for key in ['pool','split','family_id']):raise ValueError('Task/Trial provenance or split changed')
        result=Path(row['result_path'])
        if sha(result)!=row['result_sha256']:raise ValueError('Original indexed Result changed')
        index_by_result[str(result)]=row['result_sha256'];grouped[row['task_id']].append(row)
        if pending_class(row['classification']):pending.append(dict(task_id=row['task_id'],trial_id=row['trial_id'],classification=row['classification']))
        if row['qualified_success']:
            if row['classification']!='QUALIFIED_SUCCESS' or row['raw_reward']!=1 or not row['verifier_actually_completed'] or row['native_exception'] or row['infrastructure_errors'] or not row.get('cli_normal_closure') or row.get('teacher_contract_status')!='PASSED' or row.get('teacher_contract_violations') or row.get('original_task_environment_contract_status')!='PASSED':
                raise ValueError('A qualified success lacks actual normal verified closure')
            proof=row['student_proof']
            for key in ['semantic_projection_passed','exact_deployment_prefixes','all_original_targets_once','native_loader_and_collator_passed','native_streaming_and_nonstreaming_parsers_passed']:
                if proof.get(key) is not True:raise ValueError('A success lacks target-level evidence: '+key)
            if proof['source_journal_sha256']!=row['source_journal_sha256'] or proof['qwen_revision']!=QWEN_REVISION or proof['encoder_sha256']!=ENCODER_SHA:
                raise ValueError('A success mixes source journals or student contracts')
            if len(proof['original_call_ids'])!=len(set(proof['original_call_ids'])):raise ValueError('Repeated original Assistant target IDs')
    for config,scope,agent,results in teacher_sources():
        for result in results:
            if str(result) not in index_by_result:source_unindexed.append(str(result))
            elif sha(result)!=index_by_result[str(result)]:raise ValueError('Native source and indexed Result differ')
    lifecycle=R/'stream/collection-r4/teacher-lifecycle.jsonl';active={};maximum=0
    raw=lifecycle.read_bytes()
    for line in raw.splitlines():
        event=json.loads(line)
        if event['event']=='TEACHER_ADMITTED':active[event['trial_name']]=event
        elif event['event'] in ['TEACHER_AGENT_ENDED','TEACHER_FINALIZED']:active.pop(event['trial_name'],None)
        maximum=max(maximum,len(active))
    if maximum>8:raise ValueError('Global actual Teacher cap was exceeded')
    authority_path=next(R/'checks'/('CURRENT_DISPATCH_AUTHORITY_'+rev+'.json') for rev in ['R16','R15','R14','R13','R12'] if (R/'checks'/('CURRENT_DISPATCH_AUTHORITY_'+rev+'.json')).exists())
    authority=json.loads(authority_path.read_text());state=json.loads(Path(authority['state_path']).read_text())
    dispatch_root=R/'stream/collection-r4'
    native_pending=[];native_pending_ids=set();active_ids={x['task_id'] for x in active.values()}
    for path in (dispatch_root/'staging-dispatches').glob('*/setup.json'):
        setup=json.loads(path.read_text())
        if not (dispatch_root/'trials'/setup['trial_name']/'result.json').exists():
            native_pending.append(setup['trial_name']);native_pending_ids.add(setup['task_id'])
    reconciliation=R/'checks/attempt-environment-only-reconciliation-r6.json'
    excluded={x['result_sha256'] for x in json.loads(reconciliation.read_text())['environment_only_trials']}
    tasks=[]
    for row in selected:
        ident=row['task_id'];items=grouped[ident];successes=sorted((x for x in items if x['qualified_success']),key=lambda x:(x['started_at'],x['trial_id']))
        primary=[x for x in items if x['is_primary_trajectory']]
        if successes and (len(primary)!=1 or primary[0]['trial_id']!=successes[0]['trial_id']):raise ValueError('Primary is not the first chronological qualified success')
        if not successes and primary:raise ValueError('Primary without a qualified success')
        completed=[x for x in items if x['result_sha256'] not in excluded]
        if successes:status='QUALIFIED_PRIMARY_RETAINED'
        elif ident in active_ids:status='NATIVE_ADMITTED_AGENT_PHASE_ACTIVE'
        elif ident in native_pending_ids:status='NATIVE_SETUP_OR_TEACHER_GATE_PENDING'
        elif any(pending_class(x['classification']) for x in items):status='PENDING_TRIAL_CLASSIFICATION_OR_TARGET_AUDIT'
        elif counts.get(ident,0)>=2 and len(completed)>=2:status='EXHAUSTED_WITHOUT_QUALIFIED_SUCCESS'
        elif counts.get(ident,0)==0:status='UNATTEMPTED'
        elif counts.get(ident,0)>=2:status='CONSERVATIVE_RESERVATION_WITHOUT_TWO_TERMINAL_RESULTS'
        else:status='REMAINING_ALLOWED_ATTEMPT'
        tasks.append(dict(task_id=ident,pool=row['pool'],split=row['split'],family_id=row['family_id'],status=status,
            attempt_budget_used_actual_or_conservative=counts.get(ident,0),terminal_nonexcluded_trial_records=len(completed),
            qualified_trajectory_count=len(successes),primary_trial_id=primary[0]['trial_id'] if primary else None))
    worker=json.loads((R/'checks/stream-r4-data-audit-worker.json').read_text())
    moved=[path for path,digest in input_blobs.items() if sha(Path(path))!=digest]
    blockers=dict(native_admitted_agent_phase_trials=sorted(active),unfinished_native_setups_or_trials=sorted(native_pending),
        unfinished_preparation=state.get('preparing_environments',[]),native_results_not_yet_indexed=source_unindexed,
        pending_classification_or_target_records=pending,input_indexes_moved_during_check=moved,
        cpu_audit_pending_futures=worker.get('pending_futures',0),cpu_audit_errors=worker.get('errors',{}),
        unfinished_task_statuses={k:v for k,v in Counter(x['status'] for x in tasks).items() if k not in ['QUALIFIED_PRIMARY_RETAINED','EXHAUSTED_WITHOUT_QUALIFIED_SUCCESS']})
    ready=not any(blockers.values())
    engine_check=None
    if ready:
        manifest_path=Path(authority['manifest'])
        if sha(manifest_path)!=authority['manifest_sha256']:raise ValueError('Current Campaign manifest changed')
        manifest=json.loads(manifest_path.read_text());deployment_path=Path(manifest['deployment_config'])
        if sha(deployment_path)!=manifest['deployment_config_sha256']:raise ValueError('Current deployment changed')
        deployment=json.loads(deployment_path.read_text());env=dict(os.environ)
        env['PATH']=deployment['native_client_bin']+':'+str(R/'client-bin-v2')+':'+env['PATH']
        cli=['docker','--host',deployment['environment']['kwargs']['endpoint']]
        actual=subprocess.run(cli+['info','--format','{{.ID}}'],env=env,capture_output=True,text=True,check=True,timeout=30).stdout.strip()
        if actual!=deployment['runtime']['engine_id']:raise ValueError('Actual private Engine identity differs')
        containers=subprocess.run(cli+['ps','--filter','label=io.harbor.remote-docker.identity','--format','{{.ID}} {{.Names}}'],env=env,capture_output=True,text=True,check=True,timeout=30).stdout.splitlines()
        engine_check=dict(engine_id=actual,owned_native_task_containers=containers)
        if containers:blockers['owned_native_task_containers']=containers;ready=False
    report=dict(checked_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),status='READY_FOR_FINAL_CORPUS_INPUT_FREEZE' if ready else 'NOT_READY_COLLECTION_OR_AUDIT_INCOMPLETE',
        blockers=blockers,actual_engine_check=engine_check,planned_unique_tasks=1000,task_status_counts=dict(Counter(x['status'] for x in tasks)),tasks=tasks,
        qualified_success_trajectories=sum(x['qualified_success'] for x in records),qualified_primary_tasks=sum(x['is_primary_trajectory'] for x in records),
        source_index_sha256=input_blobs,lifecycle_snapshot_sha256=hashlib.sha256(raw).hexdigest(),authority=authority,
        attempt_reconciliation_sha256=sha(reconciliation),qwen_revision=QWEN_REVISION,encoder_sha256=ENCODER_SHA,
        source_sha256=sha(Path(__file__)),formal_cache_loader_collator_and_full_data_audit_still_required=True,
        raw_result_or_reward_changes=0,new_teacher_calls=0,corpus_release_or_training_started=False)
    target=R/'checks/data-finalization-readiness-r147.json';temporary=target.with_suffix('.pending');temporary.write_text(json.dumps(report,indent=2));temporary.replace(target)
    print(json.dumps(dict(status=report['status'],tasks=report['task_status_counts'],active_native_agent_phases=len(active),pending_target_or_classification_records=len(pending),native_results_not_indexed=len(source_unindexed),formal_release=False)))
    if args.require_ready and not ready:raise SystemExit(2)


if __name__=='__main__':main()
