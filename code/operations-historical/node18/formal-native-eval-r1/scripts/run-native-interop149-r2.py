"""One synthetic engineering fixture through unmodified Harbor lifecycle, excluded from TB801."""
import asyncio
import copy
import json
from pathlib import Path
from harbor.job import Job
from harbor.models.job.config import JobConfig

R=Path('/home/chenkeyi/.local/share/harbor-rsi/qwen35-new772-tb21-20261101')


async def main():
    fixture=R/'diagnostics/native-interop-fixture-r2'
    assert not fixture.exists(),'Never silently repeat an existing engineering trial'
    (fixture/'environment').mkdir(parents=True);(fixture/'tests').mkdir()
    (fixture/'instruction.md').write_text('Engineering protocol check in the current workspace: use bash to create /tmp/qwen35-interop.txt containing alpha; use read to inspect it; use edit_patch to replace alpha with beta; read it again and call finish. This is a tiny local test, not a benchmark problem.\n')
    (fixture/'task.toml').write_text('''version = "1.0"
[metadata]
category = "engineering-protocol-fixture"
difficulty = "easy"
[agent]
timeout_sec = 300
[verifier]
timeout_sec = 120
[environment]
build_timeout_sec = 60
docker_image = "alexgshaw/build-cython-ext:20251031"
cpus = 1
memory_mb = 2048
storage_mb = 10240
''')
    (fixture/'tests/test.sh').write_text('''#!/bin/bash
set -eu
mkdir -p /logs/verifier
if test -f /tmp/qwen35-interop.txt && grep -qx beta /tmp/qwen35-interop.txt; then
  printf '1' > /logs/verifier/reward.txt
else
  printf '0' > /logs/verifier/reward.txt
fi
''')
    cfg=json.loads((R/'configs/formal-native-job.json').read_text())
    cfg.update(job_name='qwen35-new772-native-interop-r2',n_attempts=1,n_concurrent_trials=1,
        tasks=[dict(path=str(fixture))],agents=[copy.deepcopy(cfg['agents'][0])])
    cfg['agents'][0]['override_timeout_sec']=300
    cfg['environment']['kwargs']['project_namespace']='q35new772interop'
    cfg['agents'][0]['env']={'OPENAI_API_KEY':'${OPENAI_API_KEY}'}
    job=await Job.create(JobConfig.model_validate(cfg))
    result=await job.run()
    assert len(result.trial_results)==1
    trial=result.trial_results[0]
    assert trial.exception_info is None, trial.exception_info
    assert trial.verifier_result is not None and trial.verifier_result.rewards.get('reward')==1, trial.verifier_result
    (R/'checks/NATIVE_INTEROP_JOB_R2.json').write_text(json.dumps(dict(
        excluded_from_801=True,synthetic_engineering_fixture=True,official_task_or_verifier_modified=False,
        native_job_dir=str(job.job_dir),native_job_id=str(result.id),finished_at=str(result.finished_at)),indent=2)+'\n')


if __name__=='__main__':asyncio.run(main())
