# WorkspaceBench 迁移与验证记录

## 范围与隔离边界

本适配只新增 `benchmarks/workspacebench/`。它不修改 Harbor-RSI 核心、现有
benchmark 或 OpenHarness 源码。WorkspaceBench 上游源码与任务资产由使用者自行
下载；适配器只接受一个固定提交的外部 checkout，并创建 detached worktree。

- Harbor-RSI 基线：`cd92bf6dfad34c46f3ea15200f7684abd0ed9d66`
- WorkspaceBench：`3fbd0f1a136720fece86786545983e26642c3db2`
- Lite：100 tasks、1850 rubrics
- 任务资产摘要：`sha256:f47d396a4a75ea8125a3683807198d23183cb70a38bb1ca0137675ff972d4847`
- OpenHarness wheel 摘要：`2f939005eebcaed2ca35b9f460a26a9002c99b3ad6502332469480f3db66002f`

运行时目录在 `benchmarks/workspacebench/datasets/` 下并被忽略。任务资产以只读
bind mount 注入，任务容器逐项创建并在结束后删除。共享的只有 benchmark 专属
OpenHarness venv volume；任务 HOME、工作区、临时目录和结果目录不共享。

## 接入策略

保留 WorkspaceBench 原生任务构造、角色文件系统、输出收集与 LLM rubric Judge。
Harbor-RSI 负责版本固定、资产校验、兼容 patch、OpenHarness 调用、隔离参数、轨迹
归档和汇总。这样不会把 WorkspaceBench 的评分语义重新实现一遍。

适配层分为三部分：

1. `manifest.json` 固定上游提交、Lite 数量和资产摘要。
2. `prepare.py` 创建 detached worktree，应用最小 patch，再覆盖新增的 OpenHarness
   agent adapter；wheel 保留合法原文件名和 SHA-256。
3. `run.sh` 生成运行配置，逐任务执行原生隔离 runner，调用原生 Judge，最后生成
   `summary.json`、`tasks.csv` 和 `trajectory-index.json`。

## 兼容性问题与处理

1. 上游准备脚本默认初始化五类角色。适配后根据选中的 task ID 只准备实际角色；
   单任务 100 只初始化 `houqin`。
2. detached worktree 的 `.git` 是文件，不是目录。任务隔离层使用空文件覆盖它，避免
   只读仓库暴露 Git 元数据，同时保持挂载类型一致。
3. `evaluation/tasks` 与 `tasks_lite` 在上游可能被忽略。准备阶段显式创建挂载目标，
   防止只读仓库挂载时 Docker 自动建目录失败。
4. Windows NTFS/WSL bind mount 可能拒绝 `copystat/utime`。输入、误放输出和正式输出
   都统一使用 portable copy：先 `copy2`，仅在 `PermissionError` 时退回 `copyfile`。
5. task 容器只读，且 NTFS 不适合直接创建 Python venv。共享 venv 放入
   `openharness-state` named volume；venv 与安装锁均位于该 volume 内。
6. pip 会拒绝被重命名为 `openharness.whl` 的文件。准备阶段保留原始、合法 wheel
   basename，运行配置从 `prepare.py` 的 JSON 结果读取该名称。
7. Docker host 不支持 `storage_opt.size` 时，原生 runner 会回退到任务目录容量监视；
   该状态记录在隔离报告中，不静默放宽任务预算。

## 2026-10-09 单样本 canary

任务 100（Logistics Manager，medium）使用与此前一致的 OpenHarness 设置：
`deepseek-flash`、reasoning `high`、图像开启、200k context、最大输出 65536、
agent timeout 2400 秒；Judge 使用 WorkspaceBench 原生 LLM rubric 流程。

最终有效尝试结果：

- agent：`passed`，runner：`ok`，耗时 71,491 ms
- 轨迹：14,995 条 LF 分隔 JSONL，包含 `agent_end`，最终 `result` 为
  `completed/exitCode=0`
- 调用：15 model calls、14 tool calls、0 tool errors
- token：prompt 281,838、completion 15,171、total 297,009
- 输出：1 个 `.doc`，44,544 bytes
- Judge：7/7 rubrics 通过；这是单样本结果，不代表 Lite 总分

在有效尝试前发生的错误均是模型调用前或适配后处理错误：只读锁目录、非法 wheel
文件名、NTFS 输出复制。前两类尝试均为 0 token；首次真实 agent 运行在产物复制时
失败，其 JSONL 与输出保留用于诊断，随后做了一次有界重测完成端到端验证。

## 轨迹与复核契约

每项至少保留：

- `agent.json`：规范化状态、token、时长、提示词、返回路径和执行摘要
- `raw/openharness_stdout.jsonl`：OpenHarness 原始逐事件轨迹
- `raw/openharness_stderr.log`、安装日志、调用参数和脱敏配置
- `output/`：agent 生成文件
- `rubrics_judge--<model>.json` 与 dependency graph
- run 级 runner report、`summary.json`、`tasks.csv`、`trajectory-index.json`

解析 JSONL 时只按 LF 切分；不要用会把 U+2028/U+2029 当换行的接口。完整性检查应
同时验证 JSON 可解析、`agent_end`、最终 `result`、输出文件哈希和 Judge rubric 数量。

## ScienceAgentBench 后续迁移清单

1. 固定上游 commit 和外部资产摘要，不把数据或环境打包进 PR。
2. 先保留原生 runner/Judge，再确认 Harbor-RSI 只承担编排与归档。
3. 所有 patch 和 overlay 都放在 benchmark 自己目录，禁止修改共享核心。
4. 为 read-only repo、`.git` 文件类型、ignored mountpoint 和 named volume 分别做预检。
5. wheel 或 CLI artifact 必须保留可安装文件名并记录 SHA-256。
6. 先跑 dry-run、patch clean-apply、单元测试，再跑一个 task canary。
7. canary 必须检查实际原始轨迹、输出和 Judge，不以进程退出码代替完整性审计。
8. 只对明确的外部/适配错误做有界重测；模型自然失败和低分保留。
9. 全量前估算工作区复制、Docker volume、轨迹和输出的磁盘上限。
10. PR 前确认 `git status` 只有新 benchmark 目录，避免格式化或工具改写既有文件。
