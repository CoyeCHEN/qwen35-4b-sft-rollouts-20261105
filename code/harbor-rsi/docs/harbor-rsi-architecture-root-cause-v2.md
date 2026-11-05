# Harbor-RSI 架构根因报告 v2

日期：2026-10-11

本报告回答一个问题：为什么官方 Harbor 接入新 Benchmark 通常只需要 Adapter、标准 Task、环境定义和 Verifier，而 Harbor-RSI 曾经需要额外的 freeze、readiness、launcher、恢复脚本和远程 Docker 排障？结论不是“六个 Benchmark 各自有问题”，而是 Harbor-RSI 在几个不同层面重复实现了已经存在的职责，随后又把远程环境和特殊 Benchmark 生命周期放进了通用执行链。

## 结论先行

官方 Harbor 的通用链是：

```text
Dataset/Adapter -> TaskClient cache -> Job -> Trial
  -> EnvironmentFactory -> BaseEnvironment
  -> InstalledAgent -> Verifier -> TrialResult/JobResult
```

每个 Trial 拥有自己的环境、日志、结果和清理边界。Provider 只实现 `BaseEnvironment`，Agent 只通过 Environment 执行，Adapter 只生成 Harbor Task。官方已经同时支持内置 Provider 和 `environment.import_path` 外部 Provider，因此不需要新的 SandboxManager、第二个 Factory 或 benchmark-specific Trial。

Harbor-RSI 复杂化的主要来源按证据强度排序如下：

1. **已证实、Fork 回归：第二套 Task 物化。** `src/harbor/extensions/rsi/runner.py` 先通过 `TaskClient.download_tasks()` 解析任务，又默认把任务复制到 `.rsi/<request>/tasks`，产生第二个路径、哈希和状态来源。阶段一已将复制改为 `execution.snapshot_tasks=false` 的显式兼容选项。
2. **已证实、Fork 回归：Trial 恢复和收尾异常越过边界。** artifact、环境停止、finalization 或 END hook 的异常曾可能从 Job 的并发任务组冒泡，导致兄弟 Trial 被取消；也可能覆盖 Agent/Environment 的主错误。阶段一已把这些错误附着到当前 Trial 的 `infrastructure_errors`，保留主错误和 `failure_phase`。
3. **已证实、无必要耦合：OpenHarness 继承 Pi。** OpenHarness 是独立 CLI，却继承了 Pi 的选项和生命周期语义。这让 CLI 适配层携带了与 Pi 相关的隐式契约。阶段一改为直接继承 `BaseInstalledAgent`，保留显式 wheel、CLI、stdout/stderr、completion marker 和退出码契约。
4. **已确认的后续风险：Remote Docker 与本地 Docker 核心混合。** WSL 未提交快照在 `DockerEnvironment` 中加入 `remote` 分支，并让 `docker.py` 导入 `docker/remote.py`。这在个人环境可用，但把 SSH、staging、远端 bind mount、ownership 和控制器存活问题带入通用 Docker 类。阶段一没有把它复制到分支，因而 Remote Docker provider extraction 尚未完成。
5. **部分证实：benchmark-specific 资产和长生命周期需求被放入通用 Runner/Environment。** Science、WorkspaceBench、E2B handoff、QEMU 和 native shared workspace 的困难是真实需求，但它们应由 Adapter、Verifier 或显式 Environment Provider 表达；不应修改 Job、Trial 或 OpenHarness 的一般语义。

因此，最小目标架构是：**Harbor 负责一次 Job/Trial 的编排和结果；OpenHarness 是标准 InstalledAgent；Sandbox 是可通过 `environment.import_path` 选择的 Provider；Benchmark 只产出标准 Task 和官方 Verifier。** 本阶段已经恢复了 Agent、Task snapshot 和 Trial 异常的三条边界，但没有声称 Remote Docker 已经完成独立化。

## 1. 版本和源码身份

