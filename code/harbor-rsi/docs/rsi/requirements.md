# Harbor RSI 评测仓库需求

日期：2026-09-24  
状态：交付方向已获用户及师兄确认；本文为需求基线草案，尚不代表实现或运行验收完成。  
配套方案：[实现设计与执行计划](design/2026-09-24-harbor-rsi-design.md)

## 1. 已确认的目标

以官方 Harbor 为基础，将目前分散在 OpenHarness `eval/` 中的 agent 适配、benchmark 接入、环境扩展及必要修复整理进去，形成完整、独立、可运行的 Harbor 评测工作仓库。

最终交付 GitHub 私有仓库，并让师兄获得协作权限。RSI 更新 Harness 后，以 CLI 工件作为被测对象交给该仓库启动评测、获取结果。

以下交流共同确定交付方向：

> “你把那个你们评测的 Harbor 仓库上传到 GitHub 上，然后拉我进去，RSI 这边同步接入一下。”
>
> “整个库上传……主仓是 Harbor 那个主仓，不是 OpenHarness 的主仓。”
>
> “你是这样接的啊，那可能需要你把 Harbor 这块的逻辑导出来，我这边只需要 Harbor 起评测的逻辑。”

用户随后向师兄确认“官方 Harbor 底座 + 我们的接入和必要改动 + 独立 Harness 工件”的交付方式，师兄回答“对”。因此本项目的交付对象是 Harbor 工作仓库，而不是仅将 `eval/` 改名发布。

## 2. 不变的架构边界

```text
RSI / OpenHarness 仓库
    更新 Harness -> 构建 wheel + 工件清单
                             |
                             v
Harbor 评测私仓
    校验输入 -> 官方 Harbor 调度和沙箱
             -> agent adapter 安装、调用原生 CLI
             -> benchmark verifier
             -> 原始结果、状态、日志、RSI 结果摘要
                             ^
                             |
    Harbor dataset 或由 builder 生成的 Harbor task 集合
```

1. Harness 本体及 RSI 优化逻辑仍归 OpenHarness/RSI 仓库所有。
2. 评测运行端只需 Harness wheel 和版本清单，不要求相邻 Harness 源码目录，不导入其内部模块。
3. Harbor 管理 task、环境、执行时限、验证及原始结果；新增入口不得重写一套调度器。
4. Benchmark 的 instruction、环境、交互接口和 verifier 通过 Harbor task 契约接入；评分规则不放进 agent adapter。
5. 同一个兼容的 Harness 工件应能通过同一个 agent adapter 运行不同 benchmark。
6. 代码放在同一 Harbor 仓库不改变上述运行时解耦关系。

## 3. 用户与主要流程

| 使用者 | 输入 | 需要得到的结果 |
| --- | --- | --- |
| RSI 开发者 | 新 Harness wheel、版本身份、benchmark 配置 | 可判断是否完成的机器可读评测结果 |
| 评测维护者 | 新 benchmark 的数据、环境和评分定义 | 复用 Harbor 和同一个 adapter 的接入方式 |
| 仓库协作者 | 新 clone、依赖、凭据及工件 | 按文档完成安装和小样本真实评测 |

主流程：选择固定工件和评测协议 -> preflight -> 创建唯一 job -> 安装 CLI -> 执行任务 -> verifier -> 汇总与归档。只有明确要求恢复时才恢复已有 job，不隐式覆盖旧结果或重复派发。

## 4. 功能需求

