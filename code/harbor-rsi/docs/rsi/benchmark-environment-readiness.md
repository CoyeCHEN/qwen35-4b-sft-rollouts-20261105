# 551 Task 环境验收进度

当前状态：**551/551所选Provider必要环境关卡通过，USER_HOLD_BEFORE_FORMAL**。用户要求启动前停止，正式Actor/Trial/评分0。当前无模型控制器均已退出；历史被中断Job的原始finished_at=null保留，完整轨迹已保存，详情见 [启动前报告](full-551-prelaunch-report.md)。

| Gate | 实际证据 | 限制/剩余 |
|---|---|---|
| A：Task/资产 | 551标准任务原生加载/静态/确定性Hash；TB89镜像官方内容身份全部核验 | 149 HF网络仍阻塞，选定E2B通过必要请求；不声称149网络已恢复 |
| B/C：启动/安装/真实Verifier/清理 | ALF134、Claw200、TB87 E2B+2 Remote、Job main65/easy63全部原生证据及独立清理 | 无模型fixture与Oracle不是正式Actor成绩；Claw/Job替代Judge；HF HEAD不保证完整下载吞吐 |
| D：冻结身份 | r3普通安装030d源码wheel、551任务/六个原生Jobs/六项check-only attestation通过；准备源码e219独立记录 | 最新GitHub Runner账单限制未启动；d1实际全通过，不能伪装最新通过 |
| 启动授权 | 费用背景授权保留，最新用户明确要求停止 | 不启动任何正式Job/Actor/Judge |

历史原生失败、取消与恢复均保留，原40成绩/42尝试不可覆盖。当前完整账本见 `task-readiness.csv` 与 `evidence/selected-provider-all551-gates.json`，默认149旧计划独立留存。下文历史快照不代表最终就绪状态。

## 当前 hf 镜像的离线准备

当前任务使用 alexgshaw/hf-model-inference:20260430。该镜像现在已在指定 daemon
c6e16cdf-e878-4cc5-84c8-78a56c54b5c5 实际导入并 inspect 验证。
官方 linux/amd64 manifest 为 sha256:a88d98a849e81bf42754973d1ed58f5971eb76315bf94d2b19cabedd7d7af9c7；
config 为 sha256:43a3ff616ca45a6b1693e4cd436c14c6449367e090f4a50f379c9da89cd5062f。
归档 328,597,504 字节，原始 SHA、8 个 blob、全部 RootFS diff ID、配置与平台已校验。
149 containerd 存储的实际 Image ID 是 manifest digest，不能假定 Image ID 总是 config digest。
旧 :20251031 仍缺失；没有替换 Task Tag，也没有预下载题目要求 Agent 获取的模型。

