"""JobBench on Harbor + E2B.

Two entry points:

* ``jobbench_e2b.adapter``  — build Harbor tasks from the upstream JobBench
  source tree (see the module docstring for the exact layout).
* ``jobbench_e2b.migrate``  — reshape an existing JobBench-Harbor dataset
  (yqi03-style, Siflow/sandbox-manager bound) into the same E2B-compatible
  form, without re-downloading anything.
"""

__all__ = ["adapter", "migrate"]
