"""Finite eight-Task image buffer using the accepted17 image helper; no teacher."""
import datetime
import fcntl
import json
import os
from pathlib import Path

import collection_readiness_r21 as n
from collection_attempts_r8 import attempt_counts
from collection_selection_r7 import active_rows
from collection_current_setup_blocks_r453 import current_setup_blocks
from collection_administrative_ready_r427 import reconcile
from run_collection_stream_r22 import freeze

S = n.R/'stream/remaining-resident-buffer17-r458'


def main():
    S.mkdir(parents=True,exist_ok=True)
    lock = (S/'worker.lock').open('a')
    fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    assert not (S/'PLAN.json').exists(), 'Observe this bounded image pass; never replay'
    counts = attempt_counts()
    rows = active_rows(counts)
    qualified = {json.loads(line)['task_id'] for pool in ['CALIBFORGE','TMAX'] for line in (n.R/'indexes'/(pool+'_SUCCESS_INDEX.jsonl')).open()}
    eligible = [row for row in rows if row['task_id'] not in qualified and counts[row['task_id']] < 2]
    identities = {row['task_id'] for row in eligible}
    ready = {}
    receipts = {}
    for root in n.readiness_roots():
        for path in [*sorted((root/'environment-outcomes').glob('*.json')),*sorted((root/'ready-revisions').glob('*/*.json'))]:
            value = json.loads(path.read_text())
            if value['status'] == 'ENV_READY' and value['task_id'] in identities:
                ready[value['task_id']] = n.normalize_ready(value,path)
                receipts[value['task_id']] = path
    blocks,_ = reconcile(n.R,ready,current_setup_blocks(n.R,ready))
    chosen = [row for row in eligible if row['task_id'] in ready and row['task_id'] not in blocks][:8]
    assert len(chosen) == 8 and len({row['task_id'] for row in chosen}) == 8
    freeze(S/'PLAN.json',dict(checked_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        task_ids=[row['task_id'] for row in chosen],maximum_resident_tasks=8,image_preparation_concurrency=1,
        selection='First eight still-authorized Tasks in the unchanged frozen active manifest order; no source sampling changes',
        deployment_config_sha256=n.CONFIG_SHA,runtime_node='17',engine_id=n.NODE['engine_id'],
        actual_or_conservative_attempts=sum(counts.values()),model_calls=0,teacher_dispatches=0,
        source_sha256=n.sha(Path(__file__))))
    outcomes = {}
    for row in chosen:
        ident = row['task_id']
        accepted = ready[ident]
        admitted = accepted['admitted_task']
        assert admitted['runtime_node'] == '17' and admitted['runtime_engine_id'] == n.NODE['engine_id']
        value = dict(task_id=ident,pool=row['pool'],image_id=admitted['image_id'],
            ready_receipt=str(receipts[ident]),ready_receipt_sha256=n.sha(receipts[ident]),
            known_original_nop_limitation=bool(accepted.get('preflight_exception')),
            model_calls=0,teacher_trial=False)
        try:
            proof = n.ensure_resident(admitted)
            freeze(S/'image-proofs'/(ident+'.json'),proof)
            actual = n.image_info(admitted['image_id'])
            assert actual is not None
            value.update(status='VALIDATED_READY_TASK_IMAGE_RESIDENT_ON17',image_inspection=actual)
        except Exception as error:
            value.update(status='IMAGE_BUFFER_NOT_READY',error_type=type(error).__name__,reason=str(error)[:1500])
        freeze(S/'outcomes'/(ident+'.json'),value)
        outcomes[ident] = value
        state = dict(checked_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),pid=os.getpid(),
            terminal=len(outcomes),planned=8,resident_ready_tasks=sum(row['status']=='VALIDATED_READY_TASK_IMAGE_RESIDENT_ON17' for row in outcomes.values()),
            model_calls=0,actual_teacher_trials=0,maximum_resident_tasks=8,outcomes=outcomes)
        temporary = S/'state.pending'
        temporary.write_text(json.dumps(state,indent=2))
        temporary.replace(S/'state.json')
    assert attempt_counts() == counts
    state.update(terminal=True,teacher_budget_unchanged=True,live_teacher_queue_buffer=False,
        prepared_images_are_not_actual_teacher_trials=True)
    freeze(S/'TERMINAL.json',state)
    print(json.dumps(dict(terminal=str(S/'TERMINAL.json'),resident_ready_tasks=state['resident_ready_tasks'],
        actual_teachers=0,model_calls=0,attempt_counter=sum(counts.values()))))


if __name__=='__main__':
    os.environ['PATH']=n.DEPLOYMENT['native_client_bin']+':'+str(n.R/'client-bin-v2')+':'+os.environ['PATH']
    for key in ['DEEPSEEK_API_KEY','OPENAI_API_KEY','GH_TOKEN']:
        os.environ.pop(key,None)
    main()
