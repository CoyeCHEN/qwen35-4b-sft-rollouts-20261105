# 四基准全量接入与验收记录

2026-10-14，基线 `098be17d22deea658131570366bd8ee93621b88a`，工作分支
`codex/full-benchmark-integration`。这是持续更新的准备记录，**不是 551 题正式评测完成报告**。
用户随后授权执行全部551题并取消费用等待；最新又要求启动前停止并详细汇报，当前不派发正式评测。

## 当前验收结果

最新启动前快照：551/551必要原生无模型环境门槛全部通过，正式Actor/Trial/评分仍0。用户最新要求“先别正式启动评测，启动评测前停止并做详细汇报”，因此保持停止。详细结论见 [正式评测启动前报告](full-551-prelaunch-report.md)。

| 指标 | ALFWorld | ClawGym | TB2.1（选定 E2B87/Remote2） | JobBench main | JobBench easy |
|---|---:|---:|---:|---:|---:|
| 冻结官方任务 | 134 | 200 | 89 | 65 | 63 |
| 已生成、原生TaskClient解析、静态检查 | 134 | 200 | 89 | 65 | 63 |
| 动态环境就绪（独立清理后） | 134 | 200 | 89 | 65 | 63 |
| 实际Verifier路径通过 | 134 | 200 | 89 | 65 | 63 |
| 历史真实Agent最终合法评分 | 10 | 10 | 10 | 10 | 0 |
| 历史首次Infrastructure Error | 0 | 0 | 2 | 0 | 0 |
| 当前轮正式完成评分 | 0 | 0 | 0 | 0 | 0 |
| 全量原生Job配置 | 有 | 有 | 两个原生分区Job | 有 | 有 |

完整逐题所选Provider、原始hash/执行hash、原生Result和清理见 [task-readiness.csv](../../artifacts/benchmark-readiness/task-readiness.csv)、[selected-provider-readiness.csv](../../artifacts/benchmark-readiness/selected-provider-readiness.csv)、[all551 gate proof](../../artifacts/benchmark-readiness/evidence/selected-provider-all551-gates.json)。原默认149状态保存在 `default-provider-task-readiness-before-selected-plan.csv`，没有把E2B成功写成149网络恢复。

TB选定镜像89/89缓存并核验官方内容身份。原始E2B任务87个完整通过，92次尝试包含4个原异常/取消及一次不同条件HF重复验收；两道QEMU在生产Remote独立完成安装fixture和官方Oracle。QEMU startup及Alpine真实官方测试各1 passed/Reward1；它们是Oracle无模型验收，不能当正式Agent成绩。所有完整数据集的准备轨迹/失败/恢复已私有归档。

最近通用Verifier-only缓存修复源码 `e2195dd2`，固定core/Provider运行时仍正常安装的030d6ab8普通wheel，其后src/Provider源码无改动。551任务/六个原生Jobs的六项check-only Runtime Attestation全部通过。生产SSH/CLI不变，SDK研究不并入，正式模型配置不改变。Claw hybrid和Job采用既定替代Judge口径，实际Judge执行已证实但不等同官方指定模型成绩。

GitHub d1bb49e6的Linux/Windows/Build/Ruff/ty全部真实成功；最新e2195dd2的所有Runner因账户付款/支出额度限制未启动，见 `evidence/ci-e2195dd2-billing-block.json`。不得声称最新源码CI已通过。旧d4网络runtime失败保留，根因未定。

main/easy恢复、E2B模板/APT404、protein最初ensurepip失败与控制器取消、Remote缺curl/sshpass的Verifier失败均留原始Result/日志，旧40/42不改。恢复后的551就绪不代表历史首次无故障。以下较早时间快照保留历史，当前表和启动前报告优先。

## 官方来源和数量口径

