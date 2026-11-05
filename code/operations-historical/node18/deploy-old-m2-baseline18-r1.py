"""Install only the sealed, SHA-verified old-study baseline on18 SSD."""
import hashlib
import json
from pathlib import Path
import subprocess
import time

R=Path('/ssd/chenkeyi/qwen35-sft-772-20261101')
S=Path('/data/chenkeyi/qwen35-sft-772-20261101/assets/old-m2-baseline-r1')
def sha(p):
    h=hashlib.sha256()
    with p.open('rb')as f:
        for block in iter(lambda:f.read(8*1024*1024),b''):h.update(block)
    return h.hexdigest()


def main():
    source=S/'OLD_M2_BASELINE_TRANSFER.json';manifest=json.loads(source.read_text())
    assert manifest['old_four_baseline_only']and manifest['not_new_m1_m2_initialization']
    target=R/'assets/old-m2-baseline-r1';staging=R/'staging/old-m2-baseline-r1.partial'
    assert not target.exists()and not staging.exists()
    start=time.monotonic();staging.mkdir()
    subprocess.run(['rsync','-a','--bwlimit=131072',str(S)+'/',str(staging)+'/'],check=True)
    assert sha(staging/source.name)==sha(source)
    for member in manifest['files']:
        p=staging/member['path'];assert p.is_file()and not p.is_symlink()
        assert p.stat().st_size==member['bytes']and sha(p)==member['sha256']
    binding=dict(source=str(S),runtime_model_path=str(target),original17_source=manifest['source'],
        original_weight_sha256=manifest['original_model_sha256'],bytes=manifest['bytes'],
        source_transfer_manifest_sha256=sha(source),all_files_sha256_verified=True,
        no_cross_node_runtime_symlinks=True,old_four_baseline_only=True,
        forbidden_as_new_m1_or_new_m2_initialization=True,originals_preserved=True,
        transfer_seconds=time.monotonic()-start,source_sha256=sha(Path(__file__)))
    (staging/'BASELINE_LOCATION_BINDING.json').write_text(json.dumps(binding,indent=2)+'\n')
    staging.rename(target);(R/'checks/OLD_M2_BASELINE18_DEPLOYMENT.json').write_text(json.dumps(binding,indent=2)+'\n')
    print(json.dumps(binding),flush=True)


if __name__=='__main__':main()
