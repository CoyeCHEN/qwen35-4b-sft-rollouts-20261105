"""Freeze native proofs and exact image bindings for two public setup repairs."""
import copy
import json
from pathlib import Path
import shlex
import shutil
import subprocess
import tomllib

import collection_readiness_r11 as n
from collection_attempts_r8 import attempt_counts
from collection_selection_r7 import active_rows


def read(p):return json.loads(Path(p).read_text())


def main():
    target=n.R/'manifests/PUBLIC_DEPENDENCY_IMAGE_APPROVALS_R76.json'
    if target.exists():raise FileExistsError('Inspect existing image approvals; never replay')
    previous=read(n.R/'manifests/CF_PUBLIC_VERIFIER_DEPENDENCY_APPROVALS_R39.json')
    if n.sha(n.R/'checks/public-image-bindings-r39-mirror-r76.json')!=n.NODE['approved_public_verifier_dependency_bindings']['sha256']:
        raise ValueError('Previous immutable node image mapping differs')
    approvals=copy.deepcopy(previous['tasks']);mapping=read(n.R/'checks/public-image-bindings-r39-mirror-r76.json')
    original_mapping=copy.deepcopy(mapping['bindings'])
    specs=[('task_007141_26892089','public-pytest-image-native17-r69','accept_public_pytest_image17_r69.py'),
        ('task_001742_6788502c','public-font-image-native17-r74','accept_original_public_image_font17_r74.py')]
    for ident,scope,worker in specs:
        if attempt_counts().get(ident,0):raise ValueError('An attempted Task cannot change its image')
        root=n.R/'stream'/scope;prior=root/'candidate-outcomes'/(ident+'.json');out=read(prior);plan=read(root/'PLAN.json')
        if out['status']!='CANDIDATE_ENV_READY_PENDING_IMAGE_BINDING_APPROVAL' or out['model_calls'] or out['teacher_dispatches']:
            raise ValueError('Candidate is not a zero-model native acceptance')
        if plan['source_sha256']!=n.sha(n.R/'scripts'/worker):raise ValueError('Frozen native worker changed')
        if read(root/'initial.json')['status']!='ORIGINAL_TASK_INITIAL_RESOURCES_NETWORK_ACCEPTED':raise ValueError('Original initial state did not pass')
        row=next(x for x in active_rows(attempt_counts()) if x['task_id']==ident)
        prepared=Path(out['admitted_task']['prepared_task_path']);base=Path(out['admitted_task']['task_path'])
        expected=tomllib.loads((base/'task.toml').read_text());expected['environment']['docker_image']=out['image_id']
        expected['environment']['workdir']='/home/user';expected['environment'].setdefault('env',{})['HOME']='/home/user'
        if tomllib.loads((prepared/'task.toml').read_text())!=expected:raise ValueError('External image-pin copy changed additional Task fields')
        if n.sha(prepared/'instruction.md')!=row['instruction_sha256']:raise ValueError('Original instruction changed')
        for member in out['admitted_task']['verifier_files']:
            if n.sha(prepared/member['path'])!=member['sha256']:raise ValueError('Official test bytes changed')
        native={}
        for kind in ['install','nop']:
            trial=Path(out['native_'+kind+'_trial']);path=trial/'result.json';raw=read(path)
            if n.sha(path)!=out[kind+'_result_sha256'] or raw.get('exception_info') or raw.get('infrastructure_errors') or not raw['finished_at']:
                raise ValueError('Candidate native lifecycle was not completed normally')
            cfg=copy.deepcopy(raw['config']);expected_cfg=n.native_config(out['admitted_task'],kind)
            if kind=='install':expected_cfg.agent.env={}
            expected_cfg=expected_cfg.model_dump(mode='json')
            for value in [cfg,expected_cfg]:
                value.pop('trial_name');value.pop('trials_dir');value['environment']['extra_docker_compose']=value['environment']['extra_docker_compose'][1:]
            if cfg!=expected_cfg:raise ValueError('Native acceptance differs beyond its isolated subnet/name/directory')
            archive=read(root/'ssd-trial-archives'/(trial.name+'.json'))
            if archive['result_sha256']!=n.sha(path) or archive['engine_id']!=n.NODE['engine_id']:raise ValueError('SSD native Result archive differs')
            if kind=='nop' and (not (raw.get('verifier') or {}).get('finished_at') or (raw.get('verifier_result') or {}).get('rewards',{}).get('reward')!=0):
                raise ValueError('Original official NOP verifier did not finish with zero')
            native[kind]=dict(trial=str(trial),result_sha256=n.sha(path),node17_result=archive['authoritative_ssd_root']+'/result.json',node17_archive_proof_sha256=n.sha(root/'ssd-trial-archives'/(trial.name+'.json')))
        # Keep the original raw candidate directory and give teacher Task names
        # their original IDs in a separate byte-identical deployment copy.
        teacher_task=n.R/'prepared-tasks/approved-public-images-r76'/ident
        if not teacher_task.exists():shutil.copytree(prepared,teacher_task)
        if any(n.sha(p)!=n.sha(teacher_task/p.relative_to(prepared)) for p in prepared.rglob('*') if p.is_file()):raise ValueError('Deployment copy is not byte identical')
        admitted=dict(out['admitted_task'],prepared_task_path=str(teacher_task),prepared_task_toml_sha256=n.sha(teacher_task/'task.toml'))
        built=read(root/'build.json')
        code='''import json,sys,hashlib,tarfile
from pathlib import Path
v=json.load(sys.stdin);sys.path.insert(0,v['scripts_root'])
from resolve_cold_image17_r2 import resolve
assert hashlib.sha256((Path(v['scripts_root'])/'resolve_cold_image17_r2.py').read_bytes()).hexdigest()==v['resolver_sha256']
old=resolve(v['task_id'],v['original_image_id'],'tmax',v['approved_bindings'])
new_path=Path(v['archive']).parent/'image-audit.json';new=json.loads(new_path.read_text())
assert hashlib.sha256(new_path.read_bytes()).hexdigest()==v['image_audit_sha256']
def config(proof):
 with tarfile.open(proof['archive']) as tar:
  raw=tar.extractfile('blobs/sha256/'+proof['config_digest'].split(':')[1]).read()
  assert 'sha256:'+hashlib.sha256(raw).hexdigest()==proof['config_digest']
  return json.loads(raw)
a=config(old);b=config(new)
keys=['Env','Cmd','Entrypoint','User','WorkingDir','Volumes','ExposedPorts','Shell','OnBuild','StopSignal','StopTimeout','Healthcheck','ArgsEscaped']
assert all(a['config'].get(k)==b['config'].get(k) for k in keys),'Original runtime configuration changed'
assert b['rootfs']['diff_ids'][:len(a['rootfs']['diff_ids'])]==a['rootfs']['diff_ids']
out={'task_id':v['task_id'],'original_image_id':v['original_image_id'],'image_id':new['image_id'],'runtime_config_keys_verified':keys,'original_rootfs_diffid_prefix_preserved':True,'runtime_environment_config_unchanged':True,'original_config_digest':old['config_digest'],'candidate_config_digest':new['config_digest'],'metadata_labels_equal':a['config'].get('Labels')==b['config'].get('Labels'),'model_calls':0}
p=Path(v['destination']);p.parent.mkdir(parents=True,exist_ok=True)
if p.exists():assert json.loads(p.read_text())==out
else:
 with p.open('x') as f:json.dump(out,f,indent=2)
print(json.dumps({'path':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'proof':out}))
'''
        request=dict(task_id=ident,original_image_id=built['original_image_id'],archive=built['archive'],
            image_audit_sha256=built['image_audit_sha256'],approved_bindings=n.NODE['approved_public_verifier_dependency_bindings'],
            scripts_root=str(Path(n.DEPLOYMENT['image_helper']).parent),resolver_sha256=n.NODE['cold_resolver_sha256'],
            destination=n.NODE['ssd_root']+'/deployment-r12/image-lineage-r76/'+ident+'.json')
        response=subprocess.run([*n.DEPLOYMENT['ssh'],n.DEPLOYMENT['host'],shlex.join([n.DEPLOYMENT['python17'],'-c',code])],
            input=json.dumps(request),check=True,capture_output=True,text=True,timeout=600)
        lineage=json.loads(response.stdout)
        declared=out.get('declared_prepared_source_image_id',built['original_image_id'])
        if ident=='task_007141_26892089':
            p=next(x for x in read(n.R/'manifests/TMAX_UNACCEPTED_ORIGINAL_ARCHIVES_R56.json')['tasks'] if x['task_id']==ident)
            source_receipt=Path(p['original_basic_receipt']);source_sha=p['original_basic_receipt_sha256']
            node_base=built['original_image_id']
        else:
            p=next(x for x in read(n.R/'manifests/TMAX_UNATTEMPTED_INITIAL_FAILURE_CONTEXTS_R58.json')['tasks'] if x['task_id']==ident)
            source_receipt=Path(p['old_basic_receipt']);source_sha=p['old_basic_receipt_sha256'];node_base=built['original_image_id']
        if n.sha(source_receipt)!=source_sha:raise ValueError('Original source identity receipt changed')
        approval=dict(task_id=ident,pool='tmax',status='NATIVE_ACCEPTED_PUBLIC_DEPENDENCY_CANDIDATE_PENDING_CAMPAIGN_PROMOTION',
            original_published_image_id=declared,original_image_identity_kind='Native conversion image; not an upstream published Docker image',
            exact_native17_base_image_id=node_base,image_id=built['image_id'],admitted_task=admitted,native_results=native,nop_reward=0,
            original_source_receipt149=str(source_receipt),original_source_receipt149_sha256=source_sha,
            original_candidate_outcome=str(prior),original_candidate_outcome_sha256=n.sha(prior),
            native_task_path_alias=dict(from_path=str(prepared),to_path=str(teacher_task),all_files_byte_identical=True),
            archive=built['archive'],archive_sha256=built['archive_sha256'],image_audit=str(Path(built['archive']).parent/'image-audit.json'),image_audit_sha256=built['image_audit_sha256'],
            original_base_layers_and_runtime_config_preserved=True,public_goal_boundary_review=None,public_goal_boundary_review_sha256=None,
            node17_image_lineage_proof=lineage['path'],node17_image_lineage_proof_sha256=lineage['sha256'],
            original_public_instruction_sha256=row['instruction_sha256'],official_private_files=admitted['verifier_files'],
            review_source_sha256=n.sha(Path(__file__)),model_calls=0,teacher_dispatches=0,official_task_or_test_changes=0)
        path=n.R/'checks/public-image-approvals-r76'/(ident+'.json');n.freeze(path,approval)
        approvals.append(dict(task_id=ident,path=str(path),sha256=n.sha(path),approval=approval))
        node_receipt=n.NODE['ssd_root']+'/deployment-r12/original-image-identities/'+ident+'.json'
        mirror=n.R/'checks/public-image-original-identities-r76'/(ident+'.json')
        n.freeze(mirror,dict(task_id=ident,image_id=node_base,original_declared_prepared_image_id=declared,
            image_identity_kind='Exact native original-context image, not an upstream published Docker image',
            accepted_native_derivation_approval_sha256=n.sha(path),original_source_receipt149_sha256=source_sha))
        subprocess.run([*n.DEPLOYMENT['ssh'],n.DEPLOYMENT['host'],'mkdir -p '+shlex.quote(str(Path(node_receipt).parent))],check=True,timeout=30)
        subprocess.run(['rsync','-a','-e',shlex.join(n.DEPLOYMENT['ssh']),str(mirror),n.DEPLOYMENT['host']+':'+node_receipt],check=True,timeout=120)
        mapping['bindings'][ident]=dict(task_id=ident,image_id=built['image_id'],original_published_image_id=node_base,
            original_image_identity_kind='Native original-context build, not an upstream published Docker image',
            original_cache_receipt=node_receipt,original_cache_receipt_sha256=n.sha(mirror),native_results=native,
            archive=built['archive'],archive_sha256=built['archive_sha256'],image_audit=approval['image_audit'],image_audit_sha256=built['image_audit_sha256'],
            original_base_layers_and_runtime_config_preserved=True,official_task_or_test_changes=0,source_approval_sha256=n.sha(path))
    n.freeze(target,dict(tasks=approvals,engine_id=n.NODE['engine_id'],model_calls=0,teacher_dispatches=0,source_sha256=n.sha(Path(__file__))))
    mapping.update(source_approval_manifest_sha256=n.sha(target),scope='Two unchanged CF approvals plus two exact native-accepted TMax public setup corrections; no teacher model or Task scoring changes')
    if any(mapping['bindings'][key]!=value for key,value in original_mapping.items()):raise ValueError('An existing CF image binding changed')
    path=n.R/'manifests/PRIVATE17_PUBLIC_IMAGE_BINDINGS_R76.json';n.freeze(path,mapping)
    print(json.dumps(dict(approved_images=len(approvals),new_tmax_images=2,retained_cf_bindings=len(original_mapping),manifest=str(target),manifest_sha256=n.sha(target),node_mapping=str(path),node_mapping_sha256=n.sha(path),teacher_dispatches=0)))


if __name__=='__main__':main()