| 数据集 | 冻结来源 | 数量确认方式 |
|---|---|---|
| ALFWorld valid_unseen | `alfworld==0.4.2`；json_2.1.1 JSON/PDDL、json_2.1.3 tw-pddl | 上游 AlfredTWEnv 从 341 个候选中枚举 134 个受支持可解游戏；134 个 game 文件逐一匹配官方 release archive |
| ClawGym | [官方仓库](https://github.com/ClawGym/ClawGym-Bench/tree/c8cbd1d0df033af24fc14064d40d6964ca8f611f)，`c8cbd1d0df033af24fc14064d40d6964ca8f611f` | 官方 JSONL 200 行，SHA-256 `b2fede029e73a769ad294089a735108be4396294590ec00c9527ac60b1da0f72` |
| TB2.1 | 原生 Registry `terminal-bench/terminal-bench-2-1`，每题不可变 SHA-256 ref | 冻结 89 个原生 TaskConfig，所有下载后的 Packager 内容 hash 对照 ref |
| JobBench main/easy | [官方 HF 数据源](https://huggingface.co/datasets/JobBench/job-bench/tree/d43a66575635da0d3f6cb9a20976dc1a60f3ffc9)，`d43a66575635da0d3f6cb9a20976dc1a60f3ffc9` | 分页获得完整目录树 1,370 项；main 65、easy 63，分别保留 Split |

JobBench Judge 来自 [官方 evaluator](https://github.com/Job-Bench/job-bench-eval/tree/bbeae9de5d2f0f6f162f053e03b37069b5f404c8)，
revision `bbeae9de5d2f0f6f162f053e03b37069b5f404c8`；Judge 文件 SHA-256
`4e86a2e7f3e0790986332a3c72d96916211127396cb92f6501fce258d0a6856a`。
已下载并逐一核验 750 个必要输入/Rubric 文件，共 278,908,469 字节；LFS 使用 SHA-256，
普通 Git 对象使用 blob SHA-1。答案和 grader-side search materials 没有放进 Agent 工作区。

ClawGym 上游 README 写 156 code / 44 hybrid，但冻结 JSONL 实际是 154 code / 46 hybrid；
200 行都有 hook_code，46 行有非空 rules。分类遵循逐题数据，没有为匹配 README 改题。
ALFWorld 六类分布为 18/24/31/21/23/17；历史 10 题均为 look_at_obj_in_light，不能覆盖六类。

来源、release ZIP 的 hash、ALFWorld 134 个游戏对应关系、TB 不可变 TaskConfig、JobBench
完整 tree 均在 [source-pins](../../artifacts/benchmark-readiness/source-pins)。没有以历史十题推断官方总量。

## 此前是否仅接入十题

此前正式真实执行确实是每基准固定十题，但不能把“运行十题”等同于“Adapter 只能支持十题”。
主分支的 ALFWorld 生成器已能枚举全部 134；JobBench Adapter 已支持 main/easy 全部目录；
TB 原生 Registry 已能选择全部 89，当时本地缓存只有部分题目。ClawGym 标准 Adapter
在最新已合并 main 中缺失，本轮从已有本地 Harbor 实现审计恢复，没有复制 OpenHarness 代码或旧 recovery runner。

本轮统一生成到 `/home/cky/.cache/harbor-rsi/full-benchmark-integration`，为可重建的持久数据根，
不是历史某次 Trial 的私有目录。大型官方资产不进入 Git；生成代码、source pins 和逐题 hash 进入 Git。
另一个独立输出目录重新生成后，551 个 Task 的 Packager hash 全部相同，且没有重复完整 Task ID。
JobBench main/easy 名称包含 Split，防止同职业/task 编号在两个 Split 中相互覆盖。

## 149 镜像与环境状态

正式 Remote Docker 仍为 CLI/OpenSSH，连接 `ssh://aibox-149`，经现有 SSH 配置连接；没有启用 SDK 原型。
已验证 daemon ID `c6e16cdf-e878-4cc5-84c8-78a56c54b5c5`，Engine 29.8.2，linux/amd64，
40 CPU、约 270 GB RAM，Docker 根 `/var/lib/docker`，约 5.42 TB 可用磁盘。

初始只查 Task 镜像时为 36 cached / 53 missing；后续独立全引用复核为 37 / 52。
`alexgshaw/headless-terminal:20251031` 状态发生变化，不能推断是谁准备了这个共享缓存。
其余查询带精确引用、Image ID、RepoDigest、平台和大小。100 个镜像引用包含预构建镜像、
Dockerfile FROM、潜在构建输入和用户指定的旧 hf Tag；未用 latest 或替代镜像。

初始查询时 `alexgshaw/hf-model-inference:20251031` 和当前任务的 `:20260430` 均缺失。
当前选定 :20260430 已以官方manifest离线导入并验证，旧:20251031未准备、也未被选用。
当前 Task/Dockerfile 是官方冻结版本，本轮没有把旧 Tag 改为新 Tag；两者分开登记。
旧 Tag manifest 压缩层约 6.19 GB；当前 linux/amd64 manifest
`sha256:a88d98a849e81bf42754973d1ed58f5971eb76315bf94d2b19cabedd7d7af9c7`，压缩层 328,580,704 字节。
对当前 Tag 的一次有界原生 docker pull 在 120 秒后退出 124，有小层下载成功，但没有完整镜像。
历史上是否曾 pull、缓存是否被清除，现有证据不足；当前缺失不等于从未拉取。

149 的 Registry 只读请求出现网络不可达；现有镜像站 /v2/ 返回 403。
控制节点能够查 manifest，但随后匿名拉取命中 Docker Hub rate limit；既有 1panel mirror
对控制节点回复 “only support mainland China”。当前没有可用的 Docker Registry 登录凭据。
未改 DNS、daemon proxy/mirror、监听、Tag、共享容器，也未 prune。

早期缺失 52 个 TB 镜像中，43 个当时已取得 linux/amd64 manifest 和压缩层清单；已知部分按
层 digest 去重约 9.72 GB，另 9 个 manifest 状态未完整确认。这个数字不包括解压后占用，
也没有把已有共享层扣除，不能当作完整增量磁盘预算。
准确逐镜像准备计划在 [resource-preparation-plan.json](../../artifacts/benchmark-readiness/resource-preparation-plan.json)。

JobBench 全部 128 题输入已经准备，Python 基础镜像已缓存；初始两题只验证了构建与空提交路径。当前全量无模型队列已扩展到实际非空fixture/逐条Judge，动态覆盖以开头快照和逐题CSV为准，尚未完成项不记READY。TB 89 个冻结 Task 未发现任务自带
多服务 Compose 定义；Provider 的多服务契约由已有单元回归覆盖，不能声称本轮真实多服务采样通过。

ALFWorld/ClawGym 使用 E2B，未要求把它们的模板拉到 149。
初始检查时134个ALFWorld模板仅匹配一题缓存；当时ClawGym Agent 模板曾有200个，
恢复 Adapter 后完整性证据变更改变 Verifier template hash，当时匹配两题的Agent+Verifier模板；后续ALF134和Claw200均已完成实际原生验收与归档。
账号模板可列举不代表全量创建配额、并发额度或后续网络已经确认。

## 两项通用/Adapter 缺陷及证据

1. E2B 可选 Resumable Provider 的 `_safe_io` 持有 `_handoff_lock` 后调用官方递归
   `download_dir`；官方方法再次调用 `self.download_dir/download_file`，同一 asyncio Task
   重新获取非重入锁，导致 Artifact 回收死锁。真实新 ClawGym Trial 卡住，取消 traceback
   定位此路径；Fake SDK 在 `/workspace` 和 `/logs/verifier` 两种目录均复现失败。
   `c290e3db` 只让持锁的同一个 Task 复用已有保护；其他 Task 仍串行，owner 在 finally 清除。
   不改变 Job、Trial、Verifier、Deadline、取消语义；继续调用官方递归 I/O。
   6 项新测试加 9 项既有测试通过，修复后同一新题的原生 Trial 56 秒完成。
2. ClawGym 标准 Adapter 保留 hook_code，使非零 checker 退出仍输出数值时，原生 reward
   继续保留，而 score_completeness 不被错误记为 complete。另从 checker AST import
   声明 Verifier 独立依赖：官方 YAML checker 需要 PyYAML==6.0.3，Agent 镜像未增加该库。
   checker 源码与官方原文一致；离线 YAML 读取缺依赖前返回 None，安装后读取正确；
   真实 E2B Task 131 的代码评分和 Artifact 已完成。

这不是按 Task ID/Benchmark 写框架特殊分支；来源是可复现的 Provider 锁契约和 Adapter
依赖完整性。Remote Docker Transport、OpenHarness2、Harbor Job/Trial 未修改。

## 无模型原生证据与零分审查

| 新 Task | 原生 Reward / RC | 验收 |
|---|---|---|
| ALFWorld pick_and_place_simple-mug-none-desk-308-2af7b53d | 0 / 0 | 真实 episode started、steps=0、官方 success verifier、回收和清理 |
| ClawGym 11 | 取消后另存修复运行，0 / 0 | 原始 Artifact 死锁记录保留；修复运行 code checker complete |
| ClawGym 131 | 0 / 0 | YAML checker 11 项指标确实产生，RC=0，complete |
| TB build-cython-ext | 0 / 0 | pytest 11 项，1 pass / 10 fail，0 skip |
| TB build-pmars | 0 / 0 | pytest 4 项实际执行；真实固定 OpenHarness wheel 安装、CLI entry/version 检查，无模型调用 |
| TB nginx-request-logging | 0 / 0 | pytest 8 项实际执行，0 skip |
| TB polyglot-c-py、query-optimize | 0 / 0 | **失败**：uv 下载失败、uvx 不存在、无 CTRF，pytest 未执行 |
| JobBench main biostatisticians/task2 | 0 / 0 | 合法 empty_output，7 rubrics；Judge 未调用，仅部分验收 |
| JobBench easy biostatisticians/task1 | 0 / 0 | 合法 empty_output，9 rubrics；Judge 未调用，仅部分验收 |

两个 TB 官方 test.sh 没有依赖失败 fail-fast，最后写 0 并成功退出。本轮保留原生结果，
在 readiness 中标 dependency_failure，没有改断言、reward 公式或 Result。下一步须在合法
Verifier 准备路径补齐官方 uv/pytest 依赖，并重新证明真实测试执行。

所有 11 次 native checksum 均与当前实际 Task 的 dirhash 一致；另保留 Packager hash，
不混淆两种算法。独立只读确认所有本轮 E2B sandbox 已 NotFound；按每个本轮 Compose
project label 检查容器/网络/volume 均不存在，并检查私有 workspace 已删除。
没有对其他用户资源做全局清理。证据含 Native Result SHA、阶段时间、Verifier proof、Artifact 文件 SHA。

## 原生入口、复现与继续执行

生成命令（先按 source pins 准备官方数据）：

```bash
python -m benchmarks.readiness.fetch_jobbench \
  --tree artifacts/benchmark-readiness/source-pins/jobbench-tree.json \
  --output /path/to/sources/jobbench
python -m benchmarks.readiness.generate \
  --alfworld-python /path/to/alfworld-0.4.2-venv/bin/python \
  --alfworld-data /path/to/official/alfworld/data \
  --clawgym-data /path/to/official/benchmark_data.jsonl \
  --jobbench-source /path/to/sources/jobbench \
  --jobbench-tree artifacts/benchmark-readiness/source-pins/jobbench-tree.json \
  --tb-manifest artifacts/benchmark-readiness/source-pins/tb21-tasks.json \
  --output /path/to/new-empty/full-dataset
python -m benchmarks.readiness.audit \
  --task-root /path/to/new-empty/full-dataset \
  --output /path/to/readiness-report
```

使用原生 DatasetConfig，无 n_tasks 十题限制；JobBench main/easy 两个完整配置。
原生 `Job._resolve_task_configs` 已验证 134/200/89/65/63 个 Task，每个数据集也成功选择
任意单题。完整配置在 full-job-configs，原生 `harbor run -y --config CONFIG`；恢复使用
官方 Job resume。无新 Task cache、Runner、Campaign 或隐藏 retry。

TB 源准备曾遇到一次 HTTP/2 连接关闭；重新用原生 TaskClient、每批 8 个固定 ref 成功导出。
这只约束资源准备请求量，不重新实现 TaskClient 缓存或修改 Job 并发。

冻结脚本需支持标准 datasets 和非十题清单。本轮沿用现有 release attestation，核验 wheel、
RECORD、实际导入文件、Git revision、全部 Task 文件及配置；计划将并发限制固定在 release
manifest，旧四基准十题清单仍可读取。它仍直接进入官方 CLI，不成为第二套调度器。

历史 40 个评分、42 次尝试、两次 QEMU 原始失败和两版 wheel 身份未修改。
此前固定随机种子的新增 40 题 proposal 是旧准备阶段记录，不是 551 题正式执行结果；
后续授权已扩大为冻结的全部 551 题。正式运行状态另存 `artifacts/benchmark-reports/full-551/`。

## 架构与未完成门槛

四项原则保持：Sandbox 以可选 Provider 解耦；任务差异放 Adapter/Task/Verifier 环境；
原生 TaskClient → Job → Trial → Environment → InstalledAgent → Verifier → Result 保留；
Harbor 编排、OpenHarness Agent loop、Provider 环境职责未混合。

**全量接入已完成，全量环境验收和正式评测尚未完成。** 下一步是解决 Registry/离线镜像路径、
独立 Verifier 依赖、全量 Agent 安装及动态验证、混合 Judge/JobBench Judge 真实调用、
固定 wheel 与 runtime attestation，再派发正式任务。全局最多 4 Trial，计划各 Provider 最多 2。
仅静态通过或缓存存在的 Task 不会直接改为 READY。

## 全量环境准备后续进度

用户随后明确授权 551 题正式 Agent/Judge，且不以费用等待审批；正式执行仍须完整环境 Gate。
阶段更新见 [环境验收进度](benchmark-environment-readiness.md)。固定 4f939654 wheel 已正常隔离安装，
五个完整 Job 的 Runtime Attestation 均通过，ALF 全134题原生无模型安装/评分 Job 正在运行。
TB 现为38个官方预构建镜像缓存、51个缺失；hf :20260430已完成官方digest/RootFS/平台验证的离线导入，
:20251031没有替换进来。共享daemon及网络配置未变，Hugging Face出网仍阻塞。
polyglot-c-py的prepared评分环境实际运行1项pytest（固定无模型提交1fail、0skip、合法0、RC0），
官方脚本和Agent镜像保持原字节，新preparedTask hash独立记录，正式配置尚待统一冻结。
原始下载失败零分、错误缓存位置导致的安全回收拒绝和取消尝试全部保留，不能算正常模型零分。
本次新增准备/证据保留回归39 passed；Ruff/Format和配置ty、逐个修改源码ty通过。
PR #11 在4f939654的Linux/Windows/Build/Ruff/ty实际CI成功，新提交仍需自己的CI验证。

## 最新实际验收快照：2026-10-13T20:06:42.555950+00:00

551/551 标准 Task 生成、原生加载与静态检查保持通过。ALFWorld 全 134 题已实际完成
安装、无模型执行、原生评分和独立清理；完整私有归档已保存。ClawGym 当前完成
62/200，原生异常 0；57 个已完成 Trial 的独立清理已确认。登记表只把拥有完整
评分与清理证据的任务计为动态通过，不以正在运行或合法零分替代证据。

TB 镜像只读快照为 63/89 已缓存、26 缺失，单路有界官方离线导入继续运行。
89 个 Verifier 准备副本均由 TaskClient 解析；79 个有已校验依赖准备，10 个保留原始依赖
并明确未解决。全部官方测试文件、超时、环境 Dockerfile 和 Agent 初始状态不变。
准备副本有独立 hash；它们不自动意味着原始未准备 Task 已动态通过。

JobBench main 原队列在 17 次结果后暂停：12 次无异常、4 次基础设施检查超时、1 次明确
人工取消。17 次资源均已独立确认无残留。4 次超时均在 Docker exec 工作目录检查阶段；
其中一次实际约 41.3 秒的评分派发前检查被记录为 Verifier 3900 秒超时。
40c1179d 仅在独立 Provider 把内部检查 TimeoutError 转为带原始 cause 的 RemoteDockerError，
不改原生 Deadline、不派发未检查命令、不自动重试，也不宣称解决底层连接迟滞。
修复前 3 项回归失败，修复后相关 67 项通过；24 次自有容器只读检查未复现 30 秒迟滞。
已开始单题显式恢复 Gate 和 8 题 TB 准备副本 Gate，使用独立正常安装 r2 wheel；
原始失败结果全部保留。当前 Remote Trial 上限 2、Claw Trial 上限 1，正式 Agent 仍为 0。

40c1179d 的真实 GitHub Ruff、Type Check、Linux Tests、Windows Tests、Package Build 全通过；
[runs](https://github.com/CoyeCHEN/harbor-rsi/actions/runs/38456162923)。
本次新增证据映射回归 45 passed，全仓 Ruff/Format、配置 ty 和修改源码显式 ty 通过。
源码映射工具仅汇总证据，既不调度也不评分；原始/准备副本 hash 必须明确对应。

### 受控恢复和镜像传输结果更新：2026-10-13T20:12:09.927008+00:00

单题 civil_engineers/task2 的 r2 恢复尝试仍失败：Agent 安装已完成，通用固定提交的
派发前 workdir 检查达到 20 秒，保留 RemoteDockerError 原始 cause；Verifier 没有启动。
生命周期 release 的次要错误也保留。该任务的容器/网络/卷/workspace 已独立确认不存在；
不会将 cleanup 成功或准确错误分类写成任务已恢复。JobBench main 队列继续暂停，
未启动 easy63 或正式模型派发。底层迟滞由生产 transport 的自有只读容器探针继续诊断。

镜像批次完成 18 项校验导入后，path-tracing-reverse 的文件传输只收到 91,702,000 字节，
归档大小/SHA 检查拒绝导入；失败和私有残缺文件保留，准备沙箱关闭记录保留。
另建有界恢复批次只处理剩余 25 引用，不重复导入已验证 18 项；唯一官方 manifest 不变。
新归档 170,995,200 字节首个下载尝试已完整校验，后续仍须远端 SHA 与 image inspect。
只读下载最多 3 次，每次新文件并核验源身份，不重放不确定状态的 Docker 操作。

### 文档、图像 Judge 与准备版本核验：2026-10-13T20:38:04.456932+00:00

JobBench main/easy 全 128 题使用相同的 Dockerfile recipe SHA
`da5aac123814f85fd6c18abd16392a6612df41a39f2ea57d6a0060620eff4a2b` 与官方 Judge SHA
`4e86a2e7f3e0790986332a3c72d96916211127396cb92f6501fce258d0a6856a`。
官方 `rubric_needs_vision` 对全量 rubric 实际扫描，有 19 题可能请求图像，不能用纯文本
fixed fixture 宣称图像路径已验证。已有自有 JobBench 构建镜像中，独立组件 Smoke 真正读取
XLSX、DOCX、PDF、SQLite 的合法无答案工件，均无依赖错误；未改变 Task 或评分代码。
官方 Judge 原函数实际发送 1 张通用 PNG 到既定 deepseek-flash，vision_used=true、
api_exit_code=0、direct_json，994 input + 506 output = 1,500 tokens，清理独立确认。
这是共享组件/模型能力证据，不是新 native Task 通过数或正式成绩。
[DeepSeek 官方 Vision 文档](https://api-docs.deepseek.com/guides/vision/)和实际只读 models 响应
均表明当前 deepseek-flash 支持 text/image；模型 ID、Agent thinking/max_tokens 不变。
首次组件断言把 DOCX 正常 Markdown 转义 `task\-specific answer\.` 当成标记缺失；
失败留档、未请求 Judge、资源已清理。后续仅修正诊断用无答案标记，不改官方解析器。

Claw 全 200 官方 Checker 的全部 AST import（含函数内部）已扫描，唯一非标准库为
第 131 题 yaml；该独立 Verifier 已声明 PyYAML 6.0.3。仍以实际全量执行及 cleanup 为准。

89 个 prepared TB Task 与其他四份原始数据合为新的完整 551 Task 冻结清单，仍是五个
原生 Dataset Job；prepared TB 配置 Runtime Attestation 实际通过。原始 manifest 和旧 wheel
均保留，不把副本 hash 伪装成原始 hash；prepared 不等于所有依赖已动态通过，正式模型仍未启动。

生产 transport 的真实探针捕获 1 次普通检查超时，另 6 次 debug 检查均达到 20 秒且
Docker CLI 当时仍活着；同期直接 SSH 只读 exec-ID 查询也达到 6 秒诊断上限。
稍后的 4 次同机查询成功，删除/保留本地代理变量两组各 2 次都成功，无法归因为代理。
全部只操作独立自有容器，清理已确认；不据此切换 Transport 或声称问题已修好。

### 原生环境验收与必需网络门槛：2026-10-13T21:02:32.864743+00:00

全 551 Task 仍为已登记/静态通过，正式 Agent 请求为 0。Claw 全量原生 Job 当前已完成
104/200，无原生异常；本次已独立确认 98 个 Trial 的 E2B 资源不存在，后续完成项继续检查。
原生无模型 Gate 与正式真实模型成绩分开保存。ALF134 的完整归档保留。

TB 当前只读镜像快照 69/89，20 个缺失；固定官方摘要的单路导入继续执行。
TB prepared 小批次因连续两次 AgentSetupTimeoutError 暂停：3 个实际 Verifier 完成
（sqlite 1、sparql 3、large-scale-text-editing 5 个测试，均为合法无答案失败，0 skipped），
2 个安装耗尽原生 360 秒，1 个明确人工取消；六个 Trial 的容器/网络/卷/workspace
全部独立确认清理，并保存 partial-readiness 私有完整归档及 SHA。剩余 2 题未派发。
失败原始结果未修改，取消不冒充测试失败；未改变安装/Agent/Verifier Deadline。

Hugging Face 必需出网仍 BLOCKED：当前 DNS 地址连接超时；临时使用 HTTPS DoH
解析的两个官方域名地址，TCP 可建立但 TLS 被重置。该检查只请求公开 model metadata，
没有下载模型、注入答案、修改 DNS/daemon 或使用替代模型。HF 的 native Verifier
路径虽实际执行过 4 个测试，不能替代题目要求的 Agent 模型下载能力；登记表已将
level2/readiness_status 明确标为 BLOCKED，level3 的真实执行证据保留。

只读生产 transport 对照中，149 端关闭复用 4/4 与现有复用 4/4 均达到 20 秒；
进一步对两跳显式关闭复用和现状各做 1 次，仍均超时，全部诊断资源独立确认清理。
因此没有证据把故障归为 ControlMaster，不能以重建 SSH 或更换 SDK 宣称已修复。
149 同期负载约 0.2/40 CPU，不支持“CPU 饱和”结论。当前 Remote Job 继续 HOLD。

提交 c7a1ac7c 的真实 GitHub Ruff、Type Check、Linux、Windows、Package Build 全通过，
[Python Tests](https://github.com/CoyeCHEN/harbor-rsi/actions/runs/38461256478)。
最新 main 实际 API 查询仍为 098be17d22deea658131570366bd8ee93621b88a。
以上新增内容仅诊断、资源准备和证据更新，无 Harbor core、OpenHarness 或生产 Transport 改动。

### 显式索引 Verifier 准备与连接对照：2026-10-13T21:21:28.933177+00:00

任务准备工具现在严格解析字面 HTTPS `--index` 与 uv 支持的 `--index-strategy`，
拒绝动态/含凭据/非 HTTPS 索引，保留官方 test.sh 原字节和全部 resolver 参数。
显式索引必须明确允许包网络解析；当前仅 requirements 的缓存清单不能证明 CPU/GPU
wheel 来源，不会通过 UV_NO_INDEX=true 静默绕过原索引。
依据 [uv 官方索引文档](https://docs.astral.sh/uv/concepts/indexes/#searching-across-multiple-indexes)。
修复前真实复现官方字面 CPU 索引配方被拒绝；新回归 1 failed/5 passed，修复后相关
46 passed，修改源码显式 ty、全仓配置 ty 与 Ruff 通过。没有修改 Harbor core 或 runtime。

实际生成并解析 pytorch-model-cli 的独立标准准备副本，原 instruction/Dockerfile/测试
及资源/时间字段全部校验不变，仅 Verifier env/cache。独立完整 89 题 prepared-indexed
目录已由正常安装 wheel 的 Task 与原生 Dataset 解析；完整 551 Task/5 Job 候选配置
再冻结，Runtime Attestation check-only 实际通过，未创建 Trial。该视图有 79 个既有准备
加 1 个新增索引准备，9 个仍保留原始未解决依赖。新增项仍为动态 UNTESTED，
CPU index HEAD200 不证明 wheel 安装/apt/Verifier 已成功；MobileSAM 固定 commit 的
GitHub Raw 12 秒只读请求超时，不能宣称其依赖已就绪。旧 manifest、目录、工件不覆盖。

私有诊断中复制 149 的 CLI29.8.2（校验 SHA）与本地 CLI29.1.3 各作 2 次同容器只读
exec，4/4 达到 20 秒，全部资源清理独立确认；生产 CLI 未替换。因此升级 CLI 也不是
已证实的修复。另一个自有 tmpfs 唯一标记探针：本地生产 API 路径 20 秒超时，后续
直接远端读取确认该次标记不存在；远端 CLI 对照约 10.78 秒完成且唯一标记可读。
标记内部两个时间字段不用于推算整个命令耗时。两个命令都只派发一次，未重放
不确定状态的操作；诊断容器清理已确认。
该证据支持存在命令派发/响应迟滞，尚不确定具体原因；不据此修改生产 Transport。

### Verifier 执行证据与传输竞争复现：2026-10-13T22:06:00.996719+00:00

Claw 全量原生验收当前完成 154/200，原生异常 0，152 个已完成 Trial 的沙箱已独立
确认不存在；其余继续检查。正式 Actor 调用仍为 0。当前带时间镜像快照 74/89，
缺失 15 个；r4 使用每个镜像独立的获取沙箱，源归档大小/SHA 验证后关闭并
独立确认，再传输/校验/导入，避免让源沙箱承担长时间 SSH 传输存活要求。r3 原始
chess-best-move 导入成功后的源清理 NotFound 失败保留；实际 daemon inspect 与旧获取
沙箱的独立 404 检查另存，不能将失败改写成原始成功。

Readiness 汇总发现可离线复现的漏洞：CTRF tests>0、但全部 skipped/pending，也曾被
判为已执行。修复前 2 failed/3 passed，最小修复后相关 51 passed；现在要求 passed+failed>0，
仍保留真实断言失败的合法零分。既有 6 份实际 CTRF 全有 pass/fail，没有全部跳过，原生
结果/Reward/测试原字节未改。全仓 Ruff/Format、配置 ty 和修改源码显式 ty 通过。

新的自有诊断把迟滞定位到 Docker CLI 初始化 Ping 与关闭 SSH 子进程等待，尚未执行
容器命令。仅暂时 SIGSTOP 自有 rsync 生产者 12 秒排空后做同一个只读 daemon 查询：
传输中达到 10 秒上限 → 暂停期间 0.313 秒成功、正确 daemon ID → 恢复传输后再次
达到 10 秒。rsync 已在 finally 中恢复，SSH master/共享配置未改。这提供了大归档传输
与控制请求竞争的直接受控证据；不能声称所有历史迟滞都已归因或底层已修复。
后续原生 Remote 恢复应先与镜像批量传输分开执行，再验证安装/Verifier/cleanup；
不增加原生预算、不切换 Transport，也不重复不确定状态的命令。

cf5487df 的真实 GitHub Ruff、Type Check、Linux、Windows、Package Build 已全部成功，
[Python Tests](https://github.com/CoyeCHEN/harbor-rsi/actions/runs/38470072144)。
上一版 0d556969 的 Python Tests 因更新分支被 concurrency 取消，不记为失败或成功。
本次报告工具修改仅影响 readiness 证据分类，正常安装 r2 wheel、OpenHarness、原生执行链
和生产 Provider 代码均不变。

149 到自有 E2B 签名文件 HTTPS 的独立通路探针实际下载 1,035,000 字节，HTTP200、SHA 完全一致，约 1.66 秒；私有远端文件与源沙箱均已确认清理。该结果仅证明小文件通路，不等于大型官方镜像准备完成。下一步独立完整镜像验证保持固定 manifest、全部 blob/归档校验和 daemon identity，不更改生产 Provider。签名 URL 不进入日志或工件。

### 直下载完整镜像与探针 fail-closed 修复：2026-10-13T22:32:49.053748+00:00

149 直接下载自有源沙箱的完整 `video-processing:20251031` 官方 OCI 归档
311,890,432 字节，约 22.69 秒；全部 blob、manifest/config、RootFS diff_ids、
平台和 daemon ID 校验及单次导入约 40.42 秒，源沙箱关闭/独立确认 404。
这是环境资产准备通路，不是新的 Provider Transport。未修改官方镜像或共享配置。
原 r4 单路最终 write-compressor 归档传输完成后单次校验/导入，原 preparing 记录
与另存恢复凭据都保留；没有重放未知状态的 load。新单路批次仅处理剩余 12 项，
冻结压缩层合计 7,503,779,950 字节，各项独立源沙箱/字节上限/磁盘余量检查。

传输移出 SSH 后 3 次只读 daemon 查询约 0.29–0.31 秒。但 civil 单题原生恢复
仍在安装期失败：Docker CLI exit1 包含 SSH dial-stdio exit255，Agent/Verifier
均未启动，Judge 请求 0，资源按真实 identity/project 标签和 workspace 独立确认
不存在。这个新失败留档，不记为普通模型零分，也不能声称 Remote Gate 已恢复。

该真实 CLI 响应证明 exit1 不能一律代表框架只读 `test -d` 的目录不存在。
离线最小复现中，6 个案例（/workspace、/app 各覆盖 SSH/OCI/异常输出）均错误
继续派发并改变 cwd。最小 Provider 修复拒绝带诊断的 exit1；只有正常 silent
false 才保留原来的缺目录行为。修复前 6 failed；修复后 Provider 38 passed，
原生 Job/Trial/InstalledAgent/Deadline/取消契约 49 passed、6 skipped，Ruff/Format
和全仓/修改源码 ty 通过。没有修改 core、评分、模型参数、正式 Transport 或重试。
这修复的是已证明的探针契约，未声称修复本次安装的 SSH 原因；运行中的旧 wheel
不改，后续正常安装工件将单独记录新版身份。

### 全部选定镜像缓存完成与原生恢复结果：2026-10-13T23:05:24.051413+00:00

实际 daemon `c6e16cdf-e878-4cc5-84c8-78a56c54b5c5` 的全 89 个选定镜像
当前 inspect 成功，缺失 0。85 项已对照官方 manifest/导入凭据，0 identity mismatch；
另外 4 项初始缓存只记录现有 ID/RepoDigest/平台，不冒称做过新的 Registry 内容对照。
最后 12 项归档累计 7,504,025,600 字节、导入镜像累计 29,517,113,819 字节，
全部源沙箱 kill 与独立 404 确认；没有改变共享 daemon、代理、DNS 或官方 Tag。
HF 当前 :20260430 已缓存，旧 :20251031 未准备且未被选用；HF Agent 必需出网仍阻塞。

正常安装 r3 Runtime 由 030d6ab8 构建，Source/wheel/module 身份清晰，全部 551 Task
及五份原生 Job 候选再次冻结，五项 Runtime Attestation check-only 实际通过。
旧 r1/r2 安装包不改。新控制器依赖检查发现冻结 OpenHarness wheel 声明的
partial-json-parser 缺失，离线补足 0.2.1.1.post7，106 包兼容、两仓 CLI --version
通过；未改 OpenHarness 源码、模型/上下文/工具策略或默认依赖。

增加本地 CLI 诊断日志的 civil Trial ehBbF4G 及恢复生产默认 CLI/SSH 的
civil Trial YVr5fpH 都完整执行，9 项真实 rubric、status=ok、judge_failures=0、
原生合法 0、RC=0、独立资源清理确认。它们是无模型恢复证据，不是正式成绩，
也不能证明所有迟滞根因已消除。早先 xRwtXwU 的安装 SSH255 和所有失败均保留。
首次日志包装器硬编码了本机不存在的 /usr/bin/docker，使诊断 Trial 82mZVSi
在环境连接前失败；错误归属为本地诊断配置，真实 CLI /home/cky/.local/bin/docker
恢复后另建 Trial，不抹掉原始记录、不归咎于任务。

JobBench main 已有 14 题完成原生 Gate；仅剩余 51 题作为一个标准 Native Dataset
选择冻结并启动，单并发、生产 CLI/SSH、正常安装 r3、固定无答案提交与原始 Judge
算法。没有重复已通过的逐题验收，也没有恢复时删除 CancelledError 历史。
正式 Actor 仍为 0，全量环境未通过；Claw 原生全量队列继续执行。

### ClawGym 全量无模型验收完成：2026-10-13T23:12:23.339142+00:00

200/200 原生 Trial 完成、原生异常 0、Verifier RC=0，全部200个 E2B 沙箱已独立确认不存在。代码154题/混合46题均完整覆盖，真实 hybrid Judge 证据随原生结果保存；固定fixture未发起 Actor 请求。整个Job、Verifier、Agent/Provider轨迹及独立清理凭据已私有归档，SHA-256 `9ebe6b3391045ee4ef160f4f27fccfb2cfaeeea98096bdef94ffa5e839152043`，大小1,222,247字节。该档是 readiness 证据，不计为正式200题成绩。

030d6ab8 的 GitHub Ruff、Type Check、Linux、Windows、Package Build 均实际success（`evidence/ci-030d6ab8.json`）。JobBench main剩余51与easy63按正常安装r3/生产默认CLI各单并发推进，总Remote Trial并发2、正式Actor0。easy启动首次因controller cwd未提供fixture模块路径而在创建Job前失败，另存启动日志后以正确cwd启动；没有修改 installed Harbor/Provider、没有source PYTHONPATH覆盖或重复原生Trial。

### 报告门槛修复：2026-10-13T23:14:58.457257+00:00

HF 的固定无模型 Verifier 路径曾通过，但任务必需的 Agent 模型下载仍被出网阻断。报告收集器原本仅按 level3 计为 dynamic，并可能在再次收集成功记录时覆盖 BLOCKED；离线复现1失败/19通过。最小修复保留独立 BLOCKED 前提，dynamic统计同时检查level2/level3与DYNAMIC_READY，另列 native_verifier_gate_passed。相关33个离线测试通过，Ruff/Format、全仓与修改源码ty、diff检查通过。此次仅修复 readiness 报告，没有改原生TrialResult、合法Reward、官方测试、生产wheel/Transport、OpenHarness或Harbor core。

最终4项初始缓存已通过独立官方Registry元数据查询，manifest/config SHA、RootFS和linux/amd64与149实际inspect全部一致，源沙箱独立404；现在全89选定镜像identity有据（`evidence/all89-tb-image-identity-verification.json`）。85+4的较早快照保留，不改写为当时已全部比较。该只读补验没有拉镜像、没有改daemon，也不替代逐题环境Gate。

本次汇总区分动态就绪与Verifier通过：alfworld:134/134, clawgym:200/200, tb21:6/89, jobbench-main:24/65, jobbench-easy:2/63。TB另有1题Verifier路径通过而必需出网仍BLOCKED，不能计作dynamic。JobBench计数随独立清理后的增量收集增长，尚在运行。

### 必需HF资源的额外逐题核查：2026-10-13T23:27:23.086153+00:00

`count-dataset-tokens` 明确要求访问官方HF数据集/README与Qwen tokenizer，`mteb-retrieve` 要求使用mteb加载固定revision的BAAI模型。三条精确原地址仅HEAD请求都在5秒连接上限失败。对两个官方镜像分别创建一个带自有identity的从未启动容器，仅检查小型默认cache元数据：镜像root用户且未设置其他HF缓存位置，指定模型/数据refs/config均不存在；两容器删除后独立确认absent，没有执行进程、下载模型、改镜像或接触其他用户资源。两Task的必要网络Gate标BLOCKED，不会因未来NOP Verifier成功而自动变READY。

`reshard-c4-data` 的hidden分片缓存尚未实际确认，保持UNPROVEN，不能据Agent初始已有另一分片认定Verifier输入就绪。82题剩余TB原生无模型候选已冻结选择，但尚未派发；当前两个Remote Trial位置用于JobBench，严格不增加第三路原生Trial。

### 现有可选E2B Provider对照：2026-10-13T23:39:55.691113+00:00

现有获授权E2B只读源沙箱对4个精确HF metadata地址HEAD均HTTP200，沙箱独立确认absent。同一个未改变的官方HF Task，通过标准environment配置使用现有ResumableE2BEnvironment、正常安装r3 wheel、冻结OpenHarness及InstallOnlyFixture，原生Trial fY5dxUr完整结束约64.75秒，安装22.71秒，实际CTRF4tests/4failed/0skip、合法0、Verifier RC0、原生异常0、独立清理确认。该无模型结果不构成正式评分，也不把149网络Gate自动解阻。试图在结束后补查该实际Task的HTTP只得到SandboxNotFound，记录留档，不据通用沙箱HEAD冒称实际Task网络已证实。

新增小型标准InstalledAgent测试fixture，仅在实际原生Task环境中对配置声明的HTTPS endpoints执行HEAD，不读响应body、不下载Agent模型或答案。缺少/失败响应不会判通过，URL禁止credentials/query/fragment/非HTTPS；沿用官方native工具timeout。相关42个离线测试、全仓Ruff/Format和ty、修改源码显式ty通过。现有正在运行的fixture未修改；这是readiness研究fixture，不是新的Runner或生产Agent策略。3a8efd7e的真实GitHub Ruff/ty/Linux/Windows/Package Build也已全部成功。下一步用该fixture证明实际Task网络能力，并分别保存Provider证据，当前149生产SSH、旧任务/评分/Actor参数都不变。

### 原生Task内网络对照通过、全量E2B能力验收继续：2026-10-13T23:48:49.411104+00:00

count-dataset-tokens/wStroBr和mteb-retrieve/ogFKqyr分别使用同一官方Task/source image/resource/timeouts，标准E2B Provider、正常安装r3和提交1b7c78f9的研究fixture；实际Task沙箱中两项必需HTTPS HEAD均200。原始官方Verifier实际运行（CTRF分别1和2项fail、0skip）、合法0、RC0、原生异常/infra列表空，两个沙箱独立404。未下载模型/数据到Agent初始环境，也未改原始Verifier或官方断言。此前HF/fY5dxUr的4项Verifier路径与清理也通过；它的补查HTTP曾因沙箱已结束而未执行，该限制仍保留。

基于现有Provider的四条架构原则，另启动标准Native DatasetConfig选择TB原始官方剩余86题，以E2B支持能力作可选后端全量无模型验收；这不是替换生产RemoteDocker Transport。89个Task均单服务、GPU0、CPU1-4/RAM2-8GiB、声明allow_internet=true；所有资源请求原样保留，未绕过额度或改配额。E2B单并发、JobBench main/easy两路Remote单并发，当前总Trial3（启动时最多4）。所有Provider逐题证据分开记录，未把E2B成功写成149网络恢复。完整Benchmark仍未正式评测，Actor0；只有整个选定Provider门槛通过后才能冻结正式配置。

## JobBench main 全量无模型门槛完成

2026-10-14T00:15:10.795863+00:00: main65/65标准Task均完成原生Environment、冻结OpenHarness CLI安装、固定非答案提交、真实替代Judge、合法评分、Artifact及独立资源清理。remaining-r3原生Job51/51正常结束、0异常；先前14题有效证据保留。完整私有归档 `jobbench-main-all65-readiness-with-preserved-history.tar.gz`，SHA-256 `d6ff84a7ec63e6adc020ea3be079df299f805d232f71c98941e3ca0960a2edf3`，1,271,229字节；覆盖74次原生准备尝试，含历史失败/取消及原始partial Job的null finished_at，不修改旧Result。见 [archive receipt](../../artifacts/benchmark-readiness/evidence/jobbench-main-all65-readiness-archive.json)。这是无模型验收，不是65个正式Agent成绩；正式Actor仍0。

2026-10-14T00:16:39.241407+00:00：HF新增实际Task沙箱内config/tokenizer/model.safetensors HEAD均200，未下载任何权重；原始Verifier4项实际测试、合法0、无原生异常、独立404。相关proof单独保存；旧controller断线后Sandbox404的未完成HEAD尝试也保留。TB可选E2B当前已独立确认33/89个唯一Task无模型Gate，完成尝试34次含HF两次不同验证，不重复计题。原始Remote BLOCKED不变。

2026-10-14T00:39:42.413514+00:00: 两项新问题据实保留。QEMU native Oracle的E2B创建先报default tag不存在，但只读tags API同时列出旧default build；原生force_build重建随后在E2B provisioning阶段因bullseye多个APT包404失败。尚未证明该E2B模板可用，不能提升全89 E2B正式配置。未创建client Trial sandbox，平台内部build VM清理由E2B管理，未独立确认。现有生产Remote Docker隔离Oracle已实际启动Alpine guest并看到kernel 6.6.4-1-lts，原始Verifier/清理待最终结果。两次原生失败不覆盖，也不作为合法零分。

CI d4d4632b实际Linux runtime失败1项dynamic/shared-allowlist：8796 non-runtime通过，runtime60通过/1失败/1跳过；Windows、Ruff、ty、构建通过。CI原生失败Trial无Harbor异常，Verifier因允许的www.iana.org请求Network is unreachable写0；同轮对应另一Trial写1。已下载诊断工件并保存SHA/具体失败证据，根因仍未定，不借此修改通用网络、移除测试或宣称最新CI全绿。下一次具体证据提交将在真实CI再次检查。

2026-10-14T00:57:50.992454+00:00: QEMU Remote原生Oracle已正常结束，guest确实启动；原始Verifier仍因缺少system curl而无法消费缓存file:// uv发行归档，CTRF未生成，RC0/Reward0不记Ready。已定位到通用Verifier准备工具，新增精确固定URI/原installer参数的本地SHA校验复制，其他curl请求照原样转交。修复前真实生成shim退出127（1 fail/1 pass），修复后相关52 tests通过、全仓Ruff/Format/ty和修改源码ty通过。官方test.sh、断言、资源、Agent初始状态、Deadline及Reward公式不改；现有准备副本不覆写。动态复验尚待新的独立副本。

JobBench easy首次完整63题原生Job已结束：62合法Verifier/Judge路径、1环境setup工作目录探针30s超时；63项资源独立清理，完整首次轨迹归档SHA `04adc6399b207a7840640743c06c59746437c376600d5bc64305601760fe2880`。单题恢复以新的原生Job执行、原失败/归档不变。该超时与QEMU约95.98MB verifier archive上传时间相交，只有相关性与此前受控传输竞争证据；本条具体故障根因尚未完全证实。恢复不与大型Remote归档上传重叠。


### TB Provider能力候选与限制

E2B官方SDK的单次`skip_cache=True`重新部署也在provisioning阶段遇到相同bullseye security包404。缓存元数据不是已证实的唯一根因，不再循环重建；正常force_build和本次无缓存构建失败都留档。最初一次脚本使用dict而非SDK SandboxQuery，在本地参数检查即失败，尚未派发云构建，也单独保存。未替换官方镜像或改变APT源；平台build VM清理不可由Trial metadata独立确认。

官方native Job当前使用一个EnvironmentConfig构造所有Trial，不能在单个Job内逐题换Provider。为保留框架边界，只新增未启动的声明式配置候选：TB88个原始Task使用现有E2B，QEMU1个独立Verifier准备副本使用生产Remote CLI/SSH；集合精确89、不重不漏，正常安装r3已解析配置。它们仍需全部逐题Gate与新的Runtime Attestation，**未运行正式Actor**。若该候选最终提升，会是五个官方数据集、六个物理原生Job；不能写成一个E2B Job已通过全89，也未新增混合Provider路由器、Task调度器或框架分支。原有完整89题单Provider配置均保留。

query-optimize的Verifier实际执行约711.56秒SQL测试，CTRF6项/2pass/4fail/0skip，原生异常空、合法0、RC0。Artifact manifest已成功保存，完成后只读沙箱探针得到404；不是已证实的Artifact死锁。对其余CTRF中的缺文件/模块/localhost服务错误逐项检查：对应无模型Agent未创建的任务要求产物、编译模块或服务，不把它们误记为Provider缺依赖。该审计不意味着任意有CTRF的任务都自动具备环境Gate；零测试、收集失败、Verifier下载失败仍不通过。


最新门槛更新：QEMU新缓存副本两条原生Trial已结束，安装fixture实际运行1项pytest且合法0，官方Oracle实际1项pytest通过/Reward1，无异常并独立确认资源全清。完整Provider失败/恢复轨迹私有归档SHA `f12d14e62633159c3125d3c8bc80954088683af6fdf076bd0caaa2403140644e`。这证明通用Verifier准备修复有效，不把Oracle Reward计成正式Actor成绩。

TB原始E2B队列后来在qemu-alpine-ssh/qemu-startup连续模板404后被观察器停止；protein-assembly实际ensurepip执行失败也保留，后一个configure-git-webserver在环境创建中被停止规则取消。四个失败/取消Task的identity metadata查询均无残留client Sandbox。73个成功Task结果保留，10个剩余不受阻任务另建标准原生Job继续，max_retries0。早期88/1 Provider候选在任何正式派发前已标SUPERSEDED，不是已批准/已执行计划；六Job候选冻结输入也单独保存且未启动。第二QEMU的生产Remote复验与protein隔离安装诊断进行中。

最新66491ff8的真实GitHub Ruff/ty/Linux/Windows/Package Build全部成功；此前d4失败不能因新轮通过而删除或声称原因已修好。


第二QEMU的E2B模板实际失败后，当前声明式Provider候选已调整为E2B87题/Remote2题；初稿88/1只在正式派发前冻结了候选输入，现保留为SUPERSEDED历史，未调用正式模型。当前所有候选仍待Gate和重新attest，不能混用初稿冻结文件。protein的两次独立环境诊断（包括完全相同TMPDIR和venv参数）均成功，随后单次有界原生安装/Verifier恢复正常，CTRF1项真实执行、合法0、资源独立404。初始ensurepip失败原因仍未知，不据此修改已经验证的安装适配层或宣称已修复特定源码Bug。


当前TB E2B87题均具备原始Task安装/实际Verifier/独立清理Gate，两个QEMU通过生产Remote separately验证。QEMU-startup已正常Oracle1；qemu-alpine-ssh的旧Oracle实际启动guest并成功安装/启动OpenSSH，但Verifier因sshpass缺失返回合法0/CTRF1fail，因此不能提升最后一题Gate。APT安装curl/sshpass事务的curl404使sshpass未安装，并不是空Agent未提交的产物缺失。

已按[Debian官方公钥说明](https://ftp-master.debian.org/keys.html)核验签名Release、Packages.xz SHA256、官方bullseye amd64 sshpass1.09-1+b1包SHA256和提取的18,440字节二进制；包仅12,988字节。WSL没有系统Debian keyring，公钥从官方HTTPS获取、核验公布fingerprints并放入独立cache keyring，未修改系统/user keyring；公告页403未冒称读取。新的Generic verifier cache仅允许已登记/哈希核验的平铺bin工具，不允许覆盖curl/uv/uvx，保持字节上限、regular-file/无symlink和可执行权限检查。修复前1fail/27pass，后相关73tests通过、Ruff/Format、全仓和修改源码ty通过；实际Verifier新副本复验待运行。官方test.sh、断言、Agent环境、官方资源、Deadline、Reward均不变；旧准备副本与所有原生0分/失败保留。
