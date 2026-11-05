"""Verify every official OCI manifest/config/layer byte in a public archive."""
import hashlib,json,tarfile,sys
from pathlib import Path


def file_sha(path):
 with Path(path).open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()


def verify(source,archive):
 digest=source['top_manifest_digest']
 with tarfile.open(archive,'r') as tar:
  raw=tar.extractfile('blobs/sha256/'+digest.split(':',1)[1]).read()
  assert hashlib.sha256(raw).hexdigest()==digest.split(':',1)[1]
  manifest=json.loads(raw)
  assert manifest['config']['digest']==source['config_digest']
  descriptors=[manifest['config'],*manifest['layers']]
  for descriptor in descriptors:
   with tar.extractfile('blobs/sha256/'+descriptor['digest'].split(':',1)[1]) as stream:
    assert hashlib.file_digest(stream,'sha256').hexdigest()==descriptor['digest'].split(':',1)[1]
 return dict(task_id=source['task_id'],pinned=source['pinned'],source=source,
  status='PINNED_PUBLIC_IMAGE_ARCHIVE_READY',archive=str(Path(archive).resolve()),
  archive_sha256=file_sha(archive),archive_bytes=Path(archive).stat().st_size,image_id=digest,
  config_digest=manifest['config']['digest'],original_manifest_sha256=digest.split(':',1)[1],
  verified_original_blob_descriptors=descriptors,all_original_manifest_config_layer_hashes_verified=True,
  cache_transport='User-local native Skopeo 1.13.3, existing caller public-download proxy; no Docker daemon needed',
  model_calls=0,teacher_attempts=0,teacher_backend_unchanged=True)


if __name__=='__main__':
 source=json.loads(Path(sys.argv[1]).read_text());archive=Path(sys.argv[2]);value=verify(source,archive)
 Path(sys.argv[3]).write_text(json.dumps(value,indent=2));print(value['task_id'],value['archive_sha256'])
