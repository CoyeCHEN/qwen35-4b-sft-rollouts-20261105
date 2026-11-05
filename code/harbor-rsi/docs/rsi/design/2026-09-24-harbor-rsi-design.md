# Harbor RSI 实现设计与执行计划

日期：2026-09-24  
状态：基于已确认需求的设计方案；路径和新增接口是待实现设计，不能作为现有命令使用。  
需求基线：[Harbor RSI 评测仓库需求](../requirements.md)

## 1. 结论与方案选择

采用“官方 Harbor 源码底座 + 随 Harbor 安装的团队扩展 + 小范围核心修复”，交付一个 GitHub 私有工作仓库。Harness 以外部 wheel 输入，benchmark 以 Harbor dataset/task 接入。

| 方案 | 收益 | 代价与适用性 |
| --- | --- | --- |
| 官方 Harbor 底座和团队扩展同仓，推荐 | 满足师兄的仓库预期；安装后修复和 adapter 一并生效；运行链路可完整审查 | 需要维护清晰的上游差异并验证打包、CLI 和核心回归 |
| 独立 eval 包依赖官方 Harbor | 初始迁移较少、接近当前组织 | 与已确认交付形式不符，且核心修复仍需额外安装步骤 |
| 将 OpenHarness 与全部评测代码合成大仓库 | 暂时减少路径迁移 | 模糊被测对象与评测端版本，不符合师兄明确要求 |

同仓不等于把所有 benchmark 逻辑塞进 Harbor 核心。核心负责执行机制，扩展负责工件协议和团队运行契约，benchmark 目录负责任务与评分协议。

## 2. 核查证据与基线

### 2.1 固定源码身份

| 对象 | 已核实身份 | 用途 |
| --- | --- | --- |
| 官方 Harbor | `harbor-framework/harbor`，tag `v0.23.0` | 首版源码底座 |
| tag 对象 | `3c305dc5611e3600afc3c818735a82322f0264f8` | annotated tag，不能误当源码 commit |
| tag 指向的 commit | `1e5c5c6db929a10a140d05e606882c671ae20729` | 锁定上游源码 |
| 官方 `src/harbor/trial/trial.py` SHA256 | `757f34424e35ea6e924484bff9ae75464e94acd5dec3d769bc65a9518ada79a8` | 与现有补丁 `ORIGINAL_SHA256` 完全一致 |
| OpenHarness 远端评测来源 | `NiuHechang/open-harness2@9957210811473f3e5f7d158646000e8977afeaa7` | 首轮已提交迁移基线，2026-09-24 核查时的 main |

官方 pyproject 声明 Python >=3.12、Apache-2.0、`uv_build` 构建器、`src/harbor` 包和 `harbor` CLI，已有 `packages/*` workspace。适应其结构，不另起第二套运行核心。

官方依据：

