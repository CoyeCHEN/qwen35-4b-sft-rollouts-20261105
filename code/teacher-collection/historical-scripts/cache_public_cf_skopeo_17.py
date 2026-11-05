"""Cache exact public OCI bytes with native Skopeo; no Docker daemon dependency."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import time

ROOT=Path('/ssd/chenkeyi/qwen35-new-cf500-tmax500-20261029/registry/tasks-skopeo-r5')
TOOLS=Path('/home/chenkeyi/workspace/RSI/runtime-evidence/qwen35-new-cf500-tmax500-20261029/tools/skopeo')


def sha_stream(stream):
    digest=hashlib.sha256()
    for block in iter(lambda:stream.read(1024*1024),b''):digest.update(block)
    return digest.hexdigest()


def main():
    source=json.load(sys.stdin);ident=source['task_id'];digest=source['top_manifest_digest']
    if not ident.replace('_','').replace('-','').isalnum() or not digest.startswith('sha256:'):
        raise ValueError('Invalid frozen public identity')
    if source['status']!='OFFICIAL_REGISTRY_IDENTITY_FROZEN' or source['pinned']!='aweaiteam/calibforge@'+digest:
        raise ValueError('Unapproved public source')
    if source['media_type'] not in ('application/vnd.oci.image.manifest.v1+json','application/vnd.docker.distribution.manifest.v2+json'):
        raise ValueError('Multi-platform identity requires explicit original-platform audit')
    directory=ROOT/ident;directory.mkdir(parents=True,exist_ok=True);receipt=directory/'cache.json'
    if receipt.exists():
        value=json.loads(receipt.read_text())
        if value['status']=='PINNED_PUBLIC_IMAGE_ARCHIVE_READY':print(json.dumps(value));return
        raise RuntimeError('Preserved failed cache receipt requires inspection')
    if shutil.disk_usage(ROOT).free<100*1024**3:raise RuntimeError('100GiB cache headroom required')
    started=time.monotonic();archive=directory/'image.oci.tar'
    value=dict(task_id=ident,pinned=source['pinned'],source=source,model_calls=0,teacher_attempts=0,
        status='COPYING_OFFICIAL_OCI_WITH_PRESERVED_DIGESTS',cache_daemon=None,
        cache_transport='Skopeo 1.4.1 user-local; official public registry -> OCI archive',
        destination_controller='aibox-149',teacher_backend_unchanged=True)
    receipt.write_text(json.dumps(value,indent=2))
    try:
        # Match the already configured public Docker download route in this child only.
        proxy_config=json.loads(Path('/etc/docker/daemon.json').read_text()).get('proxies',{})
        transport_env=os.environ.copy()
        transport_env["GODEBUG"]="http2client=0"
        value["public_cache_http2_disabled"] = True
        for key,name in [('http-proxy','HTTP_PROXY'),('https-proxy','HTTPS_PROXY'),('no-proxy','NO_PROXY')]:
            if key in proxy_config:transport_env[name]=proxy_config[key]
        value['public_cache_proxy_basis']='Existing /etc/docker/daemon.json proxies, scoped to Skopeo child; teacher environment unchanged'
        with (directory/'copy.log').open('x') as log:
            subprocess.run([str(TOOLS/'root/usr/bin/skopeo'),'--policy',str(TOOLS/'root/etc/containers/policy.json'),
                'copy','--retry-times','2','--src-no-creds','--src-tls-verify=true',
                'docker://docker.io/'+source['pinned'],'oci-archive:'+str(archive)+':'+ident],
                stdout=log,stderr=subprocess.STDOUT,timeout=900,check=True,env=transport_env)
        with tarfile.open(archive,'r') as tar:
            manifest_name='blobs/sha256/'+digest.split(':',1)[1]
            raw=tar.extractfile(manifest_name).read()
            if hashlib.sha256(raw).hexdigest()!=digest.split(':',1)[1]:raise ValueError('Original manifest changed')
            manifest=json.loads(raw);checked=[]
            for descriptor in [manifest['config'],*manifest['layers']]:
                expected=descriptor['digest'].split(':',1)[1]
                with tar.extractfile('blobs/sha256/'+expected) as stream:actual=sha_stream(stream)
                if actual!=expected:raise ValueError('Official OCI content identity mismatch')
                checked.append(descriptor)
        with archive.open('rb') as stream:archive_sha=sha_stream(stream)
        value.update(status='PINNED_PUBLIC_IMAGE_ARCHIVE_READY',archive=str(archive),archive_sha256=archive_sha,
            archive_bytes=archive.stat().st_size,image_id=digest,config_digest=manifest['config']['digest'],
            verified_original_blob_descriptors=checked,original_manifest_sha256=digest.split(':',1)[1],
            all_original_manifest_config_layer_hashes_verified=True)
    except (OSError,ValueError,subprocess.SubprocessError) as error:
        value.update(status='PUBLIC_CACHE_FAILED',error_type=type(error).__name__,error=str(error)[:300])
    value['seconds']=time.monotonic()-started;receipt.write_text(json.dumps(value,indent=2));print(json.dumps(value))
    if value['status']!='PINNED_PUBLIC_IMAGE_ARCHIVE_READY':raise RuntimeError('Exact public OCI cache failed')


if __name__=='__main__':main()
