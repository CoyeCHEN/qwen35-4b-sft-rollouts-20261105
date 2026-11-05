"""Record literal published JSON inputs, keeping private verifier code outside the image."""
from pathlib import Path
import hashlib,json,re
r=Path('/home/chenkeyi/.local/share/harbor-rsi/qwen35-new-cf500-tmax500-20261029');ident='task_000173_27f3fc33'
source=r/'sources/tmax/original-tasks'/ident
raw=(source/'container.def').read_bytes();text=raw.decode();files=[]
for match in re.finditer(r"cat << 'EOF' > (/tests/[^\n]+)\n(.*?)^EOF$",text,re.S|re.M):
 path,body=match.groups();json.loads(body)
 files.append(dict(path=path,sha256=hashlib.sha256(body.encode()).hexdigest()))
assert len(files)==4 and all(p['path'].startswith('/tests/corpus/') and p['path'].endswith('.json') for p in files)
assert 'test_corpus_directories_exist' in (source/'test_initial_state.py').read_text()
report=dict(task_id=ident,root='/tests',files=files,source_container_def_sha256=hashlib.sha256(raw).hexdigest(),
 source_initial_state_test_sha256=hashlib.sha256((source/'test_initial_state.py').read_bytes()).hexdigest(),
 review='Literal published configuration examples, required by the official initial-state tests. No official test code, oracle or hidden answer copied into the image.',
 native_upload_semantics='Existing Harbor upload_dir merges source_dir/. into target; does not replace the published corpus directory. Real native NOP verifier remains required.',
 raw_source_modified=False,model_calls=0,teacher_attempts=0)
p=r/'checks/public-input-boundaries'/(ident+'.json');p.parent.mkdir(exist_ok=True)
with p.open('x') as stream:stream.write(json.dumps(report,indent=2))
print(json.dumps(report))
