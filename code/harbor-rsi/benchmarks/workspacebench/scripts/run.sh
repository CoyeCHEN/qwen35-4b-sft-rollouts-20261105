#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
PYTHON=(${HARBOR_PYTHON:-python3})
DRY_RUN=false
PRINT_CONFIG=false
RUNNER_ARGS=()
HAS_SELECTION=false

for option in "$@"; do
  case "$option" in
    --dry-run) DRY_RUN=true ;;
    --print-config) PRINT_CONFIG=true ;;
    --task-limit|--task-ids|--persona)
      HAS_SELECTION=true
      RUNNER_ARGS+=("$option")
      ;;
    *) RUNNER_ARGS+=("$option") ;;
  esac
done

: "${WORKSPACEBENCH_SOURCE:?Set WORKSPACEBENCH_SOURCE to the pinned WorkspaceBench checkout}"
: "${OPEN_HARNESS_WHEEL:?Set OPEN_HARNESS_WHEEL to the prebuilt OpenHarness wheel}"
WORKSPACEBENCH_SOURCE="$(realpath "$WORKSPACEBENCH_SOURCE")"
OPEN_HARNESS_WHEEL="$(realpath "$OPEN_HARNESS_WHEEL")"
[[ -d "$WORKSPACEBENCH_SOURCE/.git" || -f "$WORKSPACEBENCH_SOURCE/.git" ]] || {
  echo "WORKSPACEBENCH_SOURCE is not a Git checkout: $WORKSPACEBENCH_SOURCE" >&2
  exit 2
}
[[ -f "$OPEN_HARNESS_WHEEL" && "$OPEN_HARNESS_WHEEL" == *.whl ]] || {
  echo "OPEN_HARNESS_WHEEL must point to a .whl file" >&2
  exit 2
}

RUNTIME_ROOT="${WORKSPACEBENCH_RUNTIME_ROOT:-$REPO_ROOT/benchmarks/workspacebench/datasets/runtime}"
SCOPE="${WORKSPACEBENCH_SCOPE:-smoke}"
case "$SCOPE" in
  smoke|lite) ;;
  *) echo "WORKSPACEBENCH_SCOPE must be smoke or lite" >&2; exit 2 ;;
esac

cd "$REPO_ROOT"
"${PYTHON[@]}" "$SCRIPT_DIR/validate.py" "$WORKSPACEBENCH_SOURCE" --fast >/dev/null
PREPARED_JSON="$("${PYTHON[@]}" "$SCRIPT_DIR/prepare.py" "$WORKSPACEBENCH_SOURCE" --output "$RUNTIME_ROOT" --wheel "$OPEN_HARNESS_WHEEL")"

EVAL_ROOT="$RUNTIME_ROOT/evaluation"
export WORKSPACEBENCH_ASSET_EVAL="$WORKSPACEBENCH_SOURCE/evaluation"
PREPARED_WHEEL_NAME="$("${PYTHON[@]}" -c 'import json, os, sys; print(os.path.basename(json.loads(sys.argv[1])["wheel_path"]))' "$PREPARED_JSON")"
export OPEN_HARNESS_WHEEL="/workspace/Workspace-Bench/evaluation/.generated/artifacts/$PREPARED_WHEEL_NAME"
export OPEN_HARNESS_MODEL="${WORKSPACEBENCH_MODEL_ID:-deepseek-flash}"
export OPEN_HARNESS_CONTEXT_WINDOW="${WORKSPACEBENCH_CONTEXT_WINDOW:-200000}"
export OPEN_HARNESS_MAX_TOKENS="${WORKSPACEBENCH_MAX_TOKENS:-65536}"
export OPEN_HARNESS_REASONING="${WORKSPACEBENCH_REASONING:-high}"
export OPEN_HARNESS_SUPPORTS_IMAGES="${WORKSPACEBENCH_SUPPORTS_IMAGES:-true}"

MODEL_ID="${WORKSPACEBENCH_MODEL_ID:-deepseek-flash}"
MODEL_NAME="${WORKSPACEBENCH_MODEL_NAME:-OpenHarness-DeepSeek-Flash}"
TIMEOUT_SEC="${WORKSPACEBENCH_TIMEOUT_SEC:-2400}"
RUN_NAME="${WORKSPACEBENCH_RUN_NAME:-OpenHarness-DeepSeek-Flash-${SCOPE}-$(date +%Y%m%d-%H%M%S)}"
JUDGE_MODEL_NAME="${WORKSPACEBENCH_JUDGE_MODEL_NAME:-DeepSeek-Flash-Judge}"

if [[ "$PRINT_CONFIG" == true || "$DRY_RUN" == true ]]; then
  "${PYTHON[@]}" - "$PREPARED_JSON" "$SCOPE" "$MODEL_ID" "$MODEL_NAME" "$TIMEOUT_SEC" "$RUN_NAME" <<'PY'
import json
import sys

