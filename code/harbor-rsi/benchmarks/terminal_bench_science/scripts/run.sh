#!/usr/bin/env bash
set -euo pipefail

for option in "$@"; do
  case "$option" in
    --print-config|--dry-run) ;;
    *) echo "Unsupported option: $option" >&2; exit 2 ;;
  esac
done

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
: "${OPEN_HARNESS_WHEEL:?Set OPEN_HARNESS_WHEEL to the prebuilt CLI wheel}"
OPEN_HARNESS_WHEEL="$(realpath "$OPEN_HARNESS_WHEEL")"
[[ -f "$OPEN_HARNESS_WHEEL" && "$OPEN_HARNESS_WHEEL" == *.whl ]] || exit 2
: "${E2B_API_KEY:?E2B_API_KEY must be exported for the E2B evaluator}"
: "${DEEPSEEK_API_KEY:?DEEPSEEK_API_KEY must be exported for the agent sandbox}"
: "${SCIENCE_SOURCE:?Set SCIENCE_SOURCE to the pinned v0.1.0 upstream checkout}"

cd "$REPO_ROOT"
HARBOR_BIN="${HARBOR_BIN:-harbor}"
command -v "$HARBOR_BIN" >/dev/null || {
  echo "Harbor executable not found: $HARBOR_BIN" >&2
  exit 2
}

MODEL="${SCIENCE_MODEL:-deepseek/deepseek-flash}"
case "$MODEL" in
  deepseek/*) ;;
  *) echo "SCIENCE_MODEL must use deepseek/<model>." >&2; exit 2 ;;
esac

SCOPE="${SCIENCE_SCOPE:-smoke}"
case "$SCOPE" in
  smoke) JOBS_DIR="${SCIENCE_JOBS_DIR:-benchmarks/terminal_bench_science/results/smoke}"; N_TASKS="${SCIENCE_N_TASKS:-1}" ;;
  compatible) JOBS_DIR="${SCIENCE_JOBS_DIR:-benchmarks/terminal_bench_science/results/compatible}"; N_TASKS="${SCIENCE_N_TASKS:-}" ;;
  full) JOBS_DIR="${SCIENCE_JOBS_DIR:-benchmarks/terminal_bench_science/results/full}"; N_TASKS="" ;;
  *) echo "SCIENCE_SCOPE must be smoke, compatible, or full." >&2; exit 2 ;;
esac

# Validate actual task content before dispatch; Git and registry tags differ.
STAGING_DIR="${SCIENCE_STAGING_DIR:-$REPO_ROOT/benchmarks/terminal_bench_science/datasets/v0.1.0}"
SCIENCE_PYTHON="${SCIENCE_PYTHON:-$(dirname "$(command -v "$HARBOR_BIN")")/python}"
[[ -x "$SCIENCE_PYTHON" ]] || SCIENCE_PYTHON=python3
VALIDATION_JSON="$(mktemp)"
trap 'rm -f "$VALIDATION_JSON"' EXIT
"$SCIENCE_PYTHON" "$SCRIPT_DIR/prepare_local.py" "$SCIENCE_SOURCE" --output "$STAGING_DIR" >/dev/null
"$SCIENCE_PYTHON" "$SCRIPT_DIR/validate.py" "$SCIENCE_SOURCE" >"$VALIDATION_JSON"
DATASET_ARGS=(--path "$STAGING_DIR")

# E2B is a single-sandbox backend. Never silently flatten a Compose task: its
# sidecar state can be private benchmark evidence and must remain isolated.
mapfile -t COMPOSE_TASKS < <(
  "$SCIENCE_PYTHON" - "$VALIDATION_JSON" <<'PY'
import json, sys
data = json.load(open(sys.argv[1]))
for name in data["compose_tasks"]:
    print(name)
PY
)
if [[ "$SCOPE" == full && "${#COMPOSE_TASKS[@]}" -gt 0 ]]; then
  printf 'E2B cannot run %s Compose task(s):\n' "${#COMPOSE_TASKS[@]}" >&2
  printf '  %s\n' "${COMPOSE_TASKS[@]}" >&2
  echo 'Use a compose-capable backend for the complete v0.1.0 release, or SCIENCE_SCOPE=compatible for the 65 single-sandbox tasks.' >&2
  exit 3
fi

TASK_FILTER="${SCIENCE_INCLUDE_TASK_NAME:-}"
if [[ -n "$TASK_FILTER" && -n "${SCIENCE_SOURCE:-}" ]]; then
  TASK_FILTER="${TASK_FILTER#terminal-bench-science/}"
fi

mkdir -p "$JOBS_DIR"
args=(
  "${DATASET_ARGS[@]}"
  --agent harbor.agents.installed.open_harness:OpenHarnessAgent
  --agent-kwarg "wheel_path=$OPEN_HARNESS_WHEEL"
  --agent-kwarg "thinking=${SCIENCE_THINKING:-max}"
  --agent-kwarg "max_tokens=${SCIENCE_MAX_TOKENS:-131072}"
  --model "$MODEL"
  --env harbor.environments.e2b_resumable:ResumableE2BEnvironment
  --agent-env 'DEEPSEEK_API_KEY=${DEEPSEEK_API_KEY}'
  --n-concurrent "${SCIENCE_N_CONCURRENT:-1}"
  --n-attempts 1
  --yes
  --jobs-dir "$JOBS_DIR"
)
if [[ -n "$N_TASKS" ]]; then
  args+=(--n-tasks "$N_TASKS")
fi
if [[ -n "$TASK_FILTER" ]]; then
  task_name="$TASK_FILTER"
  [[ "$task_name" == */* || -n "${SCIENCE_SOURCE:-}" ]] || task_name="terminal-bench-science/$task_name"
  args+=(--include-task-name "$task_name")
fi
if [[ "$SCOPE" == compatible ]]; then
  for task_name in "${COMPOSE_TASKS[@]}"; do
    args+=(--exclude-task-name "${task_name#terminal-bench-science/}")
  done
fi
exec "$HARBOR_BIN" run "${args[@]}" "$@"
