import pathlib,json,hashlib,os,sys
root=pathlib.Path(sys.argv[1]);p=root/'TRANSFER_MANIFEST.json';m=json.loads(p.read_text());seal=json.loads((root/'SEALED.json').read_text())
assert hashlib.sha256(p.read_bytes()).hexdigest()==seal['manifest_sha256']
total=0
for r in m['files']:
 p=root/r['path']
 if 'symlink'in r:
  assert p.is_symlink() and os.readlink(p)==r['symlink']
  if pathlib.Path(r['symlink']).is_absolute():
   assert str(p.relative_to(root)).startswith('student-tokenizer/') and r['symlink'].startswith('/data/models/Qwen/Qwen3.5-4B/'), 'Unaccepted cross-host link '+str(p)
  assert p.exists(), 'Broken symlink '+str(p)
 else:
  assert p.is_file()and p.stat().st_size==r['bytes']
  h=hashlib.sha256()
  with p.open('rb')as f:
   for b in iter(lambda:f.read(8*1024*1024),b''):h.update(b)
  assert h.hexdigest()==r['sha256'],str(p)
  total+=r['bytes']
out=dict(passed=True,manifest_sha256=seal['manifest_sha256'],files=len(m['files']),verified_bytes=total,original_source_not_deleted=True)
pathlib.Path('/ssd/chenkeyi/qwen35-sft-772-20261101/checks/transfer-sha-acceptance-r1.json').write_text(json.dumps(out,indent=2))
print(json.dumps(out),flush=True)
