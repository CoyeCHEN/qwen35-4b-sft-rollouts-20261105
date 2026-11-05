# 在 OpenHarness、Harbor 和 E2B 上运行 JobBench

本目录是从用户提供的 `jobbench-e2b-source.zip` 导入的 JobBench 适配器，
并已接入本仓库的 OpenHarness Harbor agent。附件中的官方 judge 固定版本、F.1
提示词、任务转换和 reward 转换逻辑仍是评分权威。导入来源记录在
[`SOURCE.md`](SOURCE.md)。

## 生成内容

`jobbench_e2b.adapter` 会把官方 JobBench 源数据转换为 Harbor 任务：

```text
<dataset>/<split>/<profession>__task<N>/
|-- instruction.md
|-- task.toml
|-- environment/
|   |-- Dockerfile
|   |-- task_folder/
|   `-- output/.keep
|-- solution/solve.sh
`-- tests/
    |-- test.sh
    |-- jobbench_verify.py
    |-- judge.py
    `-- RUBRICS.json
```

main 数据集包含 65 个任务，easy 包含 63 个任务。适配器会在应用 `--limit`
或 `--task-ids` 前拒绝不完整的源数据集。它不会把 `task_card.md` 和
`files_required_to_search/` 放进 agent 可见环境，因为这些属于评分端或答案材料。

## 运行环境

默认执行后端是 E2B，而不是本地 Docker。E2B 使用每个生成任务的
`environment/Dockerfile` 构建 Linux 镜像，然后由 Harbor 上传并运行
OpenHarness wheel。Docker Desktop 只用于可选的本地镜像调试。

安装带 E2B 扩展的 Harbor：

```bash
uv sync --locked --no-default-groups --extra e2b --group rsi-test
```

镜像内包含官方 judge 依赖、常用文档处理工具、`ripgrep` 和 `fd`。镜像会创建
`/logs`、`/tests`、`/solution` 和 `/workspace`，因为 E2B 无法通过 Docker
bind mount 提供这些目录。

## 准备数据

在本 Harbor 仓库根目录执行：

```bash
export BENCHMARK_CACHE_ROOT="$HOME/.cache/harbor-rsi"
./benchmarks/scripts/fetch-jobbench-source.sh
uv run python benchmarks/scripts/fetch-jobbench-judge.py

export JOBBENCH_SOURCE_ROOT="$BENCHMARK_CACHE_ROOT/sources/job-bench-eval"
export JOBBENCH_SPLIT=easy
./benchmarks/scripts/prepare-jobbench.sh
```

生成任务默认位于
`$BENCHMARK_CACHE_ROOT/datasets/jobbench-e2b/<split>`。购买任何沙箱前，脚本会使用
`scripts/validate_dataset.py --strict` 校验数据集。

## 运行 OpenHarness

先在 RSI 构建端生成 wheel，或使用本仓库提供的构建端工具：

```bash
python scripts/build_rsi_artifact.py --kind harness \
  --source /absolute/path/to/open-harness --commit <commit> \
  --output /absolute/path/to/artifact-directory
```

使用[生产指南](../../docs/rsi/README.md)中的原生 JobConfig 与
[Campaign 四阶段门禁](../readiness/README.md)。tasks 指向生成的 split，
Judge 配置仅通过受信任的 Verifier 环境变量引用传入。先做真实 Judge 与
Verifier smoke，再冻结任务集；不能以 `/models` 连通替代 Judge 工作流。

当前 Campaign 真实验收支持 Docker/Remote Docker；E2B 返回 UNVERIFIED，
不能使用历史 E2B 成绩为新版本背书。旧 request/legacy launcher 已删除。
本目录数据转换和官方评分协议保持不变。

## 评分协议

`$BENCHMARK_CACHE_ROOT/vendor/jobbench/judge.py` 是固定在提交
`bbeae9de5d2f0f6f162f053e03b37069b5f404c8` 的官方 JobBench judge，SHA-256 为
`4e86a2e7f3e0790986332a3c72d96916211127396cb92f6501fce258d0a6856a`。
适配器会在生成任务前校验该哈希。

Judge 会为每个 rubric 输出通过/未通过结果和权重。Harbor reward 为：

```text
reward = total_score / max_score
```

Verifier 会写入：

- `/logs/verifier/reward.json` 和 `reward.txt`：供 Harbor 读取；
- `jobbench_result.json`：状态和逐 rubric 详情；
- `judge.json`：完整 judge 报告。

提交为空时直接计零分，不消耗 judge 调用。Judge API 失败时仍会生成合法的零 reward，
同时标记 `judge_failed` 并计入 `jobbench_judge_failures`，从而避免把基础设施故障
误判为正常的模型质量结果。

## 重要约束

- 不要同时设置 `docker_image` 和 `environment/Dockerfile`，否则 Harbor 会静默
  跳过 fixture 上传。
- 任务 workdir、instruction 和 verifier 必须统一使用 `/workspace`。
- 环境变量必须 `export`；Harbor 展开 `${VAR}` 时看不到 shell 局部变量。
- main 数据集 65 个任务中有 57 个需要公网。被测模型和 judge 端点也必须能从
  E2B 访问。

## 目录职责

- `src/jobbench_e2b/adapter.py`：把官方源数据转换为可在 E2B 运行的 Harbor 任务。
- `src/jobbench_e2b/migrate.py`：迁移旧版 JobBench-Harbor 数据集。
- `src/jobbench_e2b/task-template/`：提示词、任务清单和 verifier 适配层。
- `benchmarks/scripts/fetch-jobbench-judge.py`：获取并校验官方 judge，保存在仓库外缓存。
- `images/Dockerfile.jobbench`：OpenHarness/JobBench E2B 运行环境。
- `configs/`：并发和 E2B 运行配置。
- `scripts/validate_dataset.py`：结构和静默失败检查。
