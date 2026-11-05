"""CPU-only torchrun failure fixture. Run only through the bounded remote check."""
import json
import os
from pathlib import Path
import sys
import time
import torch
import torch.distributed as distributed

assert os.environ.get('CUDA_VISIBLE_DEVICES')==''
torch.set_num_threads(1)
distributed.init_process_group('gloo')
rank=int(os.environ['RANK']);directory=Path(sys.argv[1])
identity=dict(pid=os.getpid(),startticks=Path('/proc/self/stat').read_text().rsplit(')',1)[1].split()[19],
              boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip(),CUDA_initialized=torch.cuda.is_initialized())
(directory/f'rank-{rank}.json').write_text(json.dumps(identity))
assert not torch.cuda.is_initialized()
distributed.barrier()
if rank==1:os._exit(19)
time.sleep(60)  # The elastic agent must terminate this remaining rank.
