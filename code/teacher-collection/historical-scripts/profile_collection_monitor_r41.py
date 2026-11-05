"""One bounded observer profile; no teacher or data-index actions."""
import cProfile
import contextlib
import datetime
import io
import json
from pathlib import Path
import pstats
import resource
import signal
import time

import observe_collection


R = observe_collection.ROOT
D = R / 'checks/monitor-resource-profile-r41'


def main():
    D.mkdir(exist_ok=False)
    profiler = cProfile.Profile()
    wall = time.monotonic()
    cpu = time.process_time()
    finished = False

    def save(code):
        profiler.disable()
        profiler.dump_stats(str(D / 'profile.pstats'))
        stats = pstats.Stats(profiler)
        rows = []
        for (path, line, name), (_, calls, own, cumulative, _) in sorted(stats.stats.items(), key=lambda item:item[1][3], reverse=True)[:45]:
            rows.append(dict(file=Path(path).name, line=line, function=name, calls=calls,
                own_seconds=own, cumulative_seconds=cumulative))
        usage = resource.getrusage(resource.RUSAGE_SELF)
        result = dict(checked_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
            exit_code=code, finished=finished, wall_seconds=time.monotonic()-wall,
            self_cpu_seconds=time.process_time()-cpu, max_rss_bytes=usage.ru_maxrss*1024,
            children_cpu_seconds=resource.getrusage(resource.RUSAGE_CHILDREN).ru_utime,
            rows=rows, teacher_dispatches=0, official_task_changes=0)
        with (D / 'result.json').open('x') as stream:
            json.dump(result, stream, indent=2)

    def stop(signum, frame):
        save(124)
        raise SystemExit(124)

    signal.signal(signal.SIGTERM, stop)
    profiler.enable()
    with contextlib.redirect_stdout(io.StringIO()):
        observe_collection.main()
    finished = True
    save(0)


if __name__ == '__main__':
    main()
