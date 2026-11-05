"""Select the same pinned tokenizer.json backend through a separate HF resource.

Original model/tokenizer/template/processor files and all existing caches remain
unchanged. This resource is a candidate until both runtimes and all targets pass.
"""
import datetime
import hashlib
import json
from pathlib import Path

source=Path('/data/models/Qwen/Qwen3.5-4B')
target=Path('/ssd/chenkeyi/qwen35-new-cf500-tmax500-20261029/student-tokenizer-r155')
target.mkdir(exist_ok=False)
sha=lambda path:hashlib.sha256(path.read_bytes()).hexdigest()
original=json.loads((source/'tokenizer_config.json').read_text())
changed=dict(original,tokenizer_class='PreTrainedTokenizerFast')
if {key for key in set(original)|set(changed) if original.get(key)!=changed.get(key)}!={'tokenizer_class'}:
    raise ValueError('Tokenizer selection change was not exactly one declared field')
members={}
for path in source.iterdir():
    if path.name.startswith('.') or not path.is_file() or path.name=='tokenizer_config.json':continue
    (target/path.name).symlink_to(path.resolve())
    if path.suffix not in ['.safetensors','.bin','.pt']:
        members[path.name]=dict(original_path=str(path),sha256=sha(path),mode='Read-only source symlink; original bytes unchanged')
(target/'tokenizer_config.json').write_text(json.dumps(changed,ensure_ascii=False,indent=2))
manifest=dict(created_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
    original_model_directory=str(source),original_model_revision='851bf6e806efd8d0a36b00ddf55e13ccb7b8cd0a',
    original_tokenizer_config_sha256=sha(source/'tokenizer_config.json'),derived_tokenizer_config_sha256=sha(target/'tokenizer_config.json'),
    explicit_selection_change=dict(field='tokenizer_class',original=original.get('tokenizer_class'),selected='PreTrainedTokenizerFast'),
    tokenizer_json_sha256=sha(source/'tokenizer.json'),unchanged_source_members=members,
    model_weights_copied=False,original_files_modified=False,teacher_contract_changed=False,
    admission='CANDIDATE_ONLY_REQUIRES_BOTH_RUNTIME_PREFIX_AND_FULL_TARGET_REVALIDATION',source_sha256=sha(Path(__file__)))
with (target/'SOURCE_MANIFEST_R155.json').open('x') as stream:json.dump(manifest,stream,indent=2)
print(json.dumps(dict(resource=str(target),tokenizer_json_sha256=manifest['tokenizer_json_sha256'],derived_config_sha256=manifest['derived_tokenizer_config_sha256'],original_files_modified=False)))