- [Harbor pyproject](https://github.com/harbor-framework/harbor/blob/1e5c5c6db929a10a140d05e606882c671ae20729/pyproject.toml)
- [官方 agent phase](https://github.com/harbor-framework/harbor/blob/1e5c5c6db929a10a140d05e606882c671ae20729/src/harbor/trial/trial.py#L554)
- [官方 SingleStepTrial](https://github.com/harbor-framework/harbor/blob/1e5c5c6db929a10a140d05e606882c671ae20729/src/harbor/trial/single_step.py#L75)

迁移来源依据：

- [现有评测包依赖](https://github.com/NiuHechang/open-harness2/blob/9957210811473f3e5f7d158646000e8977afeaa7/eval/pyproject.toml)
- [现有 TB2.1 launcher](https://github.com/NiuHechang/open-harness2/blob/9957210811473f3e5f7d158646000e8977afeaa7/eval/scripts/run-tb21.sh)
- [现有 adapter](https://github.com/NiuHechang/open-harness2/blob/9957210811473f3e5f7d158646000e8977afeaa7/eval/openharness_harbor/agent.py)
- [现有生命周期补丁](https://github.com/NiuHechang/open-harness2/blob/9957210811473f3e5f7d158646000e8977afeaa7/eval/scripts/apply_lifecycle_patch.py)
- [现有新增 benchmark 指南](https://github.com/NiuHechang/open-harness2/blob/9957210811473f3e5f7d158646000e8977afeaa7/eval/docs/add-benchmark.zh-CN.md)

### 2.2 不能混为一谈的本地版本

`RSI/open-harness2/`、`open-harness2-latest/` 和 `open-harness2-eval-merge/` 是不同 checkout。本地 `open-harness2/eval/harbor` 不是远端 main 的当前目录，后者使用 `eval/openharness_harbor`。

本地工作树存在未提交变化，且有一些与远端不同的 transport、adapter 和环境实现。不能整体复制某一个目录后宣称其等同于远端 main。迁移时以固定远端提交为主线，对本地差异逐文件记录来源、行为影响和采用理由；有价值的修复以独立变更及测试迁入。

### 2.3 已发现的具体问题

| 发现 | 影响 | 设计处置 |
| --- | --- | --- |
| `run-tb21.sh` 默认寻找相邻 `open-harness-benchmarks/harbor` | 复制 eval 后仍无法独立运行 | 从当前安装的团队 Harbor 启动，不寻找另一个 checkout |
| launcher 会寻找第一个匹配 wheel | 可能测试错误候选版本 | 正式入口强制显式 wheel + SHA256 |
| 补丁直接修改安装包并 import `openharness_harbor.lifecycle` | 安装顺序、包来源和 PYTHONPATH 容易影响行为 | 将修复纳入 Harbor 源码和自身包依赖 |
| 远端 adapter 继承 `Pi`，但覆盖 install/run | 存在模型配置和继承行为需要核对 | 首次迁移保持继承，增加契约测试，不直接重写 agent |
| adapter 显式设置四个工具、`persist=False`、`--no-session`、推理及 token 参数 | 与早期本地“保留原生默认”协议不同 | 明确历史 profile 与新 RSI 原生 profile，不静默混合 |
| `_wait_for_completion_marker` 只等宿主 `logs_dir` 文件 | 对没有共享挂载的 E2B 存在完成确认风险 | 使用 Harbor 文件下载接口读取远端完成状态并真实验证 |
| 远端单测 mock 掉了上述完成等待 | 不能证明真实 E2B 完成链路正确 | 增加无共享挂载 transport 测试及云端 smoke |
| `run()` 有重新安装 CLI 的 fallback，stdout 经 grep 过滤 | 安装计入执行预算、日志或退出码语义可能变化 | 安装阶段失败单独归类；保存原始输出并审查退出码传播 |
| 现有结果逻辑包含 benchmark 名称推断和有效子集平均 | 新 benchmark、部分完成或重试可能误读 | 运行 manifest 显式声明 benchmark、范围及聚合规则 |
| 构建/工件验证脚本依赖 OpenHarness Git 和 setuptools 布局 | 不能当作独立评测的运行前提 | 构建端生成 provenance，评测端只验证输入契约和内容哈希 |

以上是静态核查结论与风险识别，不是已重现所有运行故障。实现时先补可复现测试，再修复对应问题。

## 3. 仓库与安装设计

建议仓库名 `harbor-rsi`，保留官方提交历史、许可证和来源说明，在其上形成小而可解释的团队提交。GitHub 建立独立私仓；`upstream` 指官方 Harbor，`origin` 指团队私仓。发布只推送明确的目标分支和必要标签，不镜像推送整个来源仓库的 refs。

建议目标结构如下，新目录是设计，不表示已创建：

```text
harbor-rsi/
  pyproject.toml                 # 官方 harbor distribution，团队版本可辨识
  uv.lock                       # 按首版运行和测试环境验证过的依赖
  LICENSE
  UPSTREAM.md                   # 上游 SHA、团队改动索引、来源版本
  src/harbor/
    agents/installed/open_harness.py
    environments/               # 官方后端及明确选用的 E2B 扩展
    trial/agent_lifecycle.py     # 通用、按 adapter 选择启用的生命周期逻辑
    trial/process_supervisor.py
    extensions/rsi/
      runner.py                 # 组装配置和调用原生 Harbor CLI
      models.py                 # request/manifest/result 契约
      report.py                 # 读取原始结果和校验完整性
      trajectory.py             # OpenHarness 输出格式转换
      profiles/                 # 随包安装的运行协议配置
    cli/                        # 保留原命令，新增 rsi 子命令组
  benchmarks/
    terminal_bench_2_1/          # preset、说明、显式 recovery 入口
    alfworld/                   # builder、模板、数据准备说明
    jobbench/                   # 可选依赖和独立评分协议
    webshop/                    # 可选依赖和独立环境准备
  tests/rsi/
  docs/rsi/
```

安装时必须包含运行所需的 Python 代码、supervisor 资源和默认 profile；从非仓库 cwd 启动仍能访问。Benchmark 构建资料可以随源码分发，但所有运行时 import 指向已安装包，不依赖根目录临时加 `PYTHONPATH`。

原有 benchmark 子包按其 packaging 保留或迁到官方 workspace 的 `packages/*`；选择依据是模板和资源能否从安装产物读取。不要仅移动文件而破坏 `importlib.resources`、脚本相对路径或镜像构建上下文。

首版保留 distribution 名 `harbor`，采用可辨识团队版本，例如 `0.23.0+rsi.1`，并在 manifest 记录官方 SHA 与团队完整 commit。安装入口明确使用本地 Harbor 项目；核验依赖解析没有从索引重新装入未修改的同名官方包。`harbor --version`、包 metadata、import 来源和 manifest 应一致。

使用独立 venv，先验证 root wheel 的非 editable 安装，再验证开发安装。E2B 按需安装 extra，测试依赖保持必要范围，避免为少量测试引入全部云提供商。

## 4. 迁移清单

| 现有内容 | 目标 | 迁移动作与验证 |
| --- | --- | --- |
| `openharness_harbor/agent.py` | `harbor.agents.installed.open_harness` | 保留安装/CLI 适配职责，明确 profile，验证原始指令及退出状态 |
| trajectory、runtime config、results、metrics | `harbor.extensions.rsi` | 提取被运行入口使用的部分，保留原始结果，不依赖 monitor |
| lifecycle、process_supervisor | `harbor.trial` 下的机制模块 | 调整资源路径、异常引用和测试，核心不得反向依赖可选 benchmark 包 |
| `apply_lifecycle_patch.py` | 核心源码提交 + 安装检查 | 新仓库不再运行字符串替换补丁；旧脚本仅作迁移来源记录 |
| e2b_one_hour / resumable / reconnect | 已安装的环境扩展 | 明确选用，不自动改变 timeout 或重复执行 agent |
| TB 配置和 task 特定恢复 | benchmark 资料 + 已安装环境代码 | runtime import 不能指向未安装的根目录；QEMU recovery 显式选择 |
| ALFWorld builder、模板、测试 | benchmark 模块 | 固定数据和 task 清单，保留原有 verifier/隐藏数据边界 |
| JobBench/WebShop builder、环境、judge 配置 | 可选 benchmark 模块 | 保留任务协议和依赖，不引入核心的强制安装路径 |
| 版本构建、fetch、record-artifact 脚本 | 可选 producer 工具或外部 RSI | 使用显式 source/ref/output；正常评测无需源码和网络 fetch |
| campaign/watch 脚本 | 首轮不作为基础启动前提 | 只迁必需结果规则；原有完整恢复流程单独保留和验证 |
| monitor 和历史报告 | 可选后续模块 | 不作为“Harbor 起评测”的交付前提，不复制运行缓存冒充验收 |

固定源与本地修复的采用表至少记录：源路径、源 commit 或文件 SHA256、目标路径、是否改变行为、对应测试。不同来源的同名文件不得最后写入者覆盖。

## 5. RSI 调用契约

### 5.1 首版接口

默认选同步 CLI + 文件 JSON，因为可从 Python、Shell 或其他 RSI 实现调用。保留原生 `harbor run`；增加薄的 `harbor rsi` 子命令组，不建设 HTTP 服务。

设计中的命令形态：

```text
harbor rsi preflight --request /absolute/request.json
harbor rsi run --request /absolute/request.json --output /absolute/result.json
harbor rsi summarize --job-dir /absolute/jobs/JOB_ID --output /absolute/result.json
```

`preflight` 进行结构和本地检查；远端镜像/账号验证另用显式环境检查，不能把 dry-run 描述成远端已就绪。`run` 使用同一配置解析结果，通过同一 venv 的 Harbor 可执行文件调用原生命令，参数用 argv 数组传递，不通过 shell 拼接。

原生 Harbor 的 job/task 配置模型负责格式校验，runner 只完成工件身份、profile 展开、输出约定和完成判定。实现前核对固定版本的 CLI schema，测试最终渲染命令，不硬猜字段别名。

### 5.2 请求字段

| 字段 | 规则 |
| --- | --- |
| `schema_version` | 首版为 1，未知主版本拒绝 |
| `request_id` | RSI 提供或 runner 生成；重复请求不得自动派发第二次 |
| `artifact.path` / `artifact.sha256` | 显式 wheel 绝对路径和完整 SHA256 |
| `artifact.harness_commit` | 完整提交身份，附来源声明/构建验证状态 |
| `artifact.cli_contract` | 明确的兼容协议版本，不根据文件名猜测 |
| `benchmark.id` | 明确 benchmark 身份，不能仅靠 task 名称前缀推断 |
| `benchmark.source` | registry 引用或本地 task 目录，二者互斥 |
| `benchmark.revision` | 准备阶段解析后的固定 revision 或内容清单哈希 |
| `selection` | 明确 task ID 集合；可使用限制数量做 smoke，但执行前保存解析清单 |
| `profile` | `native-cli-v1` 或显式历史协议，见第 6 节 |
| `model` / `agent_options` | 经过契约校验的配置，不包含密钥值 |
| `environment` | 后端及必要设置；E2B 恢复策略显式声明 |
| `execution` | 并发、attempts、预算、输出目录；首版 RSI 入口仅接受 attempts=1，不自动重试有效低分 |

请求文件中不存模型密钥。轮子路径不可用、哈希不匹配、未知 CLI 契约和不受支持的 provider 在启动前报错。预检只说明输入与接口匹配；真实模型请求兼容性由 smoke 验证。

### 5.3 工件边界

RSI 或独立 producer 构建 wheel，生成声明 commit、CLI 契约和 SHA256 的 manifest。producer 可在源码可见时验证 payload；runner 只校验已提供内容，不强制访问 OpenHarness Git，也不承诺凭 SHA256 可证明源码 provenance。

正式运行开始前将候选 wheel 固定到按内容哈希隔离的工件缓存，并记录副本哈希；每次安装使用该固定副本，避免同路径 wheel 在不同 task 安装之间被重新构建替换。

### 5.4 输出与退出码

输出采用版本化 JSON，同时保留原生 Harbor job 目录为证据来源。摘要通过临时文件与原子替换写入；不得覆盖别的 request/job 的产物。

摘要包括 `run_status`、`scope`、请求及 job 身份、上游/团队/Harness 版本、artifact hash、有效配置 hash、dataset revision、task manifest hash、预期/终态/评分任务数、逐任务 reward 和分类、指标定义、日志位置。未知费用为 null。

首版退出码建议：0 为所选范围正常完成（允许正常零分）；2 为输入或预检失败；3 为基础设施/完整性失败或 partial；130 为用户取消；1 为未分类的 runner 内部错误。任务级 agent 错误是否仍有有效评分由 benchmark 协议决定，原始状态始终保留。

只有 selected task 全部达到协议允许的终态且评分有效，才能标记 completed；completed smoke 的 `scope` 仍为 subset，不代表完整 benchmark。进程 exit 0 不能单独决定 completed。

`request_id` 在输出区以原子创建的 manifest/锁占用。已有运行或结果时返回已有身份或明确拒绝，首版不实现自动恢复调度。显式人工恢复继续使用 Harbor 已验证能力，禁止 runner 通过重新启动模拟 reconnect。

runner 接到取消信号时，将取消转交给它启动的 Harbor 进程并等待其清理路径；取消等待本身有上限。若宿主强制终止、远端不可达或超出清理等待窗口，摘要标记 `cleanup_unconfirmed`，不能声称远端已停止。进程退出后的结果仍须核对原始 job 状态，不能把仅杀掉宿主子进程当作沙箱清理成功。

## 6. Adapter 与评测协议

### 6.1 继承与能力边界

首轮以固定远端 adapter 为迁移来源，保留当前 Pi 继承关系及其所需的模型连接支持，测试证明实际安装的是 Harness wheel、运行的是 OpenHarness CLI，没有执行 Pi agent。不要同时改继承、CLI 行为和 benchmark，以免失去可解释的回归基准。

若契约测试发现继承链强制注入 Pi 行为，再以独立变更改成 `BaseInstalledAgent`；这一调整必须有相同工件、profile 和任务的对照证据。

### 6.2 显式 profile

| profile | 用途 | 行为 |
| --- | --- | --- |
| `legacy-eval-v1` | 对照旧远端评测条件 | 显式记录旧工具集、session 禁用、推理/token 等覆盖；不称为原生默认 |
| `native-cli-v1` | 建议作为新 RSI 评测默认 | 不隐式关闭 session，不强制裁剪工具；仅应用请求中明确的模型/预算及协议所需设置 |

两种 profile 的结果不混为同一实验。采用 native 作为默认是本设计建议，不是从历史分数推导的事实；实现时写进发布说明，并用行为测试确认有效配置。首版 smoke 至少验证用于 RSI 交付的 native profile，legacy 通过契约回归并注明真实验证级别。

CLI 版本差异通过已知契约映射处理，例如某版本是否支持 prompt file、literal 参数、配置文件结构。读取实际 wheel 的 help/version 及 producer 声明确认，不将任意报错后重试其他参数作为兼容策略。

### 6.3 执行与完成确认

- `install()` 负责依赖和 wheel 安装、版本检查；失败归为 setup。运行阶段不隐式重新安装后继续计分。
- task cwd 和原始 instruction 由 Harbor 提供。支持 prompt file 的契约通过文件传输；其他契约严格 shell quoting，不改写 instruction。
- stdout/stderr 分开完整保存。ATIF/监控所需过滤或转换在原始文件之外进行，不用 grep 过滤后的管道状态替代真实 CLI 退出码。
- 完成状态在沙箱内原子写入，包含当前 trial/attempt 身份和 CLI exit code。开始执行前清除该次目标 marker，不消费旧文件。
- 通过环境 API 获取 marker，不假设宿主与沙箱共享目录；传输和等待受官方 agent deadline 约束。退出后日志仍由 Harbor 的既有回收链路收集。
- 模拟环境必须覆盖 marker 延迟、缺失、损坏、身份不符和非零 exit，真实 E2B 必须验证无共享挂载路径。

## 7. 生命周期修复的核心集成

将现有 supervisor/lifecycle 机制纳入 Harbor 源码，不继续使用安装后的字符串补丁。当前官方 agent phase 的哈希已匹配，修改位置可精确定位。

为 adapter 增加明确的生命周期能力声明，默认关闭，新 OpenHarness adapter 开启。`Trial` 对开启此能力且满足 Linux 环境要求的 adapter 使用屏障；其他官方 agent 保留原执行路径。避免首版就把修复无条件施加给全部官方 agent、Windows task 和多轮交互流程。

要求保持：

1. task 原有 agent deadline 不延长；监督准备与运行阶段的预算归属显式记录。
2. 正常结束不杀死 task 合法后台服务。
3. agent timeout 后停止其受管理的后代，确认清理再按 Harbor 原有规则运行 verifier。
4. cleanup 失败抛专用基础设施异常，不伪装为 AgentTimeoutError；当前 SingleStepTrial 仅捕获指定 agent 异常，清理异常必须阻止正常 verifier 流程。
5. 外部取消单独标为 cancelled，完成清理和可获取日志回收后退出；无法确认清理时记录状态，不宣称正常完成。
6. 测试覆盖 setsid、double fork、PID 重用、清理时新 fork、早期取消和非 OpenHarness agent 回归。

首版真实验收聚焦当前 benchmark 的 single-step task。多步任务、simulated user 和其他 agent 的 managed lifecycle 不列为已支持，不能仅因共享 Trial 基类就作承诺。

## 8. 环境、预算与 Benchmark 迁移

Harbor task deadline、模型 token/动作预算与 E2B sandbox lifetime 是三种限制，配置和结果分别记录。恢复同一 sandbox 不等于延长 task deadline，也不等于重新执行 agent。

E2B one-hour profile 只接收该寿命能覆盖准备、agent、verifier、收集及余量的任务；不能因为 canary 任务短就宣称整个 TB2.1 可用一小时配置完成。长任务使用显式 resumable profile 并单独验收，账号支持更长 lifetime 时可以选标准 E2B。

推荐首批 TB2.1 与 ALFWorld 在同一 E2B 后端验证，以隔离“替换 benchmark”这个变量；若 ALFWorld 当前镜像仅完成 Docker 准备，则先完成同后端准备再宣称该路径支持，也可单列 Docker 的真实验收结果。不同后端不共享运行成功结论。

对标准 dataset 直接使用 Harbor 的解析、下载和 task 配置；对本地 builder 产物生成确定性 task manifest。新增 benchmark 只增加数据/环境/verifier 及必要 metric 定义，不复制一份 OpenHarnessAgent。

TB2.1、ALFWorld 原 verifier 保持不变。JobBench 按自身 total/max 权重汇总，WebShop 保留 Task Score 和 Success Rate。未知 benchmark 先输出原始 reward 和完整性，不猜一个通用“总分”。

## 9. 结果完整性与比较

复用当前 results/metrics 中经过测试的解析函数，但不得只扫描已出现的 task 结果推断全集。分母来自运行前固定的 task/attempt manifest，每次 attempt 使用稳定身份。

首版 RSI 入口每 task 仅接受一个 attempt；没有自动 best-of、没有因为分数低而重跑。原生 Harbor 的多 attempt 功能保持原状，但不冒充已纳入 RSI 摘要契约。将来增加恢复或多 attempt 时，必须定义首个有效结果或其他明确协议，不继承偶然的文件扫描顺序。

超时后存在官方有效 reward 时，可按 benchmark 协议计分，同时保留 timeout 状态。环境失联、setup 失败、清理失败、verifier 无结果等保留未评分，不转零。原始错误不因摘要生成成功而被抹去。

指标必须带名称、单位、范围及聚合范围。subset 平均可以用于调试，但不得替代全量主指标。输入的 eval commit、数据、任务范围、profile、模型、预算和环境变化时，比较报告必须标注差异，不能只看 Harness commit。

## 10. 分阶段执行计划

### P0：冻结来源与差异清单

输入：第 2 节两个固定远端提交、本地候选修复、现有测试。

工作：建立逐文件迁移表；复核官方 hash；确认候选 wheel 的 CLI 契约；列明与历史 profile 的差异。新工作目录与现有三个 OpenHarness checkout 隔离，不移动或覆盖其工作树。

产物：UPSTREAM 来源记录、迁移表、验收任务与工件清单。出口条件：无来源不明覆盖、官方基线可重建。

### P1：建立 Harbor 工作仓库和安装闭环

工作：从官方固定历史建立新工作仓库；引入团队版本识别；迁入最小 adapter、运行 helper 和资源；配置依赖锁与按需 extra。GitHub 发布在本地结果可审查后执行。

验证：新 venv 构建/安装 Harbor wheel；清除原工作区 PYTHONPATH；从其他 cwd 检查 CLI、import 来源、资源与 profile；验证未误装官方同名包。

产物：可独立安装的源码和工件。出口条件：AC-01、AC-02 的安装部分通过。

### P2：执行契约与生命周期修复

工作：迁移受管理进程机制为核心改动；落实显式 profile、原始输出、准确 exit code、远端完成确认和取消传播；补充缺失的 transport/生命周期测试。

验证：现有 adapter、trajectory、lifecycle 测试迁移运行；新增无共享挂载 transport、非零退出和异常 verifier 顺序测试；运行受影响的官方 Trial/agent 单元测试。

产物：明确的核心 diff 和行为证据。出口条件：关键异常测试通过，正常及取消路径均不提前评分。

### P3：RSI 入口与 Benchmark 配置

工作：实现第 5 节薄 CLI；固定请求和结果 schema；加入内容哈希工件缓存、预检、任务 manifest、唯一 job 身份与原子摘要；迁入 TB2.1/ALFWorld 配置和准备材料。

验证：实际解析官方配置；无模型 dry-run；失败早于派发；结果 fixture 覆盖正常零分、partial、未知 reward 字段、异常和重复请求。替换 benchmark 不改变 adapter。

产物：请求示例、输出示例、准备与运行文档。出口条件：AC-08、AC-09 的离线部分通过。

### P4：真实可运行性验收

顺序：独立环境本地确定性任务 -> TB2.1 单 task/并发 1 -> ALFWorld 单 episode/并发 1 -> 两个 bench 各少量代表任务 -> 固定条件替换两个 Harness wheel。

确定性测试只验证管道，不是 benchmark 成绩。模型 smoke 使用实际可用且已授权的凭据和有限预算；遇到新的安装、环境、adapter 或 verifier 错误先修复、补测试，再继续。

记录：eval/upstream commit、wheel hash、CLI profile、Python/依赖、task revision/list、模型、环境、有效配置、命令、时间、job ID、逐任务证据和验收结论。无法运行某项时明确未通过，不能用历史分数填补。

产物：真实 smoke 报告及机读结果。出口条件：需求 AC-01 至 AC-10 逐项有证据；第二后端、恢复或全量按单独范围标注，不扩大声明。

### P5：迁移其余模块与私仓交付

工作：完成已列入范围的 JobBench/WebShop 模块迁移及离线契约验证，分别标注真实验证情况；整理 README、新增 benchmark 指南、上游差异说明和限制；发布验收过的提交，配置协作权限。

如果本阶段改变依赖锁、公共 adapter、环境或结果处理，必须针对最终代码重跑受影响的安装/契约测试及真实 smoke。只修改说明文档或隔离的可选资料时，不无故重复模型评测。发布报告记录实际验证的代码身份，不能只引用 P4 阶段已经过时的提交。

发布前检查实际 staged 文件和历史来源，排除环境凭据、wheel、数据缓存及未审查的运行日志。保留上游许可证。仓库归属和邀请账号使用真实确认值，不从对话推定。

产物：私仓地址、发布 SHA、协作权限、可执行交接文档。出口条件：AC-11，协作者可复现最小运行。

## 11. 测试策略与证据边界

| 层次 | 验证对象 | 不足以证明的事项 |
| --- | --- | --- |
| 静态核查 | 来源、依赖、配置、调用路径 | 任何真实模型或远端环境成功 |
| 单元与契约测试 | 输入输出、退出码、超时机制、评分公式 | 镜像可构建、云端可访问 |
| 打包与独立安装 | 非 editable 运行、包资源、无旧源码依赖 | benchmark 完整准备 |
| 确定性本地任务 | 完整 Harbor pipeline 和 runner | 正式 benchmark 分数 |
| 真实 smoke | 指定 backend/task/profile 的可运行性 | 全量完成、其他后端和恢复策略 |
| 小批与工件切换 | 跨任务、跨 benchmark、跨候选的一致调用 | 未测试任务的性能及正式榜单排名 |

首版不以“所有测试名称都收集到”或只通过 mock 为验收。尤其 marker transport、任务用户安装权限、Python venv 可用性、E2B lifetime 和 verifier 运行都需要真实证据。

修改公共 Trial 后，运行受影响的官方测试与团队生命周期测试；只有新增失败或新的共享行为风险才扩大回归。不要将整个官方云服务测试矩阵无差别列为本次前提。

## 12. 风险、取舍与处理

| 风险 | 处理 |
| --- | --- |
| 本地修复比远端新，但来源混乱 | 固定已提交主线，逐项迁入本地修复并记录 hash 与测试 |
| native profile 改变旧评测条件 | 版本化 profile，保留 legacy 描述，不混比历史成绩 |
| 核心修复影响官方其他 agent | 明确能力开关，首版仅新 adapter 启用，增加原路径回归 |
| 团队 Harbor 被依赖解析替换 | 独立环境、本地 source 约束、团队版本和 import 来源检查 |
| 脱离源码后丢失模板/supervisor | 构建 wheel 后检查包资源，从任意 cwd 执行 |
| marker 无共享文件同步 | 环境 API 获取远端状态，单测不 mock 掉关键 transport |
| 环境丢失被误判低分 | 阶段化异常与完整性检查，reward 缺失保持未评分 |
| 迁入所有功能造成首版膨胀 | 主链路先验收；monitor、长流程自动恢复和服务化保持可选 |
| 上游版本演进 | 保留小范围核心 diff，先在隔离分支复核基线及回归再升级 |

不提前抽象自动发现的 benchmark 插件系统。首版沿用显式模块、Harbor 原生扩展点和独立 benchmark 准备流程；第二个 benchmark 证明复用后，再根据实际重复提取公用代码。

## 13. 当前完成情况与下一步

- 已确认：以完整 Harbor 工作仓库交付，而不是仅发布 eval 包。
- 已核实：官方 tag、commit、核心文件 hash、固定远端 eval 来源及主要迁移风险。
- 已完成：需求、接口建议、源码组织、迁移清单、执行阶段和验收标准文档化。
- 本节是设计形成时的状态；实施后的验证和交付状态见 `../validation.md`。

建议按 P0 -> P1 -> P2 -> P3 -> P4 -> P5 执行。实现评审重点是 profile 行为、生命周期启用范围、RSI 输出契约和第二 benchmark 的真实验证，不再重新讨论交付物是否是 Harbor 仓库。