| 对象 | 身份 | 状态 |
| --- | --- | --- |
| 官方 Harbor 原始分叉基线 | `v0.23.0`, `1e5c5c6db929a10a140d05e606882c671ae20729`；`UPSTREAM.md` 记录的 tag object 为 `3c305dc5611e3600afc3c818735a82322f0264f8` | Harbor-RSI 的声明基线 |
| 官方 Harbor 最新 `main` | `dc933be707feafbb9efcdf092cb8a0e391332617`，2026-10-11 04:40:12 UTC，`fix(codex): chown auth.json to the image's agent user` | 通过 GitHub API 和 `git ls-remote` 核对；不是本次分支的 merge base |
| Harbor-RSI 最新远端 `main` | `5f7dfd3b9bf83dc51d18862cdd94c7a6b6779019`，2026-10-11 10:43:44 UTC，PR #4 merge | 审计和阶段一的 fork 基线 |
| Harbor-RSI 阶段一特性分支 | `codex/native-provider-boundaries`, `0d465427d17dde9cc6306e068bc7517d6e8eafe2`，2026-10-11 21:29:45 +08:00 | 当前报告对应代码；PR #5 |
| WSL 当前工作副本 | `/home/cky/workspace/RSI/harbor-rsi`，无 `.git`；包含未提交 Remote Docker、历史工件和本地修改 | 未覆盖、未重置、未纳入阶段一提交 |
| 审计 checkout | `/home/cky/harbor-rsi-audit-20261011/harbor-rsi-latest`，`5f7dfd3b...` | 远端最新 Harbor-RSI |
| OpenHarness2 最新可得 checkout | `f033d7255b34d4aa7958d0fb3bfcb03970aaccc9`，2026-10-07 19:01:45 +08:00 | checkout 为 GitHub `main` 快照 |
| OpenHarness CLI 源码包 | `open-harness-ai==0.3.0`，入口 `open-harness`，要求 Python >=3.11 | 实际运行的 CLI wheel 应为此包；源码位于 OpenHarness2 根项目 |
| Harbor 侧兼容包 | `openharness2-harbor==0.1.0`，`eval/pyproject.toml` | 这是旧 eval 适配包，不等于 CLI wheel |
| CLI 契约 | `openharness-cli-v1` | prompt file、config file、cwd、JSON stdout、completion marker、exit code |

审计没有在仓库中发现一个可重新计算的完整运行 wheel SHA-256 工件；历史验证记录只有缩写 hash。因此版本可追溯到源码 commit 和包版本，但某一次历史运行的完整 wheel hash 仍是证据缺口，正式运行必须从 `artifact.json` 读取并校验。

本阶段没有修改 `/home/cky/workspace/RSI`，没有清理 149 上的 Docker 资源，没有重建历史数据，也没有运行付费模型。

## 2. 官方 Harbor 的接入机制

### 2.1 Task 是唯一的 Benchmark 交界面

官方 Adapter 指南要求每个生成任务包含 `task.toml`、`instruction.md`、`environment/`、`tests/`，可选 `solution/`。`task.toml` 声明 task name、agent/verifier timeout、资源、网络、Compose/GPU 等能力；`tests/test.sh` 写入 `/logs/verifier/reward.txt`。Adapter 代码负责解析上游数据和生成目录，不修改 Job 或 Trial。

任务通过 `Dataset`/registry 解析成 `TaskConfig`，由 `TaskClient.download_tasks()` 下载、缓存和物化。内容 hash、Task identity 和 Job 目录由 Harbor 持有。开发者不需要再写一个冻结目录或任务调度器；需要不可变输入快照时才显式做 snapshot。

### 2.2 Job、Trial、Environment、Agent、Verifier 的职责

- `Job` 根据 Task 集合创建并发 Trial，汇总 Job 结果；并发隔离由 Trial task 边界实现。
- `Trial` 负责单个任务的准备、Agent phase、artifact、Verifier、timeout、cancel、result persistence 和 teardown。
- `EnvironmentFactory` 延迟加载内置 Provider，并提供 `create_environment_from_import_path()`。`EnvironmentConfig.import_path` 是外部 Provider 入口，不要求修改注册表或增加第二个 Factory。
- `BaseEnvironment` 提供 `start`、`stop`、`exec`、upload/download、能力声明和用户/日志辅助方法。Docker、E2B、Modal 等 Provider 用各自 SDK 实现这些操作。
- `BaseInstalledAgent` 接受 instruction、Environment 和 AgentContext。Installed Agent 不创建 Job，不评分，不拥有 Benchmark 数据。
- `Verifier` 在 shared 或 separate Environment 中运行，通过标准 artifact 和 reward 文件回传 `VerifierResult`。

### 2.3 三类官方 Adapter 的代表

| 类型 | 代表 | Adapter 文件 | Harbor core 是否修改 | 特殊点 |
| --- | --- | --- | --- | --- |
| 一般容器/代码任务 | `adapters/swebench` | `adapter.py`、`main.py`、`task-template/*`、`swebench.yaml` | 否 | 从 SWE-bench instance 生成 Dockerfile、instruction、tests；可直接 `harbor run -d swebench-verified -a ...` |
| 复杂环境/多资源 | `adapters/featurebench` | `run_adapter.py`、`template/*`、CPU/GPU/Modal YAML | 否 | Task metadata 声明 GPU、shm、资源；不支持 GPU 时配置选择明确失败或换 Provider，不偷偷改变 Task |
| 自定义数据/Judge/外部资产 | `adapters/scienceagentbench` | `adapter.py`、`utils.py`、`template/tests/*`、manifest | 否 | 将 benchmark 数据、gold result 和官方 eval wrapper 放入 Task 环境；视觉 Judge 仍是 verifier 资产；外部数据获取是 Adapter 预检问题 |

