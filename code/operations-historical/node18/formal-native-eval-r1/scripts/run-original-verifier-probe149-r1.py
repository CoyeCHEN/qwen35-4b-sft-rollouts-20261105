"""Official unchanged regex-log NOP/Verifier lifecycle; independent from 801 model Trials."""
import asyncio
import json
import os
from pathlib import Path
from harbor.job import Job
from harbor.models.job.config import JobConfig

B=Path('/home/chenkeyi/.local/share/harbor-rsi')
R=B/'qwen35-new772-tb21-20261101'


async def main():
    os.environ['SSH_AUTH_SOCK']=str(B/'near-r3-20261015/auth.sock')
    cfg=json.loads((R/'configs/formal-native-job.json').read_text())
    task=next(x for x in cfg['tasks']if Path(x['path']).name=='regex-log')
    profile=json.loads((B/'tb21-teacher-max-20261023/configs/environment-profiles.json').read_text())['terminal-bench/regex-log']
    cfg.update(job_name='qwen35-new772-official-verifier-nop-r1',n_attempts=1,n_concurrent_trials=1,
        tasks=[task],agents=[dict(name='nop')],environment=profile['environment'],verifier=profile['verifier'])
    cfg['environment']['kwargs'].update(staging_root=str(R/'staging'),project_namespace='q35new772verifierprobe')
    assert not (R/'jobs'/cfg['job_name']).exists()
    job=await Job.create(JobConfig.model_validate(cfg))
    result=await job.run();assert len(result.trial_results)==1
    trial=result.trial_results[0]
    proof=dict(official_task='regex-log',official_task_and_verifier_modified=False,actual_teacher_or_student_model_attempts=0,
        excluded_from_801=True,native_job_dir=str(job.job_dir),trial_id=str(trial.id),
        verifier=trial.verifier_result.model_dump(mode='json')if trial.verifier_result else None,
        exception=trial.exception_info.model_dump(mode='json')if trial.exception_info else None,
        infrastructure_errors=[x.model_dump(mode='json')if hasattr(x,'model_dump')else x for x in trial.infrastructure_errors])
    (R/'checks/OFFICIAL_VERIFIER_NOP_ACCEPTANCE_R1.json').write_text(json.dumps(proof,indent=2)+'\n')
    assert trial.exception_info is None and not trial.infrastructure_errors
    assert trial.verifier_result is not None and trial.verifier_result.return_code==0
    assert trial.verifier_result.rewards['reward']==0,'NOP is an expected legal zero, never synthetic success'
    print(json.dumps(proof))


if __name__=='__main__':asyncio.run(main())
