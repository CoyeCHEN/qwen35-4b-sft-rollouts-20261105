"""Persistent invocation of the existing fixed two-stage native advance entry."""
import fcntl
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time

R=Path('/ssd/chenkeyi/qwen35-sft-772-20261101')
W=R/'new-sft/workspace'
C=Path('/data/chenkeyi/qwen35-sft-772-20261101/control')
SRC=R/'new-sft/source-r4/repository'
sys.path.insert(0,str(SRC))
os.environ['OPENHARNESS_SFT_WORKSPACE']=str(W)
from sft.runtime.checkpoint_archive import atomic_json,sha256
from sft.runtime.identity import training_source_sha256
from sft.runtime.public_stages import advance


def main():
    with (C/'unique-native-advance.lock').open('a') as owner:
        fcntl.flock(owner,fcntl.LOCK_EX|fcntl.LOCK_NB)
        old=subprocess.check_output(['systemctl','--user','show','qwen35-old-four-node18-20261101-r1',
            '--property=ActiveState','--value'],text=True).strip()
        if old in ('active','activating'):raise ValueError('Previous writable sequence is still active')
        authority=dict(kind='UNIQUE_NATIVE_ADVANCE_NODE18',host=socket.gethostname(),pid=os.getpid(),
            boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
            start_ticks=Path('/proc/self/stat').read_text().rsplit(')',1)[1].split()[19],
            entry='sft.runtime.public_stages.advance',workspace=str(W),
            collection_closed=True,old_four_deferred_until_801_terminal=True,started_at=time.time())
        atomic_json(C/'NATIVE_ADVANCE_OWNER.json',authority)
        acceptance=R/'runs/verify-capacity772-131072-dp4/CAPACITY_ACCEPTANCE.json'
        selected=False
        while True:
            state=dict(at=time.time(),owner=authority,old_four_gpu_dispatch_allowed=False)
            if not acceptance.exists():
                unit=subprocess.check_output(['systemctl','--user','show',
                    'qwen35-capacity772-128k-dp4-20261101-r6.service',
                    '--property=ActiveState','--value'],text=True).strip()
                state.update(status='WAITING_REAL_UPDATE_SAVE_RESUME',capacity_unit_state=unit)
                if unit not in ('active','activating'):
                    state.update(status='CAPACITY_STOPPED_WITHOUT_ACCEPTANCE',manual_failure_investigation_required=True)
            else:
                value=json.loads(acceptance.read_text())
                assert value['passed'] and value['context']==131072 and value['dp']==4 and value['ga']==8
                assert value['global_batch']==32 and value['source_sha256']==training_source_sha256()
                peak=max(x['max_memory_allocated']for x in value['ranks'])
                assert peak < int(79.25*1024**3*.90), 'Insufficient measured four-card headroom'
                if not selected:
                    runtime=json.loads((W/'configs/runtime.json').read_text())
                    atomic_json(C/'FORMAL_GPU_ALLOCATION.json',dict(
                        kind='MINIMUM_STABLE_GPU_ALLOCATION',execution_node='18',context=131072,
                        dp=4,ga=8,global_batch=32,gpu_ids=runtime['planned_gpu_ids'],
                        gpu_uuids=runtime['authorized_gpu_uuids'][:4],
                        capacity_acceptance=str(acceptance),acceptance_sha256=sha256(acceptance),
                        max_memory_allocated_bytes=peak,
                        held_by_native_training_lock=True,no_dummy_gpu_processes=True,
                        unused_gpu_ids=['4','5','6','7'],
                        reason_256k='Actual DP8 recurrent FLA backward OOM after allocator-fragmentation mitigation'))
                    selected=True
                state.update(advance())
            atomic_json(C/'NATIVE_ADVANCE_STATUS.json',state)
            with (W/'logs/native-advance-events.jsonl').open('a') as stream:
                stream.write(json.dumps(state,ensure_ascii=False)+'\n')
            print(json.dumps(state,ensure_ascii=False),flush=True)
            if state['status']=='NEW_M1_AND_M2_HF_READY_FOR_TB21_N3':
                return
            time.sleep(30)


if __name__=='__main__':main()
