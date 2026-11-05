"""Verify the published source snapshot without installing Torch or private Harness."""
import ast
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
manifest = json.loads((ROOT / 'metadata/PUBLIC_SOURCE_FILES.json').read_text())
errors = []
for row in manifest['files']:
    p = ROOT / row['path']
    if not p.is_file() or p.is_symlink():
        errors.append(row['path'] + ': missing or symlink')
    elif hashlib.sha256(p.read_bytes()).hexdigest() != row['sha256']:
        errors.append(row['path'] + ': SHA256 mismatch')
count = 0
for p in (ROOT / 'code').rglob('*.py'):
    try:
        ast.parse(p.read_bytes(), filename=str(p.relative_to(ROOT)))
        count += 1
    except (SyntaxError, UnicodeError) as error:
        errors.append(str(error))
for p in (ROOT / 'code').rglob('*'):
    if p.is_file() and (p.suffix in {'.whl', '.safetensors', '.arrow', '.npz', '.pt', '.pth'} or p.name == '.env'):
        errors.append(str(p.relative_to(ROOT)) + ': unexpected data/binary artifact')
print(json.dumps({'files_verified': len(manifest['files']), 'python_files_parsed': count,
                  'errors': errors, 'private_harness_required_for_execution': True}, indent=2))
raise SystemExit(bool(errors))
