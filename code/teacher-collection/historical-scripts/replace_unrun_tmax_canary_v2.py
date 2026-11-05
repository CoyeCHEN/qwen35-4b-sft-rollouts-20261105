"""Use the next frozen same-stratum reserve after two pre-model build failures.

Never replaces a task that has had a teacher attempt. All source/build failures
remain separate preparation records and are not model rewards or attempts.
"""
import datetime
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tomllib
import zipfile

import toml
import yaml
import prepare_tmax_sources as source_preparation
from prepare_tmax_images_v2 import tree_identity
from prepare_cf_images import image_info,command,DISK_RESERVE
from tmax_runtime_adapter import runtime_compose_override

ROOT=source_preparation.ROOT
OLD='task_002254_d86cab6c'


def main():
    destination=ROOT/'manifests/TMAX_RUNTIME_CANDIDATES_V2.jsonl'
    if destination.exists():raise FileExistsError('Runtime candidate identities already frozen')
    rows=list(map(json.loads,(ROOT/'manifests/TMAX_RUNTIME_CANDIDATES_V1.jsonl').open()))
    old=next(r for r in rows if r['task_id']==OLD)
    for config in (ROOT/'jobs').glob('*/config.json'):
        data=json.loads(config.read_text())
        if data.get('install_only') or not any(a.get('name')=='open-harness' for a in data.get('agents',[])):continue
        if any(Path(t['path']).name==OLD for t in data.get('tasks',[])):
            raise ValueError('Cannot replace a task submitted to a teacher')
    path=ROOT/'checks/tmax-runtime-reserves'/(OLD+'.asset-failure.json')
    raw=path.read_bytes();value=json.loads(raw)
    if value['status']!='ASSET_PREPARATION_FAILED' or value['model_attempts']!=0:raise ValueError('Expected unrun original asset failure')
    prior=[dict(path=str(path),sha256=hashlib.sha256(raw).hexdigest(),reason=value['reason'])]
    used={r['task_id'] for r in rows}
    used.update(r['task_id'] for r in map(json.loads,(ROOT/'manifests/TMAX_500_TASKS.jsonl').open()))
    for e in map(json.loads,(ROOT/'manifests/TMAX_PREPARATION_REPLACEMENTS.jsonl').open()):
        used.update(e[k] for k in ['initial_task_id','candidate_task_id','task_id'] if k in e)
    for event in map(json.loads,(ROOT/'manifests/TMAX_RUNTIME_REPLACEMENTS_V1.jsonl').open()):
        used.add(event['candidate_task_id'])
    reserves=[r for r in map(json.loads,(ROOT/'manifests/TMAX_RESERVES.jsonl').open())
        if r['stratum']==old['stratum'] and r['task_id'] not in used]
    reserves.sort(key=lambda r:r['reserve_rank'])
    out=ROOT/'checks/tmax-runtime-reserves-v2';out.mkdir(exist_ok=True)
    ledger=ROOT/'manifests/TMAX_RUNTIME_REPLACEMENTS_V2.jsonl'
    with zipfile.ZipFile(ROOT/'sources/tmax/tasks.zip') as archive,ledger.open('x') as journal:
        replacement=None
        for candidate in reserves:
            ident=candidate['task_id'];record=dict(initial_task_id=old['initial_task_id'],replaced_task_id=OLD,
                candidate_task_id=ident,prior_preparation_failures=prior,stratum=candidate['stratum'],
                frozen_family_id=candidate['family_id'],frozen_split=candidate['split'],reserve_rank=candidate['reserve_rank'],
                model_attempts_before_replacement=0,reason='Original preconfigured Neo4j executable absent after failed public download in unchanged official setup',
                checked_at=datetime.datetime.now(datetime.timezone.utc).isoformat())
            name='tmax-runtime-reserve-'+ident.replace('_','-')
            try:
                if shutil.disk_usage(ROOT).free<DISK_RESERVE:raise RuntimeError('Disk headroom below 100GiB')
                source=source_preparation.materialize(archive,ident,[m for m in archive.infolist() if m.filename.startswith(ident+'/')])
                if source_preparation.adapter.digest(source/'task.json')!=candidate['task_json_sha256']:
                    raise ValueError('Frozen reserve source identity differs')
                native=source_preparation.adapter.convert_task(source,ROOT/'tasks/tmax',
                    native_converter=ROOT/'scripts/upstream-convert-to-harbor.py',
                    intricate_base_definition=ROOT/'scripts/base_intricate.def')
                task=ROOT/'tasks/tmax'/ident;tree=tree_identity(task/'environment')
                context_sha=hashlib.sha256(json.dumps(tree,sort_keys=True).encode()).hexdigest()
                context=ROOT/'build-contexts'/(ident+'-'+context_sha[:16]);shutil.copytree(task/'environment',context)
                if tree_identity(context)!=tree:raise ValueError('Actual reserve context differs')
                tag='rsi-stage2-tmax-20261029:'+ident
                with (out/(ident+'.build.log')).open('x') as log:
                    subprocess.run(['docker','build','--progress=plain','--label','rsi.campaign='+ROOT.name,
                        '--tag',tag,str(context)],check=True,stdout=log,stderr=subprocess.STDOUT,timeout=3600)
                image=image_info(tag);raw_config=tomllib.loads((task/'task.toml').read_text());resources=raw_config['environment']
                startup=runtime_compose_override(source)
                checked=command(['docker','run','--rm','--name',name,'--label','rsi.campaign='+ROOT.name,
                    '--cpus',str(resources['cpus']),'--memory',str(resources['memory_mb']*1024**2),
                    '--mount','type=bind,src='+str(source/'test_initial_state.py')+',dst=/trusted-preparation/test_initial_state.py,readonly',
                    '--entrypoint','/bin/bash',image['Id'],'-ic' if startup else '-lc',
                    'set -eu; pwd -P; id; test -w .; test ! -e /tests; python3 -m pytest -q /trusted-preparation/test_initial_state.py'],timeout=180)
                record.update(initial_returncode=checked.returncode,initial_stdout=checked.stdout,initial_stderr=checked.stderr)
                if checked.returncode:raise RuntimeError('Original reserve initial-state tests failed')
                runtime=ROOT/'prepared-tasks/tmax'/ident;shutil.copytree(task,runtime)
                raw_config['environment']['docker_image']=image['Id'];(runtime/'task.toml').write_text(toml.dumps(raw_config))
                if startup:(runtime/'environment/docker-compose.yaml').write_text(yaml.safe_dump(startup,sort_keys=False))
                for relative in ['instruction.md','tests/test.sh','tests/test_final_state.py']:
                    if (runtime/relative).read_bytes()!=(task/relative).read_bytes():raise ValueError('Original instruction/verifier changed')
                record.update(status='SOURCE_IMAGE_INITIAL_STATE_ACCEPTED_FINAL_VERIFIER_PENDING',native_conversion=native,
                    image_id=image['Id'],prepared_task_path=str(runtime),build_context_sha256=context_sha,
                    prepared_task_toml_sha256=hashlib.sha256((runtime/'task.toml').read_bytes()).hexdigest())
                replacement=dict(candidate,initial_task_id=old['initial_task_id'],runtime_replaced_task_id=OLD,
                    task_path=str(task),prepared_task_path=str(runtime),source_status='SOURCE_ACCEPTED_RUNTIME_PREPARED')
            except (source_preparation.adapter.TaskPreparationError,OSError,ValueError,RuntimeError,subprocess.SubprocessError) as error:
                record.update(status='RESERVE_PREPARATION_FAILED',error=str(error)[:700],error_type=type(error).__name__)
            finally:
                removed=command(['docker','rm','-f',name]);record['cleanup_confirmed']=removed.returncode==0 or 'No such container' in removed.stderr
            journal.write(json.dumps(record)+'\n');journal.flush();print(json.dumps({k:record.get(k) for k in ['candidate_task_id','status','error']}),flush=True)
            if replacement is not None:break
    if replacement is None:raise RuntimeError('Frozen same-stratum reserves exhausted')
    rows=[replacement if r['task_id']==OLD else r for r in rows]
    if len(rows)!=500 or len({r['task_id'] for r in rows})!=500:raise ValueError('Unique task count changed')
    with destination.open('x') as stream:
        for row in rows:stream.write(json.dumps(row)+'\n')
    canary=json.loads((ROOT/'checks/tmax-runtime-candidates-v1.json').read_text())['canary_task_ids']
    report=dict(status='PRE_MODEL_RUNTIME_REPLACEMENT_RECORDED_FINAL_VERIFIER_PENDING',
        replaced_task_id=OLD,replacement_task_id=replacement['task_id'],model_attempts=0,
        canary_task_ids=[replacement['task_id'] if t==OLD else t for t in canary],
        runtime_candidate_manifest=str(destination),manifest_sha256=hashlib.sha256(destination.read_bytes()).hexdigest(),
        source_candidate_manifest_preserved=True,teacher_failed_tasks_replaced=False)
    (ROOT/'checks/tmax-runtime-candidates-v2.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))


if __name__=='__main__':main()