这些 Adapter 可以运行 Oracle/NOP：Oracle 通过 `solution/solve.sh` 或标准 Oracle Agent 生成确定性成功证据，NOP 用于检查 verifier 的零分和缺失输出语义。Parity 只比较 Adapter 生成的 Task 与原始 Benchmark 的 instruction、环境、测试和指标，不通过修改 Harbor core 达成分数。

### 2.4 官方真实执行链

```text
原始 benchmark
  -> adapter/main.py 解析、固定 task 清单和版本
  -> task.toml + instruction.md + environment + tests
  -> registry/local Dataset
  -> TaskClient.download_tasks()（cache、content hash、Task identity）
  -> JobConfig / Job
  -> TrialQueue / Trial（每 Task 独立状态）
  -> EnvironmentFactory（内置 type 或 environment.import_path）
  -> BaseEnvironment.start/build/compose/exec/upload
  -> InstalledAgent.install/run（instruction + cwd + AgentContext）
  -> artifacts/logs
  -> Verifier（shared 或 separate environment）
  -> reward/metrics -> TrialResult -> JobResult
```

重跑和恢复读取 Job/Trial 目录中的标准结果、锁和日志；环境的重试/恢复由 Provider 的能力决定。官方不存在强制的 readiness manifest、第二个任务目录或 benchmark-specific launcher。

## 3. Harbor-RSI 当前链和变化

远端 `main`（`5f7dfd3b`）的 RSI 入口增加了候选 wheel、模型、benchmark source、task selection、backend 和 provenance 的 request schema。这些是评测可追溯性功能；真正造成复杂度的不是 request JSON，而是 request 被送入了额外的准备和状态层。

### 3.1 阶段一之前的链

```text
原始 benchmark
  -> benchmark builder / registry
  -> RSI request + preflight
  -> resolve_tasks()
  -> TaskClient.download_tasks()
  -> runner._prepare() 复制到 .rsi/<request>/tasks
  -> manifest/fingerprint/freeze/readiness（按旧入口或 benchmark 脚本）
  -> subprocess launcher / 外围 campaign 状态
  -> Harbor Job/Trial
  -> Provider（E2B、Docker 或 WSL remote 分支）
  -> OpenHarnessAgent（旧版继承 Pi）
  -> artifact/recovery/remote handoff
  -> Verifier / benchmark report / RSI summary
```

这里至少有两套输入身份：Harbor TaskClient 的 cache/task path 和 RSI `.rsi` snapshot/manifest；在某些旧流程还有 benchmark 自己的 manifest。恢复、结果和清理也可能同时由 Trial、Remote Docker、launcher 和 benchmark script 触发。

### 3.2 阶段一后的默认链

```text
request
  -> preflight + TaskClient.download_tasks()
  -> Harbor Job/Trial（默认不复制 Task）
  -> EnvironmentFactory(type 或 import_path)
  -> OpenHarnessAgent(BaseInstalledAgent)
  -> Verifier -> Result
  -> RSI report（只做 provenance/summary）
```

`execution.snapshot_tasks=true` 时才启用 `.rsi/<request>/tasks` 兼容快照；它是审计输入的显式选择，不是正常运行的必经阶段。Runner 仍保留 request manifest、subprocess supervision 和 summary，因为这些是 RSI CLI 的 provenance/入口功能，但它不再调度 Trial、不重新实现评分。

### 3.3 新增阶段和语义变化

| 阶段 | 文件/函数 | 官方没有的行为 | 结论 |
| --- | --- | --- | --- |
| request preflight | `extensions/rsi/runner.py:preflight` | wheel SHA、模型描述、凭据存在性、backend 前置检查 | 保留；属于运行入口，不应复制 Job |
| snapshot | `runner.py:_prepare`、`Execution.snapshot_tasks` | 复制 Task 和 wheel 到 `.rsi` 控制区 | 默认关闭；只为审计/兼容显式开启 |
| manifest | `runner.py:resolve_tasks` | 额外记录 content hash、resolved source、scope | 保留 provenance；不能成为第二 cache identity |
| process supervisor | `trial/agent_lifecycle.py`、`process_supervisor.py` | OpenHarness completion marker、退出/取消观察 | Agent 有 managed lifecycle 时需要；不能拥有 Trial/Job 状态 |
| recovery | `trial.py:_recover_after_failure`、`single_step.py:_recover_outputs` | 收集 artifact/stop/finalization 错误 | 保留，但错误只能进入当前 Trial |
| legacy campaign | `extensions/rsi/legacy/*` | JobBench/WebShop/旧 E2B 运行方式 | 兼容保留；普通 Benchmark 默认不走 |
| remote staging | WSL `docker.py`、`docker/remote.py` | SSH、host staging、remote compose/cp/chown | 远端开发需求，不应进入通用 Docker core；待提取 Provider |

