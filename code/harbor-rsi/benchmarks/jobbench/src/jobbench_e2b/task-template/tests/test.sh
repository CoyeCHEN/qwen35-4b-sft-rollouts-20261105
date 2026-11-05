#!/usr/bin/env bash
# Harbor verifier entrypoint for JobBench.
#
# Runs from the sandbox workdir after the agent phase. Harbor copies this
# directory to /tests/ and invokes `bash /tests/test.sh`.
#
# Two things this file must get right:
#   1. The interpreter must have the judge's dependencies (openai, and the
#      document-parsing stack for reading .xlsx/.docx/.pdf deliverables).
#      The base image builds /opt/jobbench-venv for exactly this.
#   2. {workdir} must match task.toml's [environment].workdir — if the agent
#      wrote deliverables somewhere else, the judge sees an empty directory and
#      every task scores 0 with no error.
set -euo pipefail

WORKDIR="__WORKDIR__"

# Prefer the image's venv; fall back to system python3 so the task still runs
# (with a clear failure) if someone swapped the base image.
if [ -x /opt/jobbench-venv/bin/python ]; then
    PY=/opt/jobbench-venv/bin/python
else
    echo "WARN: /opt/jobbench-venv missing; falling back to python3" >&2
    PY=python3
fi

exec "$PY" /tests/jobbench_verify.py \
    --output-dir        "${WORKDIR}/output" \
    --rubrics           /tests/RUBRICS.json \
    --judge             /tests/judge.py \
    --task-id           "${JOBBENCH_TASK_ID:?JOBBENCH_TASK_ID is not set}" \
    --profession        "${JOBBENCH_PROFESSION:?JOBBENCH_PROFESSION is not set}" \
    --evaluated-model   "${JOBBENCH_EVALUATED_MODEL:?JOBBENCH_EVALUATED_MODEL is not set}" \
    --judge-model       "${JUDGE_MODEL:?JUDGE_MODEL is not set}" \
    --max-workers       "${JOBBENCH_JUDGE_WORKERS:-3}"
