"""Preserve the timed-out orphan's raw evidence without repairing or grading it."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import time
from foundation.rollouts.export import RolloutView

R=Path('/home/chenkeyi/.local/share/harbor-rsi/qwen35-new772-tb21-20261101')


def main():
    cid='1f800cbff115';identity='53401152bd2a464d8d07cebdf1dc85e9'
    actual=json.loads(subprocess.check_output(['docker','inspect',cid],text=True))[0]
    assert actual['Config']['Labels']['io.harbor.remote-docker.identity']==identity
    assert shutil.disk_usage(R).free>8*1024**3
    root=R/'recovery/e3-controller-oom-20261102-r1/regex-log'
    root.mkdir(parents=True,mode=0o700)
    raw=root/'raw-agent'
    assert not raw.exists(), 'Preserve a previous copy rather than overwriting it'
    subprocess.run(['docker','cp',cid+':/logs/agent',str(raw)],check=True,timeout=900)
    files=[]
    for p in sorted(raw.rglob('*')):
        if not p.is_file():continue
        digest=hashlib.sha256()
        with p.open('rb')as stream:
            for chunk in iter(lambda:stream.read(1024*1024),b''):digest.update(chunk)
        files.append(dict(path=str(p.relative_to(raw)),bytes=p.stat().st_size,sha256=digest.hexdigest()))
    manifest=dict(at=time.time(),source_container=cid,remote_docker_identity=identity,
        raw_agent_files=files,source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        original_result_missing=True,raw_reward=None,primary_classification='UNKNOWN_CONTROLLER_OOM_INTERRUPTED',
        actual_agent_timeout_seconds=10800,raw_recorder_not_repaired_or_redacted=True,
        qualified_success_or_training_trace_not_claimed=True,new_model_calls=0,
        original_task_and_existing_partial_host_copy_unmodified=True)
    p=root/'RAW_ORPHAN_EVIDENCE_MANIFEST.json'
    p.write_text(json.dumps(manifest,indent=2)+'\n')
    try:validation=RolloutView.open(raw/'openharness-rollout').validate()
    except Exception as error:validation=dict(error_type=type(error).__name__,error=str(error))
    result=dict(at=time.time(),raw_manifest_sha256=hashlib.sha256(p.read_bytes()).hexdigest(),
        native_recorder_validation=validation,source_container_retained_for_native_verifier=True,
        primary_classification='UNKNOWN_CONTROLLER_OOM_INTERRUPTED',new_model_calls=0,
        no_repair_or_reward_synthesis=True)
    (root/'RAW_RECORDER_VALIDATION.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(dict(manifest_sha256=result['raw_manifest_sha256'],files=len(files),
        bytes=sum(x['bytes']for x in files),validation=validation)))


if __name__=='__main__':main()