## 4. Fork Diff 审计

### 4.1 已实施的阶段一改动

提交 `0d465427` 修改 11 个文件，增加 607 行，删除 20 行。

| 文件/函数 | 变化 | 分类 | 证据和风险 |
| --- | --- | --- | --- |
| `src/harbor/agents/installed/open_harness.py:OpenHarnessAgent` | `Pi` -> `BaseInstalledAgent`；显式 `InstalledAgentOptions`、`ModelConnectionSpec`；保留 wheel SHA、Python probe、prompt/config、stdout/stderr、completion marker、non-zero exit | KEEP / SIMPLIFY | 151 个定向测试覆盖；移除 Pi 隐式 options。仍有 DeepSeek 与 `openharness-cli-v1` 契约，属于当前 wheel 版本要求，不是 Sandbox 依赖 |
| `src/harbor/environments/factory.py` 和 `EnvironmentConfig.import_path` | 复用上游已有入口 | UPSTREAM | 不新增 registry/manager；Mock Provider 只改环境配置 |
| `src/harbor/trial/trial.py` | 增加当前 Trial 的 cleanup/finalization/infrastructure error 记录；保留 primary exception | FIX | TB2.1 类兄弟 Trial 被取消风险对应 TaskGroup 边界；需继续做真实 cancellation fault injection |
| `src/harbor/trial/single_step.py` | artifact、sync、stop 分阶段恢复；去重并保留原始错误 | FIX | 覆盖 cleanup failure persistence、agent non-zero 和 verifier failure |
| `src/harbor/models/trial/result.py` | `failure_phase`、`infrastructure_errors` | KEEP | 使正常零分、Agent 错误、Provider 错误可区分；Result schema 兼容性需继续验证旧 JSON |
| `src/harbor/extensions/rsi/models.py` | `execution.snapshot_tasks` 默认 false | SIMPLIFY | 允许明确审计快照，不强制第二套 Task |
| `src/harbor/extensions/rsi/runner.py` | `_prepare` 默认不复制任务；TaskClient cache 成为默认输入 | UPSTREAM / REMOVE(old default) | 直接消除第二物化；manifest 继续存在但不改变 Task identity |
| `tests/unit/rsi/test_native_job.py` | 原生 Job->Trial->OpenHarness->Environment->Verifier、两个 Provider、CLI wheel、nested binary、退出码、artifact | KEEP | 阶段主要验收证据；不等于 Docker/E2B 真实 smoke |
| `tests/unit/rsi/test_runner.py` | 默认不 snapshot、显式 snapshot 行为 | KEEP | 防止后续 runner 回归 |
| `docs/rsi/component-boundaries.md` | 三层边界和 WSL remote 过渡规则 | KEEP | 作为后续 Provider extraction 合约 |

### 4.2 尚未纳入阶段分支的 WSL Remote Docker

WSL 目录中的 `src/harbor/environments/docker/remote.py` 约 750 行，并在 `docker.py` 构造、compose path、capabilities、exec、upload/download、cleanup 等多处通过 `remote` 分支接入。它包含：

- SSH command wrapper、重试和跳板参数；
- local build context 归档、远端 staging root 和 compose JSON；
- 远程 `docker compose` build/up/exec/down；
- `docker cp` tar 流、双端 SHA-256 校验；
- uid/gid ownership 修复和递归 `chown`；
- compose project label 识别和安全删除；
- remote bind mount 被改写为 staging 路径；
- controller 消失后的资源保留/回收记录。

这些功能中，SSH、149、turing、WSL 私有路径和 Docker context 名称不能写进 Harbor core。远程 daemon 的 bind mount 也不等同于本地 Docker：宿主路径必须存在于 daemon 所在主机，控制器上传的路径不能直接作为 daemon bind source；`capabilities.mounted` 通常必须为 false；Compose 中相对路径、网络、权限和 volume 需要重新解析。

正确的提取形态是独立包或模块中的 `RemoteDockerEnvironment(BaseEnvironment)`，通过 `environment.import_path` 选择，配置显式传入 endpoint/context/ssh/staging/cleanup policy。它应该复用 Docker 的纯 compose/build 工具函数，但不能让 `DockerEnvironment` 继续拥有 remote if/else。Provider 在构造时拒绝不支持的 bind mount、Windows、网络、Compose 或 ownership 语义；不能静默把任务改写成另一个任务。

