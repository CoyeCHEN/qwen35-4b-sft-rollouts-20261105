# 551 个 Task 正式评测启动前汇报

## 停止状态

用户最新指令为“先别正式启动评测，启动评测前停止并做详细汇报”。正式评测未启动：正式 Actor 请求、正式 Trial 尝试和正式评分均为 **0**。551 行正式 Case 保留 `NOT_STARTED`。即使环境关卡全部通过，也不自动启动正式模型、Judge 或 Job。

之前“不需要考虑费用”的授权仍记录为预算背景，但不能覆盖这条更新的停止指令。准备阶段已经发生的 E2B/Judge 调用和历史原生执行仍如实保留。

## 全量接入及数据身份

| 数据集 | 官方冻结任务 | 标准 Task / TaskClient / 静态解析 | 选用 Provider | 原生无模型关卡 |
|---|---:|---:|---|---:|
| ALFWorld valid_unseen | 134 | 134 / 134 / 134 | E2B | 134 |
| ClawGym | 200 | 200 / 200 / 200 | E2B | 200 |
| Terminal-Bench 2.1 | 89 | 89 / 89 / 89 | E2B 87 + Remote Docker 2 | 89（87 E2B + 2 Remote） |
| JobBench main | 65 | 65 / 65 / 65 | Remote Docker CLI/SSH | 65 |
| JobBench easy | 63 | 63 / 63 / 63 | Remote Docker CLI/SSH | 63 |
| 合计 | **551** | **551 / 551 / 551** | 五个官方数据集，六个原生 Job | **551 / 551** |

ALFWorld 使用 `alfworld==0.4.2`、官方 `valid_unseen` 的 json 2.1.1 / tw-pddl 2.1.3，134 个游戏逐项核验。ClawGym 固定 `c8cbd1d0df033af24fc14064d40d6964ca8f611f`：实际逐题数据是 **154 code + 46 hybrid**，保留与 README 156/44 的差异。JobBench 固定数据 Revision `d43a66575635da0d3f6cb9a20976dc1a60f3ffc9`，Judge 固定 `bbeae9de5d2f0f6f162f053e03b37069b5f404c8`。TB 使用官方逐题不可变内容引用，89 题成员清单 SHA-256 为 `7f9af399b85f44adc031de363fc704ba6277b3f8e0dc5b370b3c4884727e3739`，不能伪装为统一仓库 Revision。

之前 4×10 证明样本执行能力，不能证明551环境就绪。ALF已有134题枚举能力、Job已有main/easy目录转换能力、TB官方Registry已有89题入口；历史执行各10题，不等于Adapter只能支持10题。本轮恢复main缺失的Claw标准Adapter，统一补全551题持久标准任务、资产、冻结登记和环境验证。见 [全量任务登记](../../artifacts/benchmark-readiness/full-task-manifest.csv) 和 [冻结来源](../../artifacts/benchmark-readiness/source-pins/sources.json)。

## 镜像、网络和任务环境

149 正式 daemon ID 固定为 `c6e16cdf-e878-4cc5-84c8-78a56c54b5c5`。89 个 TB 官方选用预构建镜像现已全部缓存，89 个内容身份逐项核验，包括本轮补齐的原缺53个。通过可访问 Registry 的授权控制端下载官方正确 OCI 内容，再使用私有 staging、有界并发、SHA-256 和内容校验传入149；没有改共享 dockerd、代理、镜像站、DNS、监听端口，也没有清理他人资源。

- 冻结任务实际引用 `alexgshaw/hf-model-inference:20260430`，**当前存在**。
- 历史关注的 `:20251031` **当前不存在**，不是本轮冻结任务所需 Tag；没有用旧 Tag 替换新 Tag。
- 149 Registry 403、HF egress 失败仍然存在。镜像离线准备解决缓存输入，不代表149网络恢复。
- `hf-model-inference`、`count-dataset-tokens`、`mteb-retrieve` 在 E2B 使用原始 Task 实际执行 Verifier，必要 HF HEAD 请求成功；未下载模型权重预置答案，不能据此保证大型权重下载吞吐。
- E2B 的两道 QEMU Task 遇到真实模板创建404 / bullseye APT404，已有一次有界 `skip_cache=True` 构建仍失败；不继续循环构建或更换官方镜像。选择已经验证的 Remote Docker 环境。

因此 TB 采用现有 Job 的 EnvironmentConfig 做**87/2 分区**，完整89分母不变，没有逐题 Provider Router，也没有第二套调度系统。Remote 两道 QEMU 使用不同父目录下的显式标准 `tasks` 配置，避免隐式复制和漏选。

