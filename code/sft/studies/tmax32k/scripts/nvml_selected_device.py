"""Query only the authorized GPU with the installed nvidia-ml-py library."""

import json
import sys
import time
from pathlib import Path

import pynvml as nv

nv.nvmlInit()
handle = nv.nvmlDeviceGetHandleByUUID(sys.argv[1])
memory = nv.nvmlDeviceGetMemoryInfo(handle, version=nv.nvmlMemory_v2)
processes = []
for item in nv.nvmlDeviceGetComputeRunningProcesses(handle):
    path = Path("/proc") / str(item.pid)
    processes.append(
        {
            "pid": item.pid,
            "uid": path.stat().st_uid if path.exists() else None,
            "used_bytes": int(item.usedGpuMemory),
        }
    )
name = nv.nvmlDeviceGetName(handle)
if isinstance(name, bytes):
    name = name.decode()
print(
    json.dumps(
        {
            "unix": time.time(),
            "gpu_uuid": sys.argv[1],
            "name": name,
            "memory_mib": memory.used // 2**20,
            "reserved_mib": memory.reserved // 2**20,
            "memory_info_version": 2,
            "total_mib": memory.total // 2**20,
            "processes": processes,
        }
    )
)