## 5. 根因和失败证据

| 根因 | 置信度 | 新旧语义变化 | 失败材料 | 反事实实验 |
| --- | --- | --- | --- | --- |
| 第二套 Task materialization | 已证实 | 官方 cache path 与 RSI snapshot path 同时成为输入来源；修改/恢复可能只更新其中一份 | `runner.py` 旧 `_prepare`；TB-Science 数据在物化阶段丢失；阶段一测试默认 snapshot false | 同一 TaskClient config 运行 `snapshot_tasks=false/true`，比较 task hash、文件树、verifier 输出；不接模型 |
| Trial recovery 异常扩散 | 已证实 | cleanup/finalization 异常可从 Trial task 进入 Job TaskGroup，兄弟 Trial 被取消 | TB2.1 recovery 影响兄弟 Trial 的历史日志；阶段一新增 fault injection 已验证兄弟继续 | 两个并发 Mock Trial，一个在 stop/artifact 抛错；检查另一 Trial result 和 Job 完成状态 |
| Pi 继承导致 Agent 隐式耦合 | 已证实 | OpenHarness 取得 Pi options/lifecycle 假设，增加了不属于 CLI adapter 的配置面 | 旧文件导入 `Pi, PiOptions`；阶段一改为 BaseInstalledAgent 且原生测试通过 | 同 wheel、同 Task、同 Provider 比较 direct BaseInstalledAgent 与 Pi 的配置/退出/日志差异 |
| Remote Docker 混入本地 Docker | 高可信，尚未在阶段分支真实运行 | 本地 `mounted`、compose path、ownership、cleanup 语义被 remote flag 改写；SSH controller 变成隐含单点 | WSL `docker.py` remote 分支和 `docker/remote.py`；已知递归 chown timeout、controller 消失、bind mount 风险 | 本地 Docker mock daemon 与 SSH fault injection；每次只切换 provider，不改 Task/Agent |
| Benchmark 特殊生命周期进入通用层 | 部分证实 | Science/WorkspaceBench 的数据、native workspace、长任务需求迫使 Runner/环境处理特殊状态 | Science 数据物化丢失、WorkspaceBench 需要 shared workspace、E2B recovery 文档 | 标准 Task + separate verifier artifact flow；若官方 verifier 可消费归档，则不改 Trial；否则声明 Provider 不支持 |
| OpenHarness CLI/tool loop 非零退出 | Agent 内部错误或输入契约，不足以归因 Harbor | CLI completion marker/exit code 正确传播；非零本身不应转成 reward | JobBench 历史日志；阶段一测试确保 non-zero 为 Agent failure | Mock CLI 返回各退出码，比较 AgentResult 和 verifier 是否被错误调用 |
| wheelhouse/Python ABI 不匹配 | 外部工件/环境问题 | 安装失败发生在 Provider image/runtime，不是 Job 调度语义 | CoreWars 历史记录；阶段一保留 Python >=3.11 probe 和显式 wheel | 同 wheel 在 Python 3.11/3.12/3.13 image 离线安装；记录 setup failure |
| 远端 `chown -R` 超时 | Provider 实现缺陷 | ownership 修复的复杂度和数据量依赖远端 FS；与官方 Docker 无关 | WSL remote.py 的递归 chown；历史 Remote Docker 日志 | 大文件树上用 tar ownership、容器内用户、分层目录策略对照，禁止超时后假成功 |
| E2B/镜像/外部数据不可用 | 外部基础设施或 Benchmark 资产 | 资源、GPU、下载、镜像失败应为 infrastructure/setup failure，不得变成零分 | Science GPU/OOM、E2B 模板和 SharePoint 数据限制 | Oracle/NOP 在无模型、同 Task 上运行环境预检；缺能力即 fail closed |

### 5.1 失败为何曾经“需要反复排障”

旧链将三种独立问题叠加：

1. **输入身份问题**：freeze、manifest、TaskClient cache 和 benchmark manifest 同时存在，导致“文件到底是哪一份”需要人工判断。
2. **执行边界问题**：Trial、launcher、Remote Docker 和恢复脚本都可以停止环境或写结果，导致一个错误有多个传播路径。
3. **能力/部署问题**：本地 Docker、SSH Docker Context 和云 Provider 的 mount、Compose、user、TTL、网络语义并不相同，却曾通过 `remote` 分支尝试伪装成一个环境。

这比单个 Benchmark 的复杂度更能解释“每接一个新 Benchmark 又修一轮框架”：每个新任务都会触发三套状态、一个新的 Provider 语义和一组生命周期边界的组合问题。

## 6. Provider 对比和 Remote Docker 方案

