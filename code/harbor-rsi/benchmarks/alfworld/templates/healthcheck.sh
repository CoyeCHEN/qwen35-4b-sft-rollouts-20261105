#!/usr/bin/env bash
# Idempotent daemon readiness check, run as root by Harbor after start.
#
#   not running          -> start it, wait until ready, succeed
#   running and healthy  -> succeed, touch nothing
#   running but unhealthy-> fail
#
# It never restarts a live daemon. Once the episode has been initialized, a
# rebuild would silently rewind a partially completed episode to step 0, so an
# unhealthy daemon is reported as an infrastructure failure instead.
set -uo pipefail

PRIVATE_DIR=/opt/alfworld-private
CONFIG="$PRIVATE_DIR/daemon-config.json"
PID_FILE=/run/alfworld/daemon.pid
LOG_FILE="$PRIVATE_DIR/daemon.log"
PRIVATE_SOCKET=/run/alfworld/private.sock
READY_FILE=/run/alfworld/ready
VENV_PYTHON=/opt/alfworld-venv/bin/python
DAEMON="$PRIVATE_DIR/daemon.py"
START_TIMEOUT_SEC=180

log() { printf '%s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*" >&2; }

probe() {
  # Success only when the daemon answers on its private socket and reports a
  # started episode.
  [ -S "$PRIVATE_SOCKET" ] || return 1
  "$VENV_PYTHON" - "$PRIVATE_SOCKET" <<'PY'
import json, socket, sys
try:
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as c:
        c.settimeout(20)
        c.connect(sys.argv[1])
        c.sendall(b'{"op": "status"}\n')
        with c.makefile("r") as f:
            response = json.loads(f.readline())
except Exception as exc:
    print(f"probe failed: {exc}", file=sys.stderr)
    sys.exit(1)
sys.exit(0 if response.get("ok") and response.get("started") else 1)
PY
}

daemon_pid() {
  [ -f "$PID_FILE" ] || return 1
  local pid
  pid="$(cat "$PID_FILE" 2>/dev/null)" || return 1
  [ -n "$pid" ] || return 1
  kill -0 "$pid" 2>/dev/null || return 1
  printf '%s' "$pid"
}

if pid="$(daemon_pid)"; then
  if probe; then
    log "daemon already running and healthy (pid $pid)"
    exit 0
  fi
  log "FATAL: daemon pid $pid is running but not healthy; refusing to restart it"
  log "the episode may be partially complete; restarting would reset it to step 0"
  tail -n 40 "$LOG_FILE" 2>/dev/null >&2
  exit 1
fi

if [ -e "$READY_FILE" ]; then
  # The daemon was ready before and its process is now gone. The live episode
  # state is unrecoverable, so this is an infrastructure failure, not a restart.
  log "FATAL: daemon was previously ready but its process is gone; episode state is lost"
  tail -n 40 "$LOG_FILE" 2>/dev/null >&2
  exit 1
fi

log "starting ALFWorld daemon"
mkdir -p /run/alfworld
chmod 755 /run/alfworld
[ -f "$CONFIG" ] || { log "FATAL: missing daemon config $CONFIG"; exit 1; }

setsid "$VENV_PYTHON" "$DAEMON" --config "$CONFIG" >>"$LOG_FILE" 2>&1 &
echo $! > "$PID_FILE"
log "daemon pid $(cat "$PID_FILE")"

deadline=$(( $(date +%s) + START_TIMEOUT_SEC ))
while [ "$(date +%s)" -lt "$deadline" ]; do
  if probe; then
    log "daemon ready"
    exit 0
  fi
  if ! daemon_pid >/dev/null; then
    log "FATAL: daemon exited during startup"
    tail -n 40 "$LOG_FILE" 2>/dev/null >&2
    exit 1
  fi
  sleep 2
done

log "FATAL: daemon did not become ready within ${START_TIMEOUT_SEC}s"
tail -n 40 "$LOG_FILE" 2>/dev/null >&2
exit 1