| 编号 | 要求 | 完成判据 |
| --- | --- | --- |
| FR-01 | 包含官方 Harbor 源码及可追溯的上游基线 | 能识别官方提交、团队改动和当前安装来源 |
| FR-02 | 提供独立安装方式 | 新环境安装后可运行 Harbor 和团队 adapter；不依赖原 `eval` 路径 |
| FR-03 | 接受显式 Harness wheel | 校验文件、SHA256 和契约版本；不自动选择目录中的第一个 wheel |
| FR-04 | 支持自动化触发 | RSI 可通过稳定 CLI 启动评测并读取 JSON；具体命令名为设计建议 |
| FR-05 | 运行前检查 | 配置、工件、运行后端和必要依赖不满足时，在派发模型任务前失败 |
| FR-06 | 保留 TB2.1 接入能力 | 从新仓库完成真实任务执行、verifier 和结果回收 |
| FR-07 | 验证跨 benchmark 复用 | 至少第二个真实 benchmark 使用相同 adapter 跑通，首选现有 ALFWorld |
| FR-08 | 支持标准数据入口 | 已注册 Harbor dataset 和本地 Harbor task 目录均有验证过的入口 |
| FR-09 | 返回可追溯结果 | job、工件、评测版本、数据版本、预算、逐任务 reward、状态和日志可关联 |
| FR-10 | 正确区分分数和故障 | 正常零分、超时后有效评分、基础设施异常、缺失 reward 分开表示 |
| FR-11 | 正确处理结束和取消 | CLI 退出、远端完成确认、超时清理和 verifier 顺序经测试；清理不能确认时阻止验证 |
| FR-12 | 明确扩展方法 | 新 Harbor-compatible benchmark 不要求修改 Harness 或新增 agent 实现 |
| FR-13 | 私仓协作交付 | 发布已验收提交及安装说明，配置师兄的仓库协作权限 |

已存在的 JobBench/WebShop 接入代码列入迁移清单，作为可选 benchmark 模块保留。它们的准备步骤、独立依赖和验证级别分别记录；在新仓库尚未真实验证的项目不得标记为“已跑通”。

## 5. Benchmark 通用性的准确含义

### 5.1 已符合 Harbor 格式

使用固定 dataset 引用或显式本地任务路径，加上模型、环境和预算配置，复用同一个 adapter。不同 benchmark 可需要不同环境镜像和可选依赖。

### 5.2 尚未符合 Harbor 格式

新增 builder、task 定义、环境和 verifier，使其输出 Harbor 可消费的任务。交互型任务可以提供环境 CLI，但不得通过适配偷偷增强 Harness 的规划、记忆、工具选择或答案获取能力。

### 5.3 不作出的承诺

不承诺任意 benchmark 只改名字即可运行，不承诺任意 agent/模型协议无需适配，不将所有 benchmark 的分数统一当成 reward 的算术平均。

## 6. 被测行为与版本要求

- 工件身份至少包含 wheel SHA256、Harness commit、CLI 契约版本；声明的 commit 与经过构建端核验的 commit 应可区分。
- 评测端校验工件内容哈希，但不能仅凭 manifest 就声称证明了 wheel 与源码完全一致。
- 工具、session、推理强度、context window、token 上限等有效参数必须记录；不得在换 wheel 时悄悄改变评测条件。
- 原生默认行为与历史配置覆盖使用不同协议标识；协议变更不得与历史分数无说明混比。
- Benchmark 来源、revision、task 清单、镜像及 verifier 版本在准备阶段固定；缺少版本身份时不宣称正式可复现。
- 支持 smoke 子集，但结果必须标注 task 子集及覆盖率，不能作为全量成绩。

## 7. 结果要求

RSI 接收到的摘要至少表达：

| 类别 | 内容 |
| --- | --- |
| 身份 | schema 版本、request/job ID、Harbor 工作仓库提交、Harness commit 和 wheel SHA256 |
| 协议 | benchmark ID、数据版本、task 清单哈希、环境、模型、预算、配置哈希 |
| 完成度 | 计划任务数、终态数、有效评分数、缺失或异常任务 |
| 状态 | completed / partial / failed / cancelled，附阶段与原因 |
| 分数 | benchmark 原生 reward 及明确名称、单位、公式和范围的指标 |
| 证据 | 原生 Harbor job 目录、逐任务结果及日志位置 |

任务完成不等于获得正分，命令进程退出不等于任务全部完成。基础设施异常不得直接编码为普通低分。未知 token、费用等字段保持未知，不写成真实的零。

## 8. 非功能需求与边界