| 方案 | 功能 | 安全/身份 | 开发成本 | 新 Benchmark 兼容性 |
| --- | --- | --- | --- | --- |
| Harbor 控制器与 Docker daemon 同机 | 官方 Docker build/Compose/bind mount/cleanup 语义最完整；低延迟 | 主机权限集中；不需要 SSH staging | 最低 | 最高；标准 Docker Task 直接复用 |
| Docker Context/SSH | 可访问 149；保留 Docker CLI/Compose 生态 | context、SSH agent、主机路径和 socket 权限需外部配置；控制器断开时资源仍在 | 中 | 对无 bind mount 的单容器任务较好；远程 Compose/mount 需 fail-closed |
| 独立 `RemoteDockerEnvironment` | 可封装 staging、cp、label cleanup、ownership 和重连 | Provider 可隔离凭据、endpoint、项目 ID；必须持久化 resource identity | 中高 | 标准 Task 可用，但能力声明不能伪装成本地 Docker |
| E2B/Modal/官方云 Provider | API 管理生命周期、隔离和并发；无需个人 SSH | 凭据和配额在调用环境；资源 TTL/网络/GPU 有明确限制 | 已有 | Adapter 不变；不支持的 Compose/GPU 必须提前报错 |

本阶段选择“不把 WSL remote 复制进默认 core”是风险控制，不是删除功能。下一阶段应先把 remote 逻辑拆成 Provider，再用同一 Task/Mock Agent 做本地 Docker、Mock Provider 和 Remote Provider 的契约测试。不能先依赖 149 真实资源证明抽象正确。

## 7. 分类清单

### KEEP

- `OpenHarnessAgent` 的显式 wheel SHA-256、CLI contract、prompt/cwd、stdout/stderr、completion marker 和 non-zero exit 传播。
- `BaseEnvironment` 调用、`EnvironmentFactory` 的 `import_path`、官方 Job/Trial/Verifier、TaskClient cache。
- `failure_phase`、`infrastructure_errors`、主异常优先和当前 Trial 的 cleanup 记录。
- RSI request provenance、manifest、模型/预算/Harbor/Harness identity；它们不能变成调度系统。
- benchmark 自己的官方 verifier、外部数据预检和能力检查。

### SIMPLIFY

- `extensions/rsi/runner.py`：把 snapshot、freeze、readiness 和报告拆成显式命令/可选模式；默认只调用 TaskClient + Job。
- OpenHarness 的 model descriptor：保留当前 wheel 所需的 `deepseek/<id>` 校验，但未来 CLI contract 版本化后将供应商配置交回 OpenHarness。
- Remote Docker 的共用代码：提取纯 staging、archive、hash、Compose merge 工具，避免复制 Docker build/exec 生命周期。

### UPSTREAM

- `EnvironmentConfig.import_path` 和 `EnvironmentFactory.create_environment_from_import_path()`，不要新增 SandboxManager/Registry。
- Task download/cache/content hash、Job/Trial queue、Verifier separate/shared environment、artifact handler、resume/lock。
- 官方 Docker/Compose 能力和 Provider capability validation。

### MOVE

- 远程 SSH、Docker Context、staging、resource labels、ownership、controller-loss 记录 -> `RemoteDockerEnvironment`。
- Benchmark data download、任务清单和输入哈希 -> Adapter/Task builder/preflight。
- 长任务 handoff、artifact archive 和 verifier sandbox -> 一个明确声明能力的 Provider/Benchmark integration；不要藏在普通 Verifier 调用里。
- 模型 descriptor、工具和 thinking policy -> OpenHarness CLI contract；Harbor 只传模型和显式 options。

### REMOVE

- 普通运行默认的 `freeze_tasks()` 第二复制。
- Benchmark-specific launcher 对 Job/Trial 的重复调度、评分和 resume。
- Harbor core 中的 149、turing、WSL 路径、SSH 凭据和 Docker context 名称。
- Provider failure 被吞掉后继续生成 reward 的逻辑。

### FIX

- Trial finalization、artifact、environment stop、END hook 的异常隔离；阶段一已提交第一版。
- Remote Provider 的 resource identity、cleanup 幂等性、远端 bind mount 和 ownership 失败语义；待提取后实现。
- 大文件传输必须双端 hash 校验，任何校验失败都表 infrastructure failure。

### UNKNOWN

- Remote Docker 在 149 的 Docker daemon、Compose 版本、SSH reconnect 和真实大文件性能，当前没有本阶段运行证据。
- OpenHarness wheel provenance 是否能从每个历史结果恢复完整 SHA-256。
- E2B `fork()` 对具体长任务进程、外部网络连接和 verifier artifact 的语义是否满足某个 Benchmark；必须按任务验证。
- 官方最新 `main` (`dc933be7`) 在本分支基线之后的所有上游变化是否需要 rebase；本阶段只核对了身份，没有自动合并。

