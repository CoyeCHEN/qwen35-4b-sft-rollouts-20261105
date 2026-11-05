"""Read-only admission for the already authorized, dedicated validation GPU5."""
import hashlib
import json
from pathlib import Path
import subprocess

R = Path('/ssd/chenkeyi/qwen35-sft-772-20261101')
GPU = 'GPU-7b634c3e-13ae-5243-19dd-b6edddf9a543'


def decide(uuid, used_mib, compute_pids, authorized):
    if uuid != GPU or uuid not in authorized:
        raise ValueError('Validation GPU identity or authorization differs')
    if used_mib < 0:
        raise ValueError('Invalid GPU memory observation')
    # The observed idle remainder is4 MiB; a process or anything larger waits.
    return used_mib <= 4 and not compute_pids


def inspect():
    authority = R / 'new-sft/workspace/configs/runtime.json'
    allowed = json.loads(authority.read_text())['authorized_gpu_uuids']
    actual = subprocess.check_output(['nvidia-smi', '-i', '5', '--query-gpu=uuid,memory.used',
                                     '--format=csv,noheader,nounits'], text=True, timeout=15)
    uuid, memory = [v.strip() for v in actual.strip().split(',')]
    running = subprocess.check_output(['nvidia-smi', '-i', '5', '--query-compute-apps=pid',
                                      '--format=csv,noheader,nounits'], text=True, timeout=15)
    pids = [int(line.strip()) for line in running.splitlines() if line.strip()]
    used_mib = int(memory)
    return dict(ready=decide(uuid, used_mib, pids, allowed), gpu_uuid=uuid,
                used_mib=used_mib, compute_pids=pids,
                authorization_sha256=hashlib.sha256(authority.read_bytes()).hexdigest(),
                max_observed_idle_remainder_mib=4,
                observation_does_not_identify_the_residual_allocation_origin=True)


if __name__ == '__main__':
    print(json.dumps(inspect()))