WSL 首次直接拉取遇匿名 rate limit；已有授权 E2B 准备沙箱可访问官方 Registry，使用
skopeo --preserve-digests 获取官方 OCI 归档。该私有沙箱已关闭。首次 scp 断开，残缺归档
被 SHA 校验阻止导入；有界 rsync --append-verify 续传后源/目标 SHA 一致。
短 OCI ref 导入时 CLI 显示成功但 Docker 正常查询找不到；仅规范化归档 index 的完整名称
io.containerd.image.name=docker.io/alexgshaw/hf-model-inference:20260430 后实际可见。
manifest/config/layer blob 不变，归档变换 SHA 与全部尝试保留在 hf-offline-import.json。
containerd 对 OCI 名称不自动规范化的依据：[官方 importer 源码](https://github.com/containerd/containerd/blob/main/core/images/archive/importer.go)。
未修改共享 daemon、DNS、代理、镜像站或监听端口；没有 prune、删除他人资源。

## Verifier 依赖修复

89 题完整审计中 82 题引用 uv 0.9.5 安装器。准备工具只生成独立 Task 副本；官方 test.sh、
断言、测试数据和 reward 公式保持字节相同，环境 Dockerfile/Agent 初始状态保持相同。
额外依赖随 tests 在 Agent 结束后上传，使用官方 uv 发行归档、版本相符的 managed Python
及有 SHA 的 wheel。默认严格离线；只有显式 --allow-network-packages 时才允许官方固定
额外包从原 PyPI 解析，未动态验证者不能记为 READY。
uv 的镜像/缓存配置依据：[官方环境变量文档](https://docs.astral.sh/uv/reference/environment/)。

首次准备误把 UV_CACHE_DIR 放进 /logs/verifier，产生绝对符号链接，Provider 正确拒绝回收；
DownloadVerifierDirError 原始 Trial 保留，后续旧配置队列已取消且 cleanup 已确认。
修复只把 uv 临时缓存放进 /tmp/harbor-verifier-dependencies/cache 并压缩测试依赖，
不放宽安全提取、不改 core 或评分处理。polyglot 修正配置的真实 CTRF 证明 pytest 已运行，
不能将旧下载失败的 0 当作本次通过，也不能把 prepared Task 的新 hash 伪装成旧官方 Task hash。

## 出网与运行门槛

149 只读探测：DeepSeek HTTP 401（证明传输可达，未携带密钥）、GitHub/PyPI 200、
astral.sh 403、Hugging Face Network is unreachable。142 跳板只读查询也不能访问 Registry/HF。
因此镜像导入成功并不证明 hf 任务所需下载网络就绪；需要现有获准代理或可用出网路径。
其他数据集的安装、Judge 与动态准备继续推进；资金授权不能代替实际网络 Gate。

生产 Remote Docker 保持 SSH CLI；研究 SDK 不参与。原正式 40 题、42 次尝试、两次 QEMU
初始失败与恢复结果不改。完成每个正式 Benchmark 后，分别保存私有原生 JSONL/ATIF、
工具/生命周期日志、Verifier、Artifact、Result 和来源 SHA，再生成脱敏统计。
本文件是进度记录，不宣称全量正式评测已完成。

## 后续实际 Gate 结果（持续运行）

ALFWorld 原生 Job full-readiness-alfworld-installed-wheel-all134 的 134/134 Trial 已结束，
无 exception/infrastructure_errors，Verifier RC=0、合法零分；这是无模型安装/环境验收，
不是新的真实 Agent 成绩。Sandbox.get_info 对每个自有 ID 返回 SandboxNotFoundException。
私有完整归档为 trajectory-archives/readiness/alfworld-all134-installed-wheel-no-model.tar.gz，
SHA-256 b4a0435505d4ee5028614f5033fdd6b6a0a33f37bda97adeb8c3b0f1884c7330。

ClawGym 受控混合评分实际调用 deepseek-flash Judge，完整响应的 usage 为
1,233 prompt + 733 completion = 1,966 tokens；完整 code/rubric 评分返回合法 0。
JobBench 受控非空提交仅为通用 readiness.txt，不含任务答案；官方 Judge 实际完成
7 条 rubric，status=ok、judge_failures=0、合法 0。两者的所有自有资源清理已独立确认。
受控 Judge 是已授权付费调用；formal Agent 仍为 0，不能笼统称本轮没有任何付费 API 调用。
完整 ClawGym 200 题与 JobBench main 65 题无模型原生 Job 已启动，分别并发 1 和 2；
所有统计按原生完成结果更新，未完成项不计 READY。

query-optimize 修正后的实际 CTRF 为 6 tests / 2 passed / 4 failed / 0 skipped；
polyglot 为 1 test / 0 passed / 1 failed / 0 skipped。两者 NOP 合法零分且 cleanup 独立确认。
HF 正确镜像的原生安装/Verifier检查实际执行 4 tests / 4 failed / 0 skipped，资源已清理；
但这不证明 Agent 所需 Hugging Face 下载可用，网络 Gate 仍为 PARTIAL。

首批镜像准备冻结为 8 个小型官方 linux/amd64 镜像，压缩层总量 264,793,810 字节，
一次仅一个下载/传输/导入；单归档上限 100 MB、总归档上限 550 MB。
此前未能确认的另外 9 个 Registry引用已通过同一自有 E2B 准备沙箱只读核验，均存在。
它们压缩层总量 1,520,998,145 字节；尚未导入者仍记缺失。

新增准备回归 47 passed；0990c143 的真实 GitHub Ruff/ty/Package Build/Linux Tests/Windows Tests 均成功。b3aebaf3 的 Windows 唯一失败是 POSIX 执行权限断言（其余 7,850 passed、
132 skipped），已限制为 POSIX 平台断言，同时所有平台检查生成脚本保持 LF。
没有跳过通用 Windows 测试、删除测试或改变评分/运行语义。

JobBench main 无模型 Gate 的 civil_engineers/task2 出现一次安装阶段工作目录检查超时：
Docker-over-SSH 的 test -d /workspace 在 30 秒到达上限。Environment 已启动，但
Agent execution 和 Verifier 均未开始；原始 RuntimeError 与 operation_interrupted 已保存，
Provider 记录随后 cleaned，独立查询确认容器/网络/卷与私有 workspace 均不存在。尚未证实是 SSH 链路、Engine 响应或其他原因，不据此修改
Harbor core 或调大原生 Deadline。此失败不能写成普通零分，后续恢复也不能消除首次失败。

剩余 43 个官方镜像已全部取得 Registry manifest/linux-amd64 元数据，压缩层逐引用求和
为 12,005,884,768 字节（含重复层）；最大单镜像压缩层 1,432,498,021 字节。
部署单路执行，归档总上限 16 GB、单归档上限 1.6 GB，加载镜像大小累计上限 150 GB，
149 始终保留至少 100 GB 空闲（开始时约 5.42 TB）。只使用自有私有 staging。
E2B 当前账户确认单次 TTL 上限 1 小时，准备沙箱使用官方 set_timeout 有界续期；
各下载、传输、加载操作仍有独立上限，不更改账户或服务配置。

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

## 最新可核验快照

2026-10-14T00:06:49.663810+00:00：默认Provider动态就绪 ALF134、Claw200、TB6、main59、easy34。另有TB现成E2B后端20/89独立无模型证据；只在单独Provider证据文件记录，不覆盖149的三个HF网络BLOCKED。剩余队列持续运行。1b7c78f9的GitHub五项代码检查全部成功，正式Actor仍0。

JobBench main后续已全部65/65通过动态门槛、独立清理并归档全部原生准备/失败/恢复历史。easy剩余与TB E2B队列继续运行；仍等待全551必要Gate才派发正式Actor。

2026-10-14T00:16:39.241407+00:00：HF新增实际Task沙箱内config/tokenizer/model.safetensors HEAD均200，未下载任何权重；原始Verifier4项实际测试、合法0、无原生异常、独立404。相关proof单独保存；旧controller断线后Sandbox404的未完成HEAD尝试也保留。TB可选E2B当前已独立确认33/89个唯一Task无模型Gate，完成尝试34次含HF两次不同验证，不重复计题。原始Remote BLOCKED不变。

2026-10-14T00:39:42.413514+00:00: 两项新问题据实保留。QEMU native Oracle的E2B创建先报default tag不存在，但只读tags API同时列出旧default build；原生force_build重建随后在E2B provisioning阶段因bullseye多个APT包404失败。尚未证明该E2B模板可用，不能提升全89 E2B正式配置。未创建client Trial sandbox，平台内部build VM清理由E2B管理，未独立确认。现有生产Remote Docker隔离Oracle已实际启动Alpine guest并看到kernel 6.6.4-1-lts，原始Verifier/清理待最终结果。两次原生失败不覆盖，也不作为合法零分。

CI d4d4632b实际Linux runtime失败1项dynamic/shared-allowlist：8796 non-runtime通过，runtime60通过/1失败/1跳过；Windows、Ruff、ty、构建通过。CI原生失败Trial无Harbor异常，Verifier因允许的www.iana.org请求Network is unreachable写0；同轮对应另一Trial写1。已下载诊断工件并保存SHA/具体失败证据，根因仍未定，不借此修改通用网络、移除测试或宣称最新CI全绿。下一次具体证据提交将在真实CI再次检查。

2026-10-14T00:57:50.992454+00:00: QEMU Remote原生Oracle已正常结束，guest确实启动；原始Verifier仍因缺少system curl而无法消费缓存file:// uv发行归档，CTRF未生成，RC0/Reward0不记Ready。已定位到通用Verifier准备工具，新增精确固定URI/原installer参数的本地SHA校验复制，其他curl请求照原样转交。修复前真实生成shim退出127（1 fail/1 pass），修复后相关52 tests通过、全仓Ruff/Format/ty和修改源码ty通过。官方test.sh、断言、资源、Agent初始状态、Deadline及Reward公式不改；现有准备副本不覆写。动态复验尚待新的独立副本。

JobBench easy首次完整63题原生Job已结束：62合法Verifier/Judge路径、1环境setup工作目录探针30s超时；63项资源独立清理，完整首次轨迹归档SHA `04adc6399b207a7840640743c06c59746437c376600d5bc64305601760fe2880`。单题恢复以新的原生Job执行、原失败/归档不变。该超时与QEMU约95.98MB verifier archive上传时间相交，只有相关性与此前受控传输竞争证据；本条具体故障根因尚未完全证实。恢复不与大型Remote归档上传重叠。


### main65/easy63完整门槛与恢复归档：2026-10-14T01:07:05.670187+00:00

main65/easy63全部原生无模型安装、非空固定fixture、真实逐条替代Judge及独立资源清理通过。easy首次63题中有1次setup基础设施超时，恢复Trial secretaries_and_administrative_a__ayCer3z在停止其他Remote大型上传后正常结束，Verifier RC0/合法0、10条Judge结果、0Judge失败，不能写成首次运行零故障。含全部64次easy尝试的私有轨迹归档SHA `7cfd4bd8201421643c36d3e1dc5f2cdf81e05f96faaf027bed1b0c05c023617e`，首次63归档不覆盖。准备阶段已确认至少1336个Judge响应，账单/不完整重试费用未知且不记为0；正式Actor仍0。

TB可选E2B独立门槛72/89（73次完成尝试，HF两次不重复计题）。生产Remote的3个HF网络阻塞保留。新curlfile准备副本哈希和66491ff8准备工具版本另存，原生QEMU安装fixture/Oracle按同一Job单并发顺序验证中，不能提前记Ready。正式551仍等待全部必要Gate；没有修改官方Task定义、共享daemon或生产SSH连接方式。


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
