"""Original-nine completion must never stop a service still owned by common30."""
import copy,importlib,json,time
from pathlib import Path
from unittest.mock import patch
m=importlib.import_module('observe-original-nine18-r1');phase=m.phase
actual=phase.read(m.C/'REMOTE_NATIVE_EVAL_STATUS.json');owner=phase.read(m.C/'NATIVE_ADVANCE_OWNER.json');rows=[]
for terminal in [False,True]:
 fixture=copy.deepcopy(actual);item=fixture['modes']['new-m1-epoch3-unstarted'];item['complete']=dict(terminal=5,original_started_trials_rerun=0)if terminal else None
 for value in item['original_orphans'].values():value['terminal_evidence_exists']=True
 saved={};state={}
 with patch.object(m.legacy,'remote',return_value=fixture),patch.object(phase,'save',side_effect=lambda p,v:saved.update({str(p):v})),patch.object(phase,'read',side_effect=lambda p:saved[str(p)]),patch.object(m.legacy.serving,'stop',side_effect=AssertionError('Never stop shared model serving')),patch.object(m.legacy,'request',side_effect=AssertionError('Never duplicate native dispatch')):
  m.advance(owner,state)
 marker=str(m.C/'EPOCH3_ORIGINAL_NINE_LIFECYCLE_COMPLETE_R1.json')
 assert(marker in saved)==terminal
 if terminal:assert saved[marker]['serving_retained_for_same_checkpoint_common30']
 rows.append(dict(original_nine_terminal=terminal,serving_stopped=False,trials_dispatched=0,lifecycle_marker_written=marker in saved))
result=dict(passed=True,at=time.time(),cases=rows,actual_model_or_task_calls=0,source_sha256=phase.sha(Path(m.__file__)),test_source_sha256=phase.sha(Path(__file__)),same_model_service_survives_original_nine_completion=True)
proof=m.R/'checks/COMMON30_SHARED_SERVING_LIFECYCLE_ACCEPTANCE_R1.json';assert not proof.exists();proof.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
