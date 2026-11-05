"""Measure one observer under the unchanged10%CPU/256MiB/90s limits."""
import contextlib
import datetime
import hashlib
import io
import json
from pathlib import Path
import resource
import signal
import time

import observe_collection_formal_inventory_r306 as observe_collection


def main():
    root = observe_collection.ROOT
    directory = root / 'checks/monitor-formal-inventory-r307-resource'
    directory.mkdir(exist_ok=False)
    started = time.monotonic()
    cpu = time.process_time()
    source_sha = hashlib.sha256(Path(observe_collection.__file__).read_bytes()).hexdigest()

    def save(code, complete):
        result = dict(passed=complete and code == 0, exit_code=code,
            checked_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
            wall_seconds=time.monotonic()-started, self_cpu_seconds=time.process_time()-cpu,
            max_rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024,
            source_sha256=source_sha, deadline_seconds=90, cpu_quota='10%',
            memory_limit_bytes=256*1024**2, teacher_dispatches=0,
            existing_timer_or_shared_service_changes=0)
        with (directory / 'result.json').open('x') as stream:
            json.dump(result, stream, indent=2)

    def stop(signum, frame):
        save(124, False)
        raise SystemExit(124)

    signal.signal(signal.SIGTERM, stop)
    with contextlib.redirect_stdout(io.StringIO()):
        observe_collection.main()
    save(0, True)


if __name__ == '__main__':
    main()
