#!/usr/bin/env bash
set -euo pipefail
python3 /tests/webshop_verify.py
sync
# The Docker daemon and Harbor run in separate WSL distributions. Give the
# shared DrvFS mount time to publish verifier files before Harbor reads them.
sleep 5
