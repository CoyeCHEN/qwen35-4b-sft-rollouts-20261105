"""Stage unchanged source contexts, not images, for finite native17 preparation."""
import datetime
import hashlib
import json
import os
from pathlib import Path
import shlex
import stat
import subprocess

import collection_readiness_r7 as n
from collection_selection_r7 import active_rows
from collection_attempts_r6 import attempt_counts
import run_collection_stream_r4 as c


def run(args,**kwargs):return subprocess.run(args,check=True,**kwargs)


def main():
    plan_file=n.R/'manifests/TMAX_UNSTARTED_DIRECT_SSD17_R13.json'
    if plan_file.exists():raise FileExistsError('Observe the existing finite preparation plan')
    code="""from pathlib import Path
import json
s=Path('/ssd/chenkeyi/qwen35-new-cf500-tmax500-20261029')
contexts=[p.stem.removesuffix('.context') for p in (s/'buildkit-rootless-r2/contexts').glob('*.context.json')]
cold=[]
for p in (s/'cold-images-from149-r1/tmax').glob('*/*/image-audit.json'):
 x=json.loads(p.read_text())
 if x.get('all_original_manifest_config_layer_and_diffid_hashes_verified') and Path(x['archive']).is_file():cold.append(dict(task_id=p.parents[1].name,image_id=x['image_id']))
print(json.dumps(dict(context_task_ids=contexts,cold=cold)))"""
    reply=run([*n.DEPLOYMENT['ssh'],n.DEPLOYMENT['host'],shlex.join([n.DEPLOYMENT['python17'],'-c',code])],capture_output=True,text=True,timeout=60)
    inventory=json.loads(reply.stdout);contexts=set(inventory['context_task_ids']);cold={(x['task_id'],x['image_id']) for x in inventory['cold']}
    counts=attempt_counts();rows=active_rows(counts)
    state=json.loads((n.D/'state.json').read_text())
    inflight=set(state['preparing_environments'])|set(state['active_task_pipelines'])
    tasks=[];skipped={}
    source_manifest=n.R/'manifests/TMAX_RUNTIME_CANDIDATES_V2.jsonl';source_sha=n.sha(source_manifest)
    original_ids={x['task_id'] for x in map(json.loads,source_manifest.open())}
    for row in rows:
        ident=row['task_id']
        if row['pool']!='tmax' or counts.get(ident,0):continue
        if ident in contexts or ident in inflight:continue
        basic=n.find_basic(row)
        if basic is None:skipped[ident]='No accepted original-source basic receipt; investigate separately';continue
        receipt,value=basic
        if (ident,value['image_id']) in cold:continue
        if ident not in original_ids or value.get('source_candidate_manifest_sha256')!=source_sha:
            skipped[ident]='Source context is outside the original main manifest; preserve its explicit existing preparation path';continue
        context=Path(value['actual_build_context'])
        files=[dict(path=str(p.relative_to(context)),mode=stat.S_IMODE(p.stat().st_mode),sha256=n.sha(p)) for p in sorted(context.rglob('*')) if p.is_file()]
        if files!=value['build_context_files'] or hashlib.sha256(json.dumps(files,sort_keys=True).encode()).hexdigest()!=value['build_context_sha256']:
            raise ValueError('Original native context bytes or modes changed: '+ident)
        task=Path(row['task_path'])
        if n.sha(task/'task.toml')!=value['generated_original_task_toml_sha256']:
            raise ValueError('Original Task resource identity changed: '+ident)
        metadata=dict(task_id=ident,source_revision=row['revision'],source_manifest_sha256=source_sha,
            source_task_path=str(task),source_task_toml_sha256=n.sha(task/'task.toml'),actual_build_context=str(context),
            build_context_sha256=value['build_context_sha256'],build_context_files=files,
            status='NATIVE_PUBLIC_CONTEXT_FROZEN_RUNTIME_ACCEPTANCE_PENDING',model_calls=0,environment_ready=False)
        tasks.append(dict(task_id=ident,pool='tmax',slot_id=row['slot_id'],metadata=metadata,
            old_basic_receipt=str(receipt),old_basic_receipt_sha256=n.sha(receipt),old_image_id=value['image_id'],
            actual_full_attempts_at_plan=counts.get(ident,0),teacher_config_sha256=c.TEACHER_SHA,wheel_sha256=c.WHEEL_SHA))
    plan=dict(revision='r13',created_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),tasks=tasks,
        source_sha256=n.sha(Path(__file__)),original_main_manifest=str(source_manifest),original_main_manifest_sha256=source_sha,
        inventory_at_plan=inventory,excluded_inflight_at_plan=sorted(inflight),other_missing_preparation=skipped,
        finite_build_concurrency=1,finite_native_precheck_concurrency=1,model_calls=0,teacher_dispatches=0,
        selection='All unattempted fixed-main TMax tasks lacking an exact local17 cold archive and an existing17 native source context; source/image availability only, no model outcomes',
        execution='All builds, image checks/loads, initial checks, native CLI/NOP verification and cleanup occur on17;149 only transports immutable source files and controls the bounded preparation',
        old_model_trials_cancelled_or_replayed=0,task_or_test_modifications=0,image_bytes_via149_by_this_preparer=0)
    n.freeze(plan_file,plan)
    remote_root=n.NODE['ssd_root']+'/buildkit-rootless-r2/contexts'
    for item in tasks:
        ident=item['task_id'];metadata=item['metadata']
        proof=n.R/'checks/tmax-direct17-contexts-r13'/(ident+'.json');n.freeze(proof,metadata)
        run([*n.DEPLOYMENT['ssh'],n.DEPLOYMENT['host'],'mkdir -p '+shlex.quote(remote_root+'/'+ident)],timeout=30)
        run(['rsync','-a','-e',shlex.join(n.DEPLOYMENT['ssh']),metadata['actual_build_context']+'/',n.DEPLOYMENT['host']+':'+remote_root+'/'+ident+'/'],timeout=120)
        run(['rsync','-a','-e',shlex.join(n.DEPLOYMENT['ssh']),str(proof),n.DEPLOYMENT['host']+':'+remote_root+'/'+ident+'.context.json'],timeout=60)
    remote_plan='/home/chenkeyi/workspace/RSI/runtime-evidence/'+n.R.name+'/manifests/'+plan_file.name
    run(['rsync','-a','-e',shlex.join(n.DEPLOYMENT['ssh']),str(plan_file),n.DEPLOYMENT['host']+':'+remote_plan],timeout=60)
    n.freeze(n.R/'checks/direct17-context-staging-r13.json',dict(status='UNCHANGED_NATIVE_CONTEXTS_STAGED_ON17',planned_tasks=len(tasks),plan=str(plan_file),plan_sha256=n.sha(plan_file),checked_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),model_calls=0,image_bytes_via149=0))
    print(json.dumps(dict(plan=str(plan_file),tasks=len(tasks),other_missing_preparation=len(skipped),model_calls=0)))


if __name__=='__main__':
    os.environ['PATH']=str(n.R/'client-bin-v2')+':'+os.environ['PATH']
    for key in ['DEEPSEEK_API_KEY','GH_TOKEN','OPENAI_API_KEY']:os.environ.pop(key,None)
    main()
