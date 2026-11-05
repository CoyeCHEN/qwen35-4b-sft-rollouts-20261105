#!/bin/sh
set -eu

mkdir -p /logs/verifier
status=0
python3 /tests/evaluate.py >/logs/verifier/official_stdout.txt 2>/logs/verifier/official_stderr.txt || status=$?

if [ "$status" -ne 0 ] && [ ! -f /logs/verifier/reward.txt ]; then
  printf '%s\n' "verifier execution failed" > /logs/verifier/error.txt
  exit "$status"
fi

# A non-zero upstream hook is retained in official_returncode.json, while a
# numeric score remains a valid benchmark result (including a legitimate zero).
exit 0