见 [镜像清单](../../artifacts/benchmark-readiness/image-inventory.csv)、[选定 Provider 逐题关卡](../../artifacts/benchmark-readiness/selected-provider-readiness.csv)；原默认149检查结果保留，E2B成功没有覆盖149阻塞。

## 无模型验收的实际覆盖及限制

所有标记 READY 的任务均有真实原生 Trial、启动与安装证据、Verifier/Reward、Artifact、内容身份和独立 cleanup 证据。合法0分不单独作为关卡通过依据。

- ALFWorld134：真实游戏环境、交互和成功判定、安装/CLI及评分与清理；不是134题真实 Actor 解题。
- ClawGym200：154代码评分和46混合评分均执行，混合评分调用真实的既定替代 Judge，不能宣称与官方指定Judge完全等价；缺失 PyYAML 只在独立 Verifier 环境准备；没有修改官方 Checker。
- JobBench main65/easy63：使用合法固定提交触发真实逐项 Judge，补足 NOP 空输出路径不能证明完整 Judge 的缺口。所有128题都有完整 Judge 证据；固定提交的0分不是正式成绩。沿用既定 `deepseek-flash` 替代Judge，官方评估源码保持冻结，但它不是官方基准指定Judge的成绩口径。
- TB87 E2B：原始 Task 的真实测试执行和安装/CLI验证。NOP 没有 Agent 产物、未启动服务、未创建解题模块产生的失败，保留为正常测试失败；发现下载或 OS 工具缺失则拒绝升级 READY。
- `qemu-startup`：安装 fixture 与官方 Oracle 分开证明。Oracle 启动实际 Alpine VM，官方测试 **1 passed，Reward=1**；原安装fixture **1 failed，Reward=0**，代表没有 Agent 启动 VM 的正常零分路径。
- `qemu-alpine-ssh`：原 Oracle 已完成真实 VM 启动、Alpine网络获取 OpenSSH、SSH密钥/密码/服务配置，但 Verifier 缺 `sshpass`，因此不能把非空 CTRF 和0分当 READY。新的 Verifier-only 缓存复验已完成：安装fixture实际执行SSH并连接失败产生合法0分；官方Oracle的真实SSH测试 **1 passed、Reward=1、RC=0**，没有原生异常。两个Trial的identity/project/resources/workspace都由149独立查询确认已清理。

`query-optimize` 原生 Verifier 运行约711.56秒，实际6项测试（2通过4失败0跳过）；日志证明真实SQL校验，不把长耗时误判为文件回收死锁。`protein-assembly` 首次 Python3.13 venv/ensurepip 失败，两个隔离复现成功后原源码不变的有界原生恢复成功；其最初失败根因仍不确定，没有声称已修复 Agent 安装逻辑。

## 真实失败和恢复历史

- 老4×10保持40个合法结果、42次原生尝试、两次QEMU首次基础设施失败及恢复。不能改写为历史首次40/40无错误。
- 新 JobBench main 的原始失败和恢复保留，最终65题必要关卡完整。
- JobBench easy 首63次中62正常、1次workdir探测30秒超时且尚未Actor/Judge派发；该题独立有界恢复成功，原失败保留。
- TB E2B 原队列保留两次QEMU SandboxException、protein安装失败和控制器中断的 configure-git-webserver 创建取消。连续基础设施失败后已停止原队列；后者是停止产生的取消，不描述为自发Provider故障。10题补完、protein有界恢复、受控HF测试之后，87个选定任务通过。
- Remote 原QEMU的依赖失败、源码/工具缓存修复前后的独立Trial、原0分/1分分别保存。

重型文件上传与SSH控制超时的相关性单独记录；已有受控传输实验支持竞争风险，但 easy 某次30秒失败的唯一因果关系不能下定论。后续计划串行 Remote 重型任务与准备传输，不提高超时掩盖错误。

## 最小修复与架构

最近两项准备修复只在 `benchmarks/readiness/prepare_verifier_cache.py` 和对应单元测试：

1. 已验证本地 `file://` uv release 使用严格参数和哈希的复制，解决镜像没有系统curl时Verifier bootstrap失败；其他curl调用保持原样。
2. 可选 `bin/<safe-name>` 哈希登记的普通可执行文件，限定路径、大小、执行权限及无符号链接，拒绝覆盖 curl/uv/uvx。工具仅由Verifier bootstrap在Agent阶段之后解压。

`sshpass` 使用官方 Debian bullseye `1.09-1+b1 amd64`：签名InRelease→Packages SHA-256→12,988字节deb→18,440字节二进制全部校验。公开官方密钥固定指纹，仅创建隔离缓存keyring；没有安装到共享宿主、Agent初始环境或用户系统keyring。原 `test.sh`、断言、Agent环境和Reward公式保持不变。