## 8. 阶段一验证结果

阶段一在 `/home/cky/harbor-rsi-phase1` 的 commit `0d465427` 上完成：

```text
151 passed
ruff check (changed source/tests): passed
ruff format --check: passed
ty changed source: passed
```

测试覆盖：

- 原生 `Job -> Trial -> OpenHarness -> Environment -> Verifier`；
- 同一个 Task/Agent/Verifier 切换两个 Environment 实现；
- 离线生成 CLI wheel、wheel SHA、instruction 原文、嵌套二进制输入；
- upload/download、stdout/stderr、completion marker、CLI non-zero；
- verifier reward、Environment start/stop、取消和 cleanup failure persistence；
- Trial recovery 不取消兄弟 Trial；
- Runner 默认不 snapshot，显式 snapshot 仍可用；
- TrialQueue、Pi 相关既有回归。

没有执行：付费模型、Docker/149 资源、六基准全量、历史结果修改。全仓 `ty check` 仍有约 188 个既有 optional dependency/legacy 诊断，不能作为本阶段变更失败证据。

因此三项验收的状态是：

| 验收 | 状态 |
| --- | --- |
| 不启用 Remote Docker 时，默认 Harbor 路径正常 | 已通过离线原生 Job/Mock Provider 测试；未做真实 Docker smoke |
| 切换 Environment 不修改 OpenHarness/Task/Verifier/Job/Trial | 已通过两个 Provider 原生测试 |
| Remote Docker 失败不影响无关 Trial、不改评分 | Trial 通用隔离已通过 Mock fault injection；Remote Docker 本身尚未提取/实测，因此 Provider-specific 部分待验证 |

## 9. 最小目标架构

```text
Benchmark Adapter
  └─ standard Task (task.toml, instruction, environment, tests/verifier)
       └─ TaskClient cache/content identity
            └─ Harbor Job / Trial
                 ├─ EnvironmentFactory(type | import_path)
                 │    └─ Docker / E2B / Modal / RemoteDocker / Mock
                 ├─ OpenHarnessAgent(BaseInstalledAgent)
                 └─ Verifier + ArtifactHandler
                      └─ TrialResult / JobResult / provenance
```

每层唯一职责：

- Adapter：把原始 benchmark 变成 Task；记录版本、输入、外部资产和官方评分。
- Task/Verifier：定义任务语义和评分；不选择 Provider，不读取 Harness 私有状态。
- Job/Trial：调度、timeout、cancel、异常归属、artifact、result 和清理。
- Provider：创建/停止 sandbox、能力声明、exec、传输、资源 identity 和清理。
- OpenHarness：处理自身模型供应商、session、tool loop 和 CLI；Harbor 只使用标准 InstalledAgent 契约。
- RSI CLI：校验请求、记录 provenance、调用原生 Job、汇总结果；不复制 Task、不拥有第二个 Job。

## 10. 迁移路线

### 第一步：先合并并观察阶段一

审查 PR #5 的 11 个文件，先合并或在特性分支运行离线测试。对旧结果只做读取兼容，不重写结果。增加旧 JSON 的 `infrastructure_errors` 缺省读取测试。

### 第二步：Remote Docker provider extraction

从 WSL snapshot 建立独立模块：

1. `RemoteDockerEnvironment(BaseEnvironment)` 和独立 config model；所有 endpoint、SSH、staging、context、cleanup namespace 从外部配置读取。
2. 只复用 Docker 的无状态 Compose/build 解析函数；删除 `DockerEnvironment.__init__`、`capabilities`、`_docker_compose_paths`、`exec/upload/download/stop` 中的 remote 分支。
3. 明确能力矩阵：Linux、Compose、network、bind mount、GPU、mounted、separate verifier、ownership、large transfer。不能支持就构造时报错。
4. 资源 identity 使用随机 project/session label；cleanup 只删除匹配 identity 的容器、网络和 staging。
5. controller loss 只记录 orphan evidence，不能把不确定的删除报告为成功。

### 第三步：Runner 收敛

把 `freeze_tasks`、readiness 和旧 campaign 标记为兼容命令。普通 `harbor rsi run` 只做 request preflight、TaskClient、Job 和 summary。snapshot 只在 `--snapshot-tasks` 显式开启。

### 第四步：Provider contract suite

不使用模型，固定一个标准 Dockerfile Task、一个 Compose Task、嵌套二进制、大 artifact、非零 Agent、环境启动失败、Verifier 失败、取消和两个并发 Trial。对 Mock、Docker（可用时）和 Remote Provider 运行同一套测试。

### 第五步：一个新 Benchmark 接入验收

