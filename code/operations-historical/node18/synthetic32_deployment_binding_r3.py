"""Additional image identity gate; never changes raw Result/Reward/Recorder."""
import hashlib,json
from pathlib import Path
R=Path('/ssd/chenkeyi/qwen35-sft-772-20261101');B=R/'synthetic32'
def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def bind_manifest(value):
 path=B/'SYNTHETIC32_DEPLOYMENT_R3.json';deployment=read(path);byid={x['task_id']:x for x in deployment['tasks']};assert not value.get('frozen'),'Do not mutate a frozen Manifest'
 for row in value['tasks']:
  item=byid[row['task_id']];row['deployment_identity']=dict(mode=item['mode'],deployment_manifest_sha256=sha(path),original_recipe_sha256=item['recipe_sha256'],source167_image_equivalence_claimed=False if item['required_independent_recheck']else None)
  if row['status']!='PASS':continue
  last=row['attempts'][-1];runtime=last['actual_runtime'];reasons=[]
  if item['mode']=='DECLARED_PUBLISHED_PREBUILT':
   if runtime['actual_image_id']!=item['expected_image_identity']['image_id']:reasons.append('Published prebuilt actual image differs from frozen Engine identity')
  elif item['required_independent_recheck']:
   trial=Path(last['trial_path']);proof=trial/'agent/EXPLICIT_RECIPE_IMAGE_IDENTITY_R3.json'
   if not trial.parent.name.endswith('original-recipe-recheck-20261102-r3')or not proof.exists():reasons.append('Declared prebuilt unavailable: legacy automatic build remains PROVISIONAL; independent explicit original-recipe recheck required')
   else:
    p=read(proof)
    if p['actual_image_id']!=runtime['actual_image_id']or p['private_image_tag']!=item['private_image_tag']or p['deployment_manifest_sha256']!=sha(path)or p['original_recipe_sha256']!=item['recipe_sha256']:reasons.append('Explicit original recipe identity mismatch')
    actual={x['path']:x['sha256']for x in runtime['container_probe']['public_assets']}
    if any(actual.get(x['target'])!=x['sha256']for x in item.get('image_public_files',[])):reasons.append('Original recipe public input hash not verified in actual container')
    row['deployment_identity'].update(image_identity_proof_path=str(proof),image_identity_proof_sha256=sha(proof),actual_image_id=runtime['actual_image_id'])
  if reasons:row.update(status='UNKNOWN',latest_failure_reasons=row.get('latest_failure_reasons',[])+reasons)
 for field,status in [('passed','PASS'),('failed','FAIL'),('unknown','UNKNOWN'),('running','RUNNING'),('pending','PENDING')]:value[field]=sum(r['status']==status for r in value['tasks'])
 value.update(deployment_manifest_sha256=sha(path),image_identity_binding_source_sha256=sha(Path(__file__)),explicit_recipe_rebuild_not_source167_equivalence=True)
 return value