既有 E2B 嵌套文件回收修复及跨Task互斥测试已进入冻结普通wheel。不修改 OpenHarness2；Remote SDK 原型没有混入生产；默认仍是SSH CLI。执行链保留 **TaskClient → Job → Trial → Environment → InstalledAgent → Verifier → Result**。本轮不再引入 Harbor core 特殊分支。

## 冻结配置与身份

- 最新 main：`098be17d22deea658131570366bd8ee93621b88a`，已重新fetch核验。
- 普通安装运行时 r3 源码：`030d6ab893215c13d4bbd9be26fb4d5ad1b8a4d3`；没有editable、source PYTHONPATH覆盖。
- Harbor wheel SHA-256：`7e55eb1b31b4944507583481a323150b3ad40421635706a71992c520d1d6f0e4`。
- Remote Provider wheel SHA-256：`2e86db1fbf47d2b375e6bb6623e17b68e298a2082956cc3048cb85711d8b9174`。
- OpenHarness0.1 wheel SHA-256：`09c874a34f985266548292ee17acc234f30cda4b850d0b492df2c55cd4656f1f`。
- 模型配置候选：`deepseek/deepseek-flash`、thinking high、max_tokens65536，沿用冻结设置；尚未正式请求。
- 新准备源码已提交 `e2195dd27ca350467e922b078840f4149448d04d`；原Task创建时实际是d1加未提交补丁，其时间和具体源码SHA保留，未伪装成后来Commit创建。
- 新候选551个Task / 6个原生Job / 5个数据集的六份 **check-only Runtime Attestation全部通过**。check-only不会创建Trial。旧88/1分区候选在派发前已废弃，未用于模型评测。
- 候选原生Job：ALF134、Claw200、TB E2B87、TB Remote2、Job main65、Job easy63。并发计划全局<=4、E2B<=2、Remote<=2；重型Remote实际1。计划串行原生Jobs，不增加Campaign调度器。官方Task资源、Agent/Verifier超时不变。

## 测试与 GitHub 状态

可选工具缓存最小离线复现修复前1失败/27通过，修复后相关组合73通过；最终单模块28通过。全仓Ruff/Format、配置全仓ty及修改源码显式ty通过。仅改准备和类型/测试范围，不修改已验证评分/超时行为。

`d1bb49e65d17c920f61c6330edc160390b613c85` 的真实GitHub四个工作流全部成功（Linux、Windows、Package Build、Ruff、ty和Labeler）。最新源码 `e2195dd2` 的GitHub检查因为账户付款/额度限制，**Runner未启动且没有执行steps**，不能称为代码失败，也不能宣称最新源码CI通过。精确Jobs和annotations见 [GitHub阻塞证据](../../artifacts/benchmark-readiness/evidence/ci-e2195dd2-billing-block.json)。管理员须处理仓库所有者 GitHub Billing；没有用关闭检查或重复触发掩盖。

以前 `d4d4632b` Linux runtime网络测试确实执行后失败，日志/Artifact留存，后续d1真实全通过；未宣称网络根因被修复。

工作分支 `codex/full-benchmark-integration`，Draft PR [#11](https://github.com/CoyeCHEN/harbor-rsi/pull/11)，不自动合并。

## 费用、轨迹和未完成项

准备 Judge 目前可核验的保守最低请求数 **1336**；此数不等于最终账单，不能遗漏未知重试。E2B和Judge实际账单无法从本地原生日志完整取得，记录null，不能写成免费。正式Actor/Judge请求为0，正式评测费用未发生。

ALF、Claw、Job main/easy完整验收轨迹已保存私有归档与哈希；TB87原始/失败/恢复92次原生结果已保存归档，SHA-256 `0b2ff48ecd794dde677d665fd5264097ad8a68e1a44b34967670a963b353b840`。QEMU Alpine原失败/恢复归档 SHA-256 `4e31c179e41be50bbf9135c4f9a6286792dc37484c1403b54e768f7173d32ee4`。原生trace留私有目录；公开仓库只提交脱敏报告、哈希和索引，不提交密钥、binary或模型数据。

最后QEMU复验、独立清理、完整失败/恢复轨迹保存及551关卡账本均已收尾。最新GitHub账单阻塞准确记录，需仓库所有者处理。**当前无模型控制器均已结束；历史被中断Job的原始finished_at=null保留，不启动正式评测**。全量接入和环境验收不能描述成551题已全评测；首次正式Infrastructure-Free Rate、成绩和模型完成率均尚无本轮数据。

已完成关卡指所选Provider上的必要环境/安装/真实评分/清理条件。它不保证真实Agent一定完成，也不保证未来云平台、网络和大文件传输永不失败。Claw/Job替代Judge口径、HF HEAD无法证明完整下载吞吐、E2B QEMU原阻塞及SSH竞争历史均保留，后续运行不能隐藏。
