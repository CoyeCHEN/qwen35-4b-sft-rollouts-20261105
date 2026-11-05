"""Merge immutable cohort proofs; reject changed identities and preserve the previous index."""
import hashlib,json,shutil,sys
from pathlib import Path
root=Path(sys.argv[1]); incoming=Path(sys.argv[2]); cohort=sys.argv[3]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
index=root/'checks/STUDENT_AUDIT_TRIALS.json'
old=json.loads(index.read_text()) if index.exists() else {'entries':[],'proofs':{}}
new=json.loads(incoming.read_text()); entries={x['trial_id']:x for x in old['entries']}
for item in new['entries']:
 if item['trial_id'] in entries and entries[item['trial_id']]!=item:raise ValueError('Conflicting trial proof')
 entries[item['trial_id']]=item
for name,proof in new['proofs'].items():
 source=incoming.parent.parent/proof['relative_path'];assert sha(source)==proof['sha256']
 target=root/proof['relative_path'];target.parent.mkdir(parents=True,exist_ok=True)
 if target.exists():assert sha(target)==sha(source)
 else:shutil.copyfile(source,target)
 key=cohort+'/'+name;fixed={**proof,'path':str(target)}
 if key in old['proofs']:assert old['proofs'][key]==fixed
 old['proofs'][key]=fixed
if index.exists():
 frozen=index.parent/'student-proof-index-history'/(sha(index)+'.json');frozen.parent.mkdir(exist_ok=True)
 if not frozen.exists():shutil.copyfile(index,frozen)
old['entries']=list(entries.values());old['scope']='Merged exact-trial immutable native projection, loader and serving proofs; admission separately verified'
old['does_not_approve_reward_or_task_provenance']=True
output=index.with_suffix('.tmp');output.write_text(json.dumps(old,indent=2));output.replace(index)
print(json.dumps({'trials':len(entries),'targets':sum(len(x['original_call_ids']) for x in entries.values())}))