prepared = json.loads(sys.argv[1])
print(json.dumps({
    "scope": sys.argv[2],
    "model_id": sys.argv[3],
    "model_name": sys.argv[4],
    "timeout_seconds": int(sys.argv[5]),
    "run_name": sys.argv[6],
    "runtime_root": prepared["runtime_root"],
    "source_commit": prepared["source_commit"],
    "task_asset_revision": prepared["task_asset_revision"],
    "wheel_sha256": prepared["wheel_sha256"],
    "runner": "workspacebench-native-isolated-container",
    "judge": "workspacebench-native-rubric-judge",
}, indent=2, sort_keys=True))
PY
fi
if [[ "$DRY_RUN" == true ]]; then
  exit 0
fi

: "${DEEPSEEK_API_KEY:?DEEPSEEK_API_KEY is required for the agent}"
DEEPSEEK_BASE_URL="${DEEPSEEK_BASE_URL:-https://api.deepseek.com}"
JUDGE_API_KEY="${WORKSPACEBENCH_JUDGE_API_KEY:-$DEEPSEEK_API_KEY}"
JUDGE_BASE_URL="${WORKSPACEBENCH_JUDGE_BASE_URL:-$DEEPSEEK_BASE_URL}"
JUDGE_MODEL="${WORKSPACEBENCH_JUDGE_MODEL:-deepseek-flash}"

cat > "$EVAL_ROOT/.env" <<EOF
DEEPSEEK_API_KEY=$DEEPSEEK_API_KEY
DEEPSEEK_BASE_URL=$DEEPSEEK_BASE_URL
OPEN_HARNESS_WHEEL=$OPEN_HARNESS_WHEEL
OPEN_HARNESS_MODEL=$OPEN_HARNESS_MODEL
OPEN_HARNESS_CONTEXT_WINDOW=$OPEN_HARNESS_CONTEXT_WINDOW
OPEN_HARNESS_MAX_TOKENS=$OPEN_HARNESS_MAX_TOKENS
OPEN_HARNESS_REASONING=$OPEN_HARNESS_REASONING
OPEN_HARNESS_SUPPORTS_IMAGES=$OPEN_HARNESS_SUPPORTS_IMAGES
EOF
chmod 600 "$EVAL_ROOT/.env" 2>/dev/null || true

mkdir -p "$EVAL_ROOT/.generated/runs"
JUDGE_YAML="$EVAL_ROOT/.generated/runs/judge-openharness-deepseek.yaml"
cat > "$JUDGE_YAML" <<EOF
model_name: "$JUDGE_MODEL_NAME"
baseUrl: "$JUDGE_BASE_URL"
model: "$JUDGE_MODEL"
apiKey: "$JUDGE_API_KEY"
EOF
chmod 600 "$JUDGE_YAML" 2>/dev/null || true

COMPOSE_FILE="$EVAL_ROOT/docker/docker-compose.yaml"
docker compose -f "$COMPOSE_FILE" build workspace-bench

if [[ "$SCOPE" == smoke && "$HAS_SELECTION" == false ]]; then
  RUNNER_ARGS+=(--task-limit 1)
fi

cd "$EVAL_ROOT"
runner_command=("${PYTHON[@]}" scripts/run_isolated_benchmark.py)
runner_command+=(--task-cpus "${WORKSPACEBENCH_TASK_CPUS:-2}")
runner_command+=(--task-memory-mb "${WORKSPACEBENCH_TASK_MEMORY_MB:-8192}")
runner_command+=(--task-pids "${WORKSPACEBENCH_TASK_PIDS:-512}")
runner_command+=(--task-storage-mb "${WORKSPACEBENCH_TASK_STORAGE_MB:-20480}")
runner_command+=(--harness openharness --model "$MODEL_ID" --model-id "$MODEL_ID")
runner_command+=(--model-name "$MODEL_NAME" --env-prefix DEEPSEEK --dataset lite)
runner_command+=(--timeout-sec "$TIMEOUT_SEC" --run-name "$RUN_NAME")
runner_command+=(--eval-yaml /workspace/Workspace-Bench/evaluation/.generated/runs/judge-openharness-deepseek.yaml)
runner_command+=("${RUNNER_ARGS[@]}")
"${runner_command[@]}"

RUN_DIR="$EVAL_ROOT/output/OpenHarness--${MODEL_NAME}--${RUN_NAME}"
[[ -d "$RUN_DIR" ]] || {
  echo "WorkspaceBench run directory was not produced: $RUN_DIR" >&2
  exit 1
}

docker compose -f "$COMPOSE_FILE" run --rm --no-deps workspace-bench python3 -u /workspace/Workspace-Bench/evaluation/src/agent_eval.py --task-dir "/workspace/Workspace-Bench/evaluation/output/OpenHarness--${MODEL_NAME}--${RUN_NAME}" --eval-yaml /workspace/Workspace-Bench/evaluation/.generated/runs/judge-openharness-deepseek.yaml --overwrite

"${PYTHON[@]}" "$SCRIPT_DIR/summarize.py" --run-dir "$RUN_DIR" --out "$RUN_DIR/summary.json" --judge-model "$JUDGE_MODEL_NAME"

echo "WorkspaceBench result: $RUN_DIR"
