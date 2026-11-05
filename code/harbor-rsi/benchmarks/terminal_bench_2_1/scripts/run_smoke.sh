#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
: "${OPEN_HARNESS_WHEEL:?Set OPEN_HARNESS_WHEEL to the prebuilt CLI wheel}"
OPEN_HARNESS_WHEEL="$(realpath "$OPEN_HARNESS_WHEEL")"
[[ -f "$OPEN_HARNESS_WHEEL" && "$OPEN_HARNESS_WHEEL" == *.whl ]] || exit 2
cd "$REPO_ROOT"

TB_ENV="${TB_ENV:-harbor.environments.e2b_one_hour:OneHourE2BEnvironment}"
case "$TB_ENV" in
  e2b|harbor.environments.e2b_*:*|harbor.environments.e2b_qemu_recovery:*)
    if [[ -z "${E2B_API_KEY:-}" && -n "${e2bapi:-}" ]]; then
      export E2B_API_KEY="$e2bapi"
    fi
    : "${E2B_API_KEY:?E2B_API_KEY (or lowercase e2bapi) must be exported for Harbor E2B}"
    ;;
esac
: "${DEEPSEEK_API_KEY:?DEEPSEEK_API_KEY must be exported for the agent sandbox}"
HARBOR_BIN="${HARBOR_BIN:-harbor}"
command -v "$HARBOR_BIN" >/dev/null || {
  echo "Harbor executable not found: $HARBOR_BIN" >&2
  echo 'Set HARBOR_BIN to the absolute harbor executable path.' >&2
  exit 2
}

TB_MODEL="${TB_MODEL:-deepseek/deepseek-flash}"
case "$TB_MODEL" in
  deepseek/*) ;;
  *) echo "TB_MODEL must use the target adapter format deepseek/<model>." >&2; exit 2 ;;
esac

mkdir -p benchmarks/terminal_bench_2_1/results/smoke

args=(
  --dataset terminal-bench/terminal-bench-2-1
  --agent harbor.agents.installed.open_harness:OpenHarnessAgent
  --agent-kwarg "wheel_path=$OPEN_HARNESS_WHEEL"
  --model "$TB_MODEL"
  --env "$TB_ENV"
  --agent-env 'DEEPSEEK_API_KEY=${DEEPSEEK_API_KEY}'
  --n-concurrent 1
  --n-tasks "${TB_N_TASKS:-1}"
  --n-attempts "${TB_N_ATTEMPTS:-1}"
  --yes
  --jobs-dir benchmarks/terminal_bench_2_1/results/smoke
)
if [[ -n "${TB_INCLUDE_TASK_NAME:-}" ]]; then
  task_name="$TB_INCLUDE_TASK_NAME"
  [[ "$task_name" == */* ]] || task_name="terminal-bench/$task_name"
  args+=(--include-task-name "$task_name")
fi
exec "$HARBOR_BIN" run "${args[@]}"