1. 首版宿主环境为 Python 3.12+ 的 Linux/WSL2；任务端按所选环境运行。原生 Windows 宿主及 Windows task 不作为首版验收范围。
2. 首批重点验证既有 E2B 路线；Docker 作为明确的可选后端，不把“有 Docker 配置”当成已通过 Docker 运行验收。
3. 使用固定依赖和官方基线；团队版本要能与同版本号的未修改官方包区分。
4. 安装、启动不修改全局 Python 的 `site-packages`，不依赖个人路径、旧 venv 或源工作区的 `PYTHONPATH`。
5. 凭据通过环境或本地不入库配置注入。源码、manifest、测试工件和交付报告不包含真实密钥。
6. 保留 Harbor 上游许可证和来源说明。私仓是保存团队 Harbor 源码的独立仓库，不依赖公开 fork 的私有化能力。
7. 不引入常驻 HTTP 服务、分布式队列或完整评测 UI 作为首版运行前提。
8. 不重写 Harness，不改变 benchmark verifier 来适配某个 Harness 的输出或提高分数。

## 9. 验收矩阵

所有下列状态在本文创建时均为“未在目标新仓库执行”。历史仓库测试、历史成绩和阅读源码不能替代本矩阵。

| 编号 | 验收 | 必需证据 |
| --- | --- | --- |
| AC-01 | 新环境安装且离开仓库 cwd 后仍可调用 | Python/依赖版本、Harbor import 来源、wheel 安装检查 |
| AC-02 | 目标仓库不依赖原 Harness 源码 | 独立环境只提供新仓库、工件及数据，清空原项目路径仍运行 |
| AC-03 | TB2.1 真实 smoke | 完整 CLI 日志、task ID、verifier 输出、reward 和终态 |
| AC-04 | ALFWorld 真实 smoke | 同一 adapter 身份；固定 episode；环境、verifier、reward 全链路 |
| AC-05 | 替换两个兼容 Harness 工件 | 仅工件身份变化，eval 代码不变，各自记录正确 commit/hash |
| AC-06 | 无共享挂载的日志回收 | 模拟传输测试及 E2B 实测，不依赖宿主文件自动出现 |
| AC-07 | 超时与取消 | 后代清理证据、正确异常分类；清理失败时 verifier 未启动 |
| AC-08 | 异常与计分边界 | 零分、缺失、CLI 错误、verifier 错误、重复尝试和部分完成测试 |
| AC-09 | RSI 消费契约 | 调用入口、退出码、JSON 校验、工件切换、非零基础设施失败 |
| AC-10 | 交付可复现 | 新仓库固定提交、运行命令、版本、job 记录和限制说明 |
| AC-11 | GitHub 私仓交付 | 私有可见性、发布提交、协作权限及可访问的仓库地址 |

真实 smoke 先单 task、并发 1，通过后再运行少量代表任务。模型获得零分不自动判定接入失败；verifier 有效完成、证据完整且异常被正确分类才是接入验收依据。高分也不能替代这些条件。

Smoke 通过只可标记“真实小样本已验证”。全量可运行、正式成绩、长任务恢复、第二后端分别验收，不相互替代。

## 10. 首版交付物

- 完整 Harbor 私仓及上游基线说明。
- 可独立安装的团队版本、锁定依赖及版本识别方法。
- OpenHarness CLI adapter 和必要的生命周期、环境扩展。
- TB2.1、ALFWorld 的准备及启动说明；其他已迁入 benchmark 的实际验证级别。
- RSI 输入输出契约、示例配置、新增 benchmark 指南。
- 自动化测试及可追溯的真实 smoke 验收报告。
- 师兄可访问的仓库和协作权限。

## 11. 实施前后的边界信息

以下不影响当前需求和设计文档编写，但必须在对应阶段落定：

| 信息 | 落定时点 | 当前处理 |
| --- | --- | --- |
| 私仓归属、名称、师兄账号及角色 | 发布和邀请前 | 仓库名建议 `harbor-rsi`，不假设 URL 中的账号就是邀请对象 |
| RSI 最终调用方式 | 实现入口前 | 默认设计为同步 CLI + 文件 JSON，暂不建设服务 |
| 真实评测模型、运行凭据和费用范围 | 云端 smoke 前 | 从已有授权与可用环境确定，仅安排小样本验收 |
| 两个兼容的 Harness wheel | 工件切换验收前 | 由 RSI/构建端给出，记录契约及 provenance |
| 首批具体 task 清单和数据 revision | 第一次真实运行前 | 用预算可覆盖的固定样本，保存选择依据 |

## 12. 本轮工作状态

本文是实施前需求基线，验收状态不能从前文的初始描述推断。实施已启动，
当前运行证据和未完成项以同目录的 `validation.md` 为准。