使用 SWE-bench Verified 之外的一个普通代码任务集，或者官方已有但 RSI 未特化的 `featurebench-lite`，只生成 Task 和配置。统计：新增文件、core 修改、配置项、人工步骤、状态/cache identity。若需要改 Trial/Job/OpenHarness，先停止并记录契约缺口。

回滚方式：阶段一改动可按单个 commit 回退；Remote Provider 通过 `environment.import_path` opt-in，不影响默认 Docker/E2B；snapshot 兼容开关保留，便于逐个历史运行迁移。

## 11. 新 Benchmark 对照推演

选择 `featurebench-lite` 作为代表，因为它同时有标准 Docker task、预构建镜像、CPU/GPU 任务和 Modal 配置，但不需要 WorkspaceBench 的 shared workspace 特例。

### 官方路径

1. 读取 FeatureBench revision 和 task metadata。
2. 运行 `adapters/featurebench/run_adapter.py` 生成 30 个 Harbor task 目录。
3. 运行 `harbor jobs start -p datasets/featurebench-lite -a <agent> -m <model>`。
4. 由 task.toml 选择 CPU/GPU 资源，Docker/Modal Provider 创建环境。
5. Agent 执行，官方测试写 reward，Job 汇总。

### 当前 Harbor-RSI 默认路径（阶段一后）

1. 生成相同标准 Task；记录 benchmark revision/manifest。
2. 构造 request，指定 OpenHarness wheel、模型、Provider 和 task selection。
3. `harbor rsi preflight` 校验 wheel、模型、资源和凭据；不调用模型。
4. `harbor rsi run` 通过 TaskClient cache 解析任务，默认不复制 Task。
5. 原生 Job/Trial 调用 OpenHarnessAgent 和选定 Provider，Verifier 写 reward。
6. RSI summary 记录 provenance。

静态量化（阶段一目标实现）：

| 指标 | 官方 Adapter | RSI 阶段一默认 |
| --- | ---: | ---: |
| Benchmark 新增 Adapter 源码 | 1 个 adapter package + templates | 同样 1 个 package；request/config 另 1 个 JSON/YAML |
| Harbor core 修改 | 0 | 0 |
| 新的 Job/Trial/Verifier 实现 | 0 | 0 |
| 强制 freeze/readiness/第二 Task copy | 0 | 0 |
| 必需人工状态/cache 身份 | Dataset revision + Job dir | 同上 + request/provenance；snapshot 关闭时无第二 Task identity |
| Provider 切换需修改 Agent/Task/Verifier | 否 | 否；只改 environment 配置 |

如果 FeatureBench 任务要求 GPU，而当前后端没有 GPU，正确结果是 preflight fail/unsupported，而不是降低资源后产生零分。这个对照证明架构能减少框架改动，但不宣称后端具备所有 benchmark 能力。

## 12. 证据限制和待验证事项

- 最新官方 Harbor 已核对 commit，但尚未将 `dc933be7` 合入阶段分支；其上游变化需要单独 rebase audit。
- 当前环境没有真实 Docker daemon/149 smoke 证据；Remote Docker 的 bind mount、Compose、ownership、controller-loss 和 cleanup 结论中，已验证的是源码语义和历史日志，性能/恢复部分仍待 fault injection 或隔离测试。
- OpenHarness 源码 commit 和包版本已核对；某次历史运行的完整 wheel hash 不在仓库中，不能声称历史结果可由当前源码重新构建。
- E2B、Modal、Science 外部资产、GPU、镜像下载和配额属于 Provider/基础设施验收，不能仅靠本地 Mock 结论覆盖。
- 阶段一测试证明了接口边界和异常隔离，不证明六个 Benchmark 的评分 parity，也不证明所有旧 legacy campaign 可删除。

## 最终判断

官方 Harbor 之所以容易扩展，是因为它把 Benchmark 差异压缩到 Task/Adapter/Verifier，把运行差异压缩到 BaseEnvironment Provider，把 Agent 差异压缩到 InstalledAgent；Job、Trial、cache、artifact、resume 和评分只保留一份。Harbor-RSI 变复杂，是因为在这三条边界之外又增加了任务冻结、第二份输入、外部 launcher、Provider-specific 生命周期和 Pi 继承的 Agent 适配器。

阶段一已经消除了最明确的三项通用回归：默认第二套 Task、Trial recovery 跨任务传播和 OpenHarness/Pi 耦合。剩余最大工作是把 WSL Remote Docker 变成真正的 opt-in `BaseEnvironment` provider，并继续把 readiness、freeze、legacy campaign 降为显式兼容工具。完成这两步后，新 Benchmark 的正常接入应回到“生成标准 Task、选择 Agent、选择 Provider、运行官方 Job”的官方形态。
