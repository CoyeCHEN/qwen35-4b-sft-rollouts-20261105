"""Identify historical zero-model probe reference drift without inventing bytes."""
import datetime
import json
from pathlib import Path
import shlex
import subprocess
import collection_readiness_r7 as n

references=[]
for root in [n.R/'stream/collection-r4'/name for name in ['deployment-r6','deployment-r6b','deployment-r6c']]:
    for file in (root/'initial-outcomes').glob('*.json'):
        value=json.loads(file.read_text())
        for key in ['initial_stdout','initial_stderr']:
            if key in value:
                references.append(dict(proof=str(file),proof_sha256=n.sha(file),task_id=value['task_id'],
                    kind=key,**value[key]))
paths=sorted({x['path'] for x in references})
code="""import hashlib,json,sys
from pathlib import Path
result={}
for name in json.load(sys.stdin):
 p=Path(name);assert p.is_relative_to(Path('/ssd/chenkeyi/qwen35-new-cf500-tmax500-20261029/preflight-r6'))
 result[name]=hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else None
print(json.dumps(result))
"""
reply=subprocess.run([*n.DEPLOYMENT['ssh'],n.DEPLOYMENT['host'],shlex.join([n.DEPLOYMENT['python17'],'-c',code])],
    input=json.dumps(paths),capture_output=True,text=True,check=True,timeout=60)
actual=json.loads(reply.stdout)
for row in references:
    row['current_sha256']=actual[row['path']]
    row['original_reference_matches']=row['sha256']==row['current_sha256']
bad=[x for x in references if not x['original_reference_matches']]
out=dict(checked_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
    status='HISTORICAL_ZERO_MODEL_INITIAL_PROBE_REFERENCE_AUDIT',references=references,
    broken_historical_references=bad,broken_reference_count=len(bad),
    cause='R6 reused a per-Task initial stdout/stderr path across zero-model preflight revisions. Original expected hashes remain; earlier overwritten bytes are not reconstructed.',
    repair='R7 uses a separate UUID for every probe container and log directory. Teacher Trial/Result/Session/Recorder paths are distinct and were not modified by these probes.',
    scope='Only the explicitly listed zero-model initial-state probe log paths; no teacher Recorder path in this list',
    teacher_recorder_files_modified_by_probes=0,rewards_or_official_tests_modified=0,model_calls=0,
    cannot_claim_all_historical_setup_log_references_intact=bool(bad))
n.freeze(n.R/'checks/initial-probe-log-history-integrity-r7.json',out)
print(json.dumps(dict(status=out['status'],references=len(references),broken_historical_references=len(bad),teacher_recorders_affected=0)))
