#!/usr/bin/env bash
# JobBench ships no reference solution, so there is no oracle path.
#
# This file stays deliberately non-zero: `harbor run -a oracle` is a useful
# smoke test for "is this directory recognised as a task?", and a failure here
# is the expected outcome, not a regression.
set -euo pipefail
echo "JobBench provides no oracle solution; smoke-test with a real agent instead." >&2
exit 2
