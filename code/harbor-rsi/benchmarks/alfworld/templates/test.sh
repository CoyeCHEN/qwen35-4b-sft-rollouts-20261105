#!/usr/bin/env bash
# Harbor verifier: score the episode from ALFWorld's own success signal.
#
# reward 1 when upstream reports info["won"], else 0. There is no external
# trajectory comparison and no filesystem heuristic: the benchmark's own signal
# is the only source of truth.
#
# Runs as root, so it can reach the daemon's private socket. The agent cannot.
# An unreachable daemon is an infrastructure failure: it exits non-zero without
# writing a reward file, so Harbor records the exception rather than a 0 that
# would be indistinguishable from a genuine agent failure.
set -uo pipefail

VERIFIER_DIR=/logs/verifier
REWARD_FILE="$VERIFIER_DIR/reward.txt"
PRIVATE_SOCKET=/run/alfworld/private.sock
VENV_PYTHON=/opt/alfworld-venv/bin/python

mkdir -p "$VERIFIER_DIR"
# Never grade against a stale reward from an earlier run in a reused snapshot.
rm -f "$REWARD_FILE" "$VERIFIER_DIR/reward.json"

status_json="$("$VENV_PYTHON" - "$PRIVATE_SOCKET" <<'PY'
import json, socket, sys
with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as c:
    c.settimeout(60)
    c.connect(sys.argv[1])
    c.sendall(b'{"op": "status"}\n')
    with c.makefile("r") as f:
        line = f.readline()
if not line:
    raise SystemExit("daemon closed the connection")
response = json.loads(line)
if not response.get("ok"):
    raise SystemExit(f"daemon error: {response.get('error')}")
if not response.get("started"):
    raise SystemExit("episode was never initialized")
print(json.dumps(response))
PY
)"
probe_status=$?

if [ "$probe_status" -ne 0 ]; then
  echo "VERIFIER INFRASTRUCTURE FAILURE: cannot read episode state from the daemon" >&2
  exit 1
fi

echo "episode status: $status_json" >&2

won="$("$VENV_PYTHON" -c '
import json, sys
print("1" if json.loads(sys.argv[1]).get("won") else "0")
' "$status_json")" || {
  echo "VERIFIER INFRASTRUCTURE FAILURE: cannot parse episode state" >&2
  exit 1
}

printf '%s\n' "$won" > "$REWARD_FILE"
echo "reward: $won" >&2
exit 0
