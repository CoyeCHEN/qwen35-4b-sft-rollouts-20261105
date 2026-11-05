"""Prepare frozen CF500 using a proven public cache path; no teacher dispatch.

149 remains the sole Harbor controller/engine. 17 pulls immutable public images
and exports archives only. One cache transfer at a time, 8 MiB/s, no global edits.
"""
from collections import Counter
import argparse
import copy
import datetime
import hashlib
import json
from pathlib import Path
import shlex
import shutil
import subprocess
import time
import tomllib
from harbor.models.task.config import TaskConfig

from prepare_cf_images import command, image_info, DISK_RESERVE

ROOT=Path('/home/chenkeyi/.local/share/harbor-rsi/qwen35-new-cf500-tmax500-20261029')
REMOTE='/home/chenkeyi/workspace/RSI/runtime-evidence/qwen35-new-cf500-tmax500-20261029/scripts/cache_public_cf_staged_17.py'
SOCKET='/home/chenkeyi/.ssh/cf17-20261028.sock'
HOST='chenkeyi@180.163.192.17'


def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):h.update(block)
    return h.hexdigest()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--task-id',help='Prepare one task already in the frozen 500')
    args=parser.parse_args()
    out=ROOT/'checks/cf-environments-oci-r5';out.mkdir(exist_ok=True)
    transfers=ROOT/'sources/public-image-transfers';transfers.mkdir(exist_ok=True)
    rows=list(map(json.loads,(ROOT/'manifests/CALIBFORGE_500_TASKS.jsonl').open()))
    canary=json.loads((ROOT/'manifests/SAMPLING_MANIFEST.json').read_text())['pools']['calibforge']['canary_task_ids']
    rows.sort(key=lambda r:(canary.index(r['task_id']) if r['task_id'] in canary else 8,r['task_id']))
    if args.task_id:
        rows=[r for r in rows if r['task_id']==args.task_id]
        if len(rows)!=1:raise ValueError('Expected exactly one frozen CF task')
    report_file=ROOT/'checks'/('cf-oci-r5-'+args.task_id+'.json' if args.task_id else 'cf-image-preparation-oci-r5.json')
    counts=Counter()
    report=dict(status='PREPARING_FROZEN_IMAGES',planned_tasks=len(rows),model_attempts=0)
    daemon=json.loads(command(['docker','info','--format','{{json .}}']).stdout)['ID']
    if daemon!='c6e16cdf-e878-4cc5-84c8-78a56c54b5c5':raise ValueError('Controller engine changed')
    for row in rows:
        ident=row['task_id']; receipt=out/(ident+'.json')
        if receipt.exists():counts[json.loads(receipt.read_text())['status']]+=1;continue
        if shutil.disk_usage(ROOT).free<DISK_RESERVE:
            report.update(status='WAITING_FOR_100GIB_DISK_HEADROOM',next_task_id=ident,counts=dict(counts))
            report_file.write_text(json.dumps(report,indent=2));return
        source=Path(row['source_path']);before=(source/'task.toml').read_bytes()
        if hashlib.sha256(before).hexdigest()!=row['task_toml_sha256']:raise ValueError('Frozen task changed')
        public=json.loads((ROOT/'checks/cf-public-image-identities'/(ident+'.json')).read_text())
        if public['status']!='OFFICIAL_REGISTRY_IDENTITY_FROZEN':raise ValueError('Public image resolution pending')
        record=dict(task_id=ident,image=row['docker_image'],pinned_image=public['pinned'],daemon_id=daemon,
            checked_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),model_attempts=0,
            original_task_toml_sha256=row['task_toml_sha256'],previous_check=str(ROOT/'checks/cf-environments'/(ident+'.json')))
        name='cf500-preflight-oci-r5-'+hashlib.sha256(ident.encode()).hexdigest()[:16];start=time.monotonic()
        try:
            info=image_info(row['docker_image'])
            if info is None:
                ssh=['ssh','-S',SOCKET,'-o','BatchMode=yes','-o','ControlMaster=no','-o','ProxyCommand=false',HOST]
                reply=subprocess.run(ssh+['python3 '+shlex.quote(REMOTE)],input=json.dumps(public),capture_output=True,text=True,timeout=1900)
                if reply.returncode:raise RuntimeError('Pinned public cache helper failed; remote receipt retained')
                cached=json.loads(reply.stdout)
                if cached['status']!='PINNED_PUBLIC_IMAGE_ARCHIVE_READY' or cached['pinned']!=public['pinned']:
                    raise ValueError('Public cache identity mismatch')
                archive=transfers/(ident+'.tar')
                with (out/(ident+'.transfer.log')).open('x') as log:
                    subprocess.run(['rsync','-a','--bwlimit=8192','-e',shlex.join(ssh[:-1]),
                        HOST+':'+cached['archive'],str(archive)],check=True,stdout=log,stderr=subprocess.STDOUT,timeout=1800)
                if sha(archive)!=cached['archive_sha256']:raise ValueError('Image archive transport hash mismatch')
                with (out/(ident+'.load.log')).open('x') as log:
                    subprocess.run(['docker','image','load','--input',str(archive)],check=True,stdout=log,stderr=subprocess.STDOUT,timeout=900)
                info=image_info(cached['image_id'])
                if info is None or info['Id']!=cached['image_id']:raise ValueError('Loaded public image identity mismatch')
                current=image_info(row['docker_image'])
                if current and current['Id']!=info['Id']:raise ValueError('Existing original tag conflicts; no overwrite')
                if current is None:command(['docker','tag',info['Id'],row['docker_image']]).check_returncode()
                record['public_cache_transfer']=cached
                # The verified source archive remains on 17; remove this task's duplicate transport file only.
                archive.unlink()
            if public['media_type'] in ['application/vnd.oci.image.manifest.v1+json','application/vnd.docker.distribution.manifest.v2+json']:
                if info['Id']!=public['top_manifest_digest']:raise ValueError('Actual image differs from official registry manifest')
            raw=tomllib.loads(before.decode())
            source_resource_fields=copy.deepcopy(raw.get('environment',{}))
            native_task=TaskConfig.model_validate(raw)
            normalized=native_task.environment
            resources=dict(cpus=normalized.cpus,memory_mb=normalized.memory_mb,storage_mb=normalized.storage_mb,gpus=normalized.gpus)
            record['original_resource_fields']=source_resource_fields
            record['resource_normalization']='Native Harbor TaskConfig; memory/storage unit strings preserved semantically'
            record['requested_probe_cpus']=normalized.cpus
            record['requested_probe_memory_bytes']=normalized.memory_mb*1024**2
            if resources.get('gpus',0):raise ValueError('GPU task needs explicit resource acceptance')
            checked=command(['docker','run','--rm','--name',name,'--label','rsi.campaign='+ROOT.name,
                '--cpus',str(resources.get('cpus',1)),'--memory',str(int(resources.get('memory_mb',2048))*1024**2),
                '--entrypoint','/bin/bash',info['Id'],'-lc',
                'set -eu; pwd -P; id; test -w .; command -v bash; test ! -e /tests; test ! -e /solution; '
                'probe=.cf500-preflight-$$; printf probe > "$probe"; rm -- "$probe"; '
                'if test -e /sys/fs/cgroup/memory.max; then cat /sys/fs/cgroup/memory.max /sys/fs/cgroup/cpu.max; fi; '
                'getent hosts api.deepseek.com; command -v python3 || true'],timeout=90)
            record.update(status='IMAGE_IDENTITY_AND_BASIC_SETUP_PASSED' if checked.returncode==0 else 'BASIC_SETUP_FAILED',
                image_id=info['Id'],image_size_bytes=info['Size'],probe_returncode=checked.returncode,
                probe_stdout=checked.stdout[:16000],probe_stderr=checked.stderr[:4000],
                original_resources=resources,agent_timeout_override=max(raw.get('agent',{}).get('timeout_sec',0),10800),
                original_verifier_timeout=raw.get('verifier',{}).get('timeout_sec'),
                native_agent_install_and_verifier_acceptance='Required separately; no Python-in-base requirement')
        except (OSError,ValueError,RuntimeError,subprocess.SubprocessError) as error:
            record.update(status='ENVIRONMENT_PREPARATION_FAILED',error_type=type(error).__name__,error=str(error)[:500])
        finally:
            cleaned=command(['docker','rm','-f',name]);record['cleanup_confirmed']=cleaned.returncode==0 or 'No such container' in cleaned.stderr
        if (source/'task.toml').read_bytes()!=before:raise ValueError('Original task changed')
        record.update(seconds=time.monotonic()-start,disk_free_bytes=shutil.disk_usage(ROOT).free)
        receipt.write_text(json.dumps(record,indent=2));counts[record['status']]+=1
        report.update(observed_tasks=sum(counts.values()),counts=dict(counts),next_task_id=None)
        report_file.write_text(json.dumps(report,indent=2))
        print(json.dumps(dict(task_id=ident,status=record['status'],seconds=record['seconds'])),flush=True)
    report['status']='ALL_FROZEN_IMAGES_CHECKED_VERIFIER_ADMISSION_SEPARATE'
    report_file.write_text(json.dumps(report,indent=2))


if __name__=='__main__':main()
