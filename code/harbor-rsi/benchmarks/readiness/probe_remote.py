"""Read-only cache/capacity/registry inspection on an explicitly pinned daemon."""

import argparse
import hashlib
import json
import subprocess
import shlex
from pathlib import Path


def ssh(
    target: str, command: str, *, timeout: int = 30, input: str | None = None
) -> subprocess.CompletedProcess[str]:
    if target.startswith("-"):
        raise ValueError("SSH target cannot be an option")
    return subprocess.run(
        ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10", target, command],
        input=input,
        text=True,
        capture_output=True,
        timeout=timeout,
    )


REGISTRY_SCRIPT = r"""
import concurrent.futures, hashlib, json, sys, urllib.request, urllib.error
images=json.loads(sys.argv[1])
accept='application/vnd.oci.image.index.v1+json, application/vnd.docker.distribution.manifest.list.v2+json, application/vnd.oci.image.manifest.v1+json, application/vnd.docker.distribution.manifest.v2+json'
def fetch(url,headers={}):
 with urllib.request.urlopen(urllib.request.Request(url,headers=headers),timeout=15) as response:
  data=response.read();return json.loads(data),hashlib.sha256(data).hexdigest()
def probe(image):
 try:
  reference=image.split('@',1)[-1] if '@' in image else image.rsplit(':',1)[-1] if ':' in image.rsplit('/',1)[-1] else 'latest'
  repository=image.split('@',1)[0] if '@' in image else image.rsplit(':',1)[0] if ':' in image.rsplit('/',1)[-1] else image
  if '/' not in repository: repository='library/'+repository
  first=repository.split('/')[0]
  if '.' in first or ':' in first:
   return image,{'status':'not_docker_hub','reason':'registry credentials/host require separate review'}
  token,_=fetch('https://auth.docker.io/token?service=registry.docker.io&scope=repository:'+repository+':pull')
  headers={'Authorization':'Bearer '+token['token'],'Accept':accept}
  base='https://registry-1.docker.io/v2/'+repository+'/manifests/'
  manifest,digest=fetch(base+reference,headers)
  platforms=[]
  if 'manifests' in manifest:
   platforms=[m.get('platform',{}) for m in manifest['manifests']]
   selected=next((m for m in manifest['manifests'] if m.get('platform',{}).get('os')=='linux' and m.get('platform',{}).get('architecture')=='amd64'),None)
   if not selected:return image,{'status':'no_linux_amd64','platforms':platforms}
   manifest,platform_digest=fetch(base+selected['digest'],headers)
  else:platform_digest=digest
  config,_=fetch('https://registry-1.docker.io/v2/'+repository+'/blobs/'+manifest['config']['digest'],headers)
  platform={'os':config.get('os'),'architecture':config.get('architecture')}
  if platform!={'os':'linux','architecture':'amd64'}:return image,{'status':'no_linux_amd64','platform':platform,'platforms':platforms}
  layers=manifest.get('layers',[])
  return image,{'status':'available','manifest_sha256':digest,'platform_manifest_sha256':platform_digest,'platform':platform,'platforms':platforms,'compressed_layer_bytes':sum(x['size'] for x in layers),'layers':[{'digest':x['digest'],'bytes':x['size']} for x in layers]}
 except urllib.error.HTTPError as e:return image,{'status':'http_error','code':e.code,'error':str(e)}
 except Exception as e:return image,{'status':'request_failed','error':type(e).__name__+': '+str(e)}
with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
 print(json.dumps(dict(pool.map(probe,images))))
"""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ssh-target", default="aibox-149")
    parser.add_argument("--daemon-id", required=True)
    parser.add_argument("--references", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--registry", action="store_true")
    args = parser.parse_args()
    response = ssh(args.ssh_target, 'docker info --format "{{json .}}"')
    response.check_returncode()
    info = json.loads(response.stdout)
    if info["ID"] != args.daemon_id:
        raise SystemExit("Wrong daemon identity; no image probing performed")
    rows = json.loads(args.references.read_text())
    refs = sorted(
        {
            r["image"]
            for r in rows
            if r["kind"] not in {"internal_stage", "unresolved", "compose_unresolved"}
        }
        | {"alexgshaw/hf-model-inference:20251031", "python:3.12-slim-bookworm"}
    )
    results = {}
    for image in refs:
        p = ssh(args.ssh_target, "docker image inspect " + shlex.quote(image))
        if p.returncode == 0:
            data = json.loads(p.stdout)[0]
            results[image] = {
                "status": "present",
                "id": data["Id"],
                "repo_digests": json.dumps(data["RepoDigests"]),
                "size_bytes": data["Size"],
                "platform": data["Os"] + "/" + data["Architecture"],
            }
        else:
            results[image] = {
                "status": "missing" if "No such image" in p.stderr else "query_failed",
                "returncode": p.returncode,
                "stderr": p.stderr.strip()[:1000],
            }
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "image-probes.json").write_text(json.dumps(results, indent=2) + "\n")
    disk = ssh(args.ssh_target, "df -B1 " + shlex.quote(info["DockerRootDir"])).stdout
    evidence = {
        "daemon_id": info["ID"],
        "docker_root_dir": info["DockerRootDir"],
        "cpus": info["NCPU"],
        "memory_bytes": info["MemTotal"],
        "architecture": info["Architecture"],
        "engine_version": info["ServerVersion"],
        "df": disk,
        "reference_sha256": hashlib.sha256(args.references.read_bytes()).hexdigest(),
        "history_note": "current cache state cannot establish prior pull history",
    }
    (args.output / "engine.json").write_text(json.dumps(evidence, indent=2) + "\n")
    if args.registry:
        # Only GET/token requests to the known image registry. No pulls, builds,
        # daemon changes, port scans or TLS bypass. Tokens never leave the process.
        p = ssh(
            args.ssh_target,
            "python3 - " + shlex.quote(json.dumps(refs)),
            input=REGISTRY_SCRIPT,
            timeout=1200,
        )
        p.check_returncode()
        registry = json.loads(p.stdout)
        (args.output / "registry-probes.json").write_text(
            json.dumps(registry, indent=2) + "\n"
        )
    print(f"inspected {len(results)} exact references; daemon identity verified")


if __name__ == "__main__":
    main()
