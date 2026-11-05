"""Sole persistent native owner for the latest user evaluation scope."""
import fcntl
import importlib
import json
import os
from pathlib import Path
import socket
import sys
import time

R=Path('/ssd/chenkeyi/qwen35-sft-772-20261101');E=R/'formal-native-eval-r1'
C=Path('/data/chenkeyi/qwen35-sft-772-20261101/control')
sys.path[:0]=[str(R),str(E/'scripts')]
phase=importlib.import_module('diagnostic150-phase18-r1')
winner=importlib.import_module('winner267-phase18-r1')
legacy=importlib.import_module('phase_progression18_r14')
readouts=importlib.import_module('new-validation-readouts18-r3')


def main():
    with(C/'unique-native-advance.lock').open('a')as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        release=phase.read(R/'checks/USER_DIAG150_EXECUTION_RELEASE_R1.json')
        for name,digest in release['source_sha256'].items():assert phase.sha(R/name)==digest,name
        scope=phase.read(C/'USER_EVALUATION_SCOPE_OVERRIDE_R1.json');assert scope['winner_full_n3_expected']==267
        owner=dict(kind='UNIQUE_NATIVE_ADVANCE_NODE18',host=socket.gethostname(),pid=os.getpid(),
            boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
            start_ticks=Path('/proc/self/stat').read_text().rsplit(')',1)[1].split()[19],
            entry='existing_native_harbor_user_evaluation',deployment_revision='r20-user-five30-winner267-eight-gpu',
            controller_unit='qwen35-772-native-advance-node18-20261102-r20.service',
            workspace=str(R/'new-sft/workspace'),collection_closed=True,started_at=time.time(),
            old801_superseded_by_explicit_user_update=True,old_four_deferred_until_selected267_terminal=True)
        phase.save(C/'NATIVE_ADVANCE_OWNER.json',owner)
        while True:
            state=dict(at=time.time(),owner=owner,old_801_auto_dispatch_disabled=True,
                user_scope='FIVE_MODELS_COMMON30_THEN_HIGHEST_CONFIRMED_CORRECT_MODEL_89_N3',old_four_gpu_dispatch_allowed=False)
            try:legacy.diagnostics(owner,state)
            except Exception as error:state['legacy_original_inflight_status_error']=repr(error)
            try:readouts.advance(state)
            except Exception as error:state['unique_validation_readout_blocker']=repr(error)
            try:
                if not(R/'checks/WINNER_FROM_COMMON30_SELECTION_R1.json').exists():phase.advance(owner,state)
                winner.advance(owner,state)
            except Exception as error:state.update(status='USER_EVALUATION_REQUIRES_INSPECTION',blocker=repr(error))
            phase.save(C/'NATIVE_ADVANCE_STATUS.json',state)
            with(R/'new-sft/workspace/logs/native-advance-events.jsonl').open('a')as stream:stream.write(json.dumps(state)+'\n')
            print(json.dumps(state),flush=True)
            time.sleep(20)


if __name__=='__main__':main()
