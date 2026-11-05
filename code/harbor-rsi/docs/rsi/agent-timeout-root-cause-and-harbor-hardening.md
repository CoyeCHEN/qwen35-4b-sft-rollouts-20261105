# 六个 AgentTimeoutError 的归因与 Harbor 通用可靠性修复

| Task | Benchmark | Timeout | Reward | 首要原因 | 责任层 | 是否 Harbor Bug | 修复 |
|---|---|---:|---:|---|---|---|---|
| `terminal-bench/qemu-alpine-ssh` | Terminal-Bench 2.1 | 900 s | 0.0 | 多轮启动、等待登录与 ISO 排查耗尽预算 | A/B；评分另有 E | 未证实 Deadline Bug；有共同记录缺陷 | 通用记录修复；不改 Agent |
| `terminal-bench/qemu-startup` | Terminal-Bench 2.1 | 900 s | 0.0 | 启动排查接近预算；CLI 完成后 Harbor exec 仍未返回 | B/C（适配层）；评分另有 E/F | 已复现完成后重复传输日志的通用缺陷；本题贡献无法精确量化 | 去除成功后整份日志重放 |
| `terminal-bench/train-fasttext` | Terminal-Bench 2.1 | 3600 s | 0.0 | 单核环境执行长时间 baseline 训练，工具未返回 | A/B；评分另有 E | 未证实 Deadline Bug；有共同记录缺陷 | 通用记录修复；不改训练策略 |
| `terminal-bench/regex-chess` | Terminal-Bench 2.1 | 3600 s | 1.0 | 写出结果后继续长时间 fuzz/检查，最后仍在模型请求中 | A/B；模型请求重试；记录 E | Timeout 本身不是 Bug；轨迹转换/回收有 Bug | 保留 Timeout + 1.0；修复记录 |
| `biostatisticians/task1` | JobBench | 3600 s | 0.6111111111111112 | 已提交三个工作簿，继续高成本数值积分计算直到取消 | A/B | 未证实 Deadline Bug；有共同记录缺陷 | 保留部分成果与原分；不改 Agent |
| `civil_engineers/task1` | JobBench | 3600 s | 0.0 | 外部 PDF/截图获取与 429 重试占用大量时间，未提交工作簿 | A/B；外部服务 | 未证实 Provider/Deadline Bug；有共同记录缺陷 | 保留 empty_output 零分；不改 Agent |

这里的 A–F 按本轮任务定义使用。表中“共同记录缺陷”不表示这些缺陷导致了六次超时。
没有重新运行任何 Case、调用模型、修改 OpenHarness2、修改官方任务、修改旧 TrialResult 或覆盖正式报告。

## 1. 证据身份与不可变边界

本轮基线为 `e0f89d39a3d0f8ca9abba125e4092dc88da15692`，工作树为
`/home/cky/harbor-rsi-final`，独立分支为 `codex/agent-timeout-harbor-hardening`。
开始前经 SSH 核验远端冻结分支同一提交；远端 main 为
`eac7928fe9ee1540faaf52ef639aabfc9a793159`，包含此前架构 PR 的合并。
本分支从正式评测冻结提交创建，以保留依赖的运行修复和完整工件。

唯一正式批次是 [final-4x10](../../artifacts/benchmark-reports/final-4x10/summary.md)。
逐一对照了 `cases.csv`、`attempts.csv`、`run-provenance.json`、`failure-analysis.md`、
`runtime-attestation.json`、`recovery-ledger.json`，以及对应原生 Job/Trial result、JSONL、
lifecycle、工具结果、Verifier 文件和 Remote Docker evidence。
固定最终题集仍为 40，尝试历史仍为 42；两次 QEMU 原始 AgentCleanupError 仍在恢复账本内，
没有用恢复 Trial 覆盖它们。

两个实际 Harbor wheel 均显示 **`0.23.0+rsi.1`**，但它们不是同一构建：

| 构建 | 源码 commit | wheel SHA-256 | 本轮六题中的使用者 |
|---|---|---|---|
| r1 | `75ff336eded98d7627b908bc04c2abfdf0b8cfea` | `733f92ae8bca98a9145b9d965e58bcbdfe207fcca3c84bddf9697a00bab4ee4a` | biostatisticians/task1 |
| r2（pidfd 修复） | `6fe34a677e255c9d342d6a30262d7cdeee0d5de3` | `f5f23ac577d81df53a20d2185077cc29e9dcf0e6d27cd167e86effe58c144341` | 其余五题 |

Native Trial 根目录为 `/home/cky/.local/state/harbor-rsi/final-4x10/`：

| Task | Job | Trial |
|---|---|---|
| qemu-alpine-ssh | final-4x10-tb21-qemu-alpine-r2 | `60b7050b0e0aa51641208cf65766743d__6vq7kJ5` |
| qemu-startup | final-4x10-tb21-remaining7-r2 | `8e58263747da7dc688ad470688fb7282__baPY5Fo` |
| train-fasttext | final-4x10-tb21-remaining7-r2 | `460fc0818971ec83545a76805267b654__rmmFTbG` |
| regex-chess | final-4x10-tb21-remaining7-r2 | `e763e0ac1c9759081af0a4a82ba51b8c__Jr3gFo5` |
| biostatisticians/task1 | final-4x10-jobbench-first | `biostatisticians__task1__PKaDJNv` |
| civil_engineers/task1 | final-4x10-jobbench-remaining | `civil_engineers__task1__tRcm259` |

完整原生 Task ID 是 `LocalTaskId.path`，而不是截断的 Trial 前缀：

| Task | 原生 Task ID |
|---|---|
| qemu-alpine-ssh | `/home/cky/.cache/harbor/tasks/packages/terminal-bench/qemu-alpine-ssh/60b7050b0e0aa51641208cf65766743d340e59575db2c4d2f8628240846c2a28` |
| qemu-startup | `/home/cky/.cache/harbor/tasks/packages/terminal-bench/qemu-startup/8e58263747da7dc688ad470688fb72825c4ba2c1c40443fa0f52963645bbd999` |
| train-fasttext | `/home/cky/.cache/harbor/tasks/packages/terminal-bench/train-fasttext/460fc0818971ec83545a76805267b65459128fad52e68c26a199a0d74022badb` |
| regex-chess | `/home/cky/.cache/harbor/tasks/packages/terminal-bench/regex-chess/e763e0ac1c9759081af0a4a82ba51b8cf9ae5485a93de3bbe42d7d344597bd78` |
| biostatisticians/task1 | `/home/cky/.cache/harbor-rsi/datasets/jobbench-lite10/main/biostatisticians__task1` |
| civil_engineers/task1 | `/home/cky/.cache/harbor-rsi/datasets/jobbench-lite10/main/civil_engineers__task1` |

六题配置均为 `timeout_multiplier=1.0`，Agent timeout/setup override 和 max_timeout 均为空。
两个 QEMU 的 Agent/Verifier 原生预算分别为 900/900 秒；另外两个 TB 为 3600/3600 秒；
两题 JobBench 为 3600/3900 秒。没有调整任何预算。

### 可复现的派生证据

[analyze_agent_timeouts.py](../../scripts/analyze_agent_timeouts.py) 只读取冻结批次，
输出新目录 [agent-timeout-evidence](agent-timeout-evidence/)。六个 JSON 包含原文件哈希、原生身份、
每次请求的 usage、每个工具的参数/结果摘要、日志行号、生命周期和 Provider 证据。
不复制模型 reasoning 内容；凭据模式经过脱敏。

- [requests.csv](agent-timeout-evidence/requests.csv)：276 条可见 `message_start` 请求，逐次 input/cache/output token、完成状态、消息时间戳和下一请求间隔。
- [tools.csv](agent-timeout-evidence/tools.csv)：295 次工具调用，逐次类型、可见返回码、完成状态、工具 timeout、时间字段和原 JSONL 行号。
- CSV的文本excerpt使用JSON字符串编码保留原换行/空白；解码后与对应派生JSON一致。
- 六个 JSON 的 `source_hashes` 覆盖原始 result、stdout、lifecycle、Provider、任务定义/指令/Verifier 脚本及评分文件。

可在仍具有原始日志的工作树执行：

```bash
python3 scripts/analyze_agent_timeouts.py
```

## 2. 时间测量的范围与缺口

原始 OpenHarness CLI 的 `tool_execution_start/update/end` 没有独立事件时间戳。
Assistant 消息的 `timestamp` 是消息创建时间；`message_end` 沿用它，不能作为模型结束时间。
ToolResult 消息有结果时间，因而“前一消息 → ToolResult”的差值**包含模型生成和工具操作**。
它不能冒充单个工具耗时，下一请求间隔也不能冒充 HTTP 请求延迟。
完整 usage 仅来自完成的消息；最后被取消的流没有完整计费账单。

此外控制器墙钟 phase duration 与 Provider `duration_ms`（源码明确用 loop.time）明显不同。
例如 fasttext 的 Agent phase 墙钟为 3389.894 秒，但主 exec 单调时钟持续 3612.555 秒；
bio 为 3322.600 对 3586.389 秒。这不是“提前几分钟触发超时”的充分证据。
没有控制器完整单调阶段日志或系统时钟校正日志，不能确定是何种时钟调整，也不能校准 sandbox/host。
Deadline 使用 asyncio 单调时钟，旧日志无法独立证明每题精确触发误差。

| Task | Agent phase 墙钟（含取消）s | Provider 主 exec 单调耗时 s | 取消请求→host 确认，墙钟 s | Agent phase 结束→Verifier 开始，墙钟 s | Verifier phase 墙钟 s | Verifier exec 单调耗时 s |
|---|---:|---:|---:|---:|---:|---:|
| qemu-alpine-ssh | 848.512 | 887.580 | 2.126 | 29.370 | 9.797 | 4.751 |
| qemu-startup | 854.288 | 902.934 | 18.635 | 96.810 | 8.190 | 5.673 |
| train-fasttext | 3389.894 | 3612.555 | 27.630 | 10.904 | 264.666 | 235.921 |
| regex-chess | 3602.310 | 3589.039 | 2.191 | 219.562 | 151.071 | 146.188 |
| biostatisticians/task1 | 3322.600 | 3586.389 | 6.682 | 111.412 | 76.991 | 75.993 |
| civil_engineers/task1 | 3328.833 | 3583.470 | 1.601 | 118.507 | 7.645 | 1.929 |

主 exec 在 Agent phase 内晚于 scope.prepare、pwd、mkdir、上传配置才开始，可能包含取消后的输出排空。
这些数值不能直接作为“模型实际运行时间”或预算起点。Verifier phase 包含准备、执行和日志回收；
旧日志没有 `reward_written_at`，所以表中也不声称测得了精确的 Reward 写入延迟。
阶段间日志回收等待发生在 Agent 停止之后，不能倒算成提前扣除 Agent 预算。

最后一次工具的**前一模型消息创建时间**与取消时间如下（UTC）：

| Task | 最后工具前模型消息 | controller cancel_requested_at | 两者墙钟差 s（跨时钟，仅诊断） |
|---|---|---|---:|
| qemu-alpine-ssh | 10-13 00:44:32.733 | 10-13 00:44:33.889 | 1.156 |
| qemu-startup | 10-13 01:01:40.096 | 10-13 01:02:23.904 | 43.808 |
| train-fasttext | 10-13 01:09:03.794 | 10-13 02:01:00.710 | 3116.916 |
| regex-chess | 10-13 04:11:38.290 | 10-13 04:12:31.548 | 53.258 |
| biostatisticians/task1 | 10-12 17:27:38.808 | 10-12 18:02:07.927 | 2069.119 |
| civil_engineers/task1 | 10-13 01:40:42.174 | 10-13 01:41:52.836 | 70.662 |

**“发起最后工具时距离原生 Deadline 几秒”无法精确恢复**。缺少独立 tool start、请求结束和同域单调 Deadline。
每次模型的精确耗时也无法恢复；CSV 留空 `exact_duration_sec`，而不是填写看似精确的错误数字。
本轮新增单调生命周期诊断，用于未来离线或正式运行；没有向旧结果填入推算的时间。

## 3. 逐题轨迹归因

### 3.1 qemu-alpine-ssh

证据：[派生 JSON](agent-timeout-evidence/qemu-alpine-ssh.json)，对应 Job/Trial 见上表。
15 条完成的 assistant 消息，16 次 turn_start（最后一个 turn 尚未生成 message_start）；
不能把它表述为已知 16 次 HTTP 请求。可见 input 含缓存 157945、output 18615 token。
20 次 bash，20 次都有工具结束记录；工具错误标记 1 次。逐次返回码在 tools.csv，不存在的码留空。

最长已结束操作的“模型+工具间隔”为 339.344、263.831、94.822 秒：
分别是 expect 等待登录（脚本 timeout=300，工具参数 timeout=340）、另一轮 expect timeout=240、
以及 `timeout 90 qemu-system-x86_64 ...`。有 BIOS 启动等待、未等到 login 后再次尝试、ISO/内核提取；
没有训练。到截止附近仍在检查 `/BOOT/VMLINUZ_LTS` 与 initramfs/APK，之后开始下一个模型 turn。
没有完整 SSH 成功交付证据。

scope 清理记录为三份，累计看到 2 个进程；全部 `remaining=[]`、`kernel_no_children=true`，
host `cleanup_confirmed=true`，最终 Provider `cleaned`，无 infrastructure_errors。
Verifier script 被调用并返回 0；但 apt 包 404、curl/uvx 缺失导致 pytest 未运行，官方脚本自行写 Reward=0。
因此不能将这个零分解释为“SSH 检查已经失败”。

主因 A/B：启动/登录等待和持续排查占用预算（高确定度）。E：官方评分脚本依赖失败（高确定度）。
F：精确 Deadline 误差、每次工具耗时不可恢复。340 秒工具 timeout 是否超过当时真实剩余预算无法确证；
没有证据表明它推迟了 Harbor 的取消。pidfd 修复解决了清理故障，不负责完成 VM/SSH 任务。
本题不需要 Agent 策略改动或任务特判，只应用通用记录补丁。

### 3.2 qemu-startup

证据：[派生 JSON](agent-timeout-evidence/qemu-startup.json)。66 次可见请求均完成，
input 4403535、output 66609 token。70 次 bash、1 次 write，共 71 次结束，9 次工具错误。
启动过程有 QEMU 重启、24×sleep 5 的启动轮询（模型+工具间隔 126.182 秒）、
20×sleep 5 的轮询（77.290 秒）、进程排查（85.029 秒）、直接内核/initramfs 启动和 telnet proxy。

最后工具检查 PID/端口；最后 assistant（原 JSONL 64894 行开始，创建时间 01:01:47.738 UTC）
说 VM 和 telnet 已就绪，QEMU PID=711、proxy PID=716。65642 行的 CLI result 是 `completed/exitCode=0`，
原生 `open-harness.complete.json` 也确实为 exit_code=0。
这证明 **CLI 已正常完成，不能说它一直在模型循环里直到截止**。

Harbor 适配层的 shell 在写 completion marker 后执行 `cat stdout.jsonl`、`cat stderr`，
整个主 exec 才能返回。该 Trial 的 stdout 为 **21188528 bytes**；Provider 原证据第 29 行
在 01:02:40.408608 记录主 exec 正常退出，单调耗时 902.934 秒。
此前 lifecycle 已在 01:02:23.904091 请求取消；host 在 01:02:42.538727 确认。
原有完整日志重放使“已完成 CLI”仍可能卡在 native Agent phase，这已通过通用慢输出环境离线复现。
没有 marker 创建时间、exec 字节传输分段时间和单调 CLI 退出时间，故不能证明本题唯一原因就是传输，
也不能量化传输与原有启动排查各消耗了多少真实剩余预算。

取消报告实际终止了 PID 711/716，两个服务不再保留；这符合超时后必须清理的契约。
不能为了让 telnet Verifier 得分而忽略残留 Agent 子进程。
Verifier 另因 apt 404/curl/uvx 缺失没有执行 pytest，原生 Reward=0 也不能归结为杀掉 VM 所致。

主因 B/C：接近预算的任务执行与完成后 exec 等待（完成/等待顺序高确定度；历史耗时份额 F）。
E：官方依赖失败。Harbor 安装/运行适配层有已证实的通用日志重放问题，需要修改；
没有证实 Remote Docker SSH 本身违反 timeout 契约。
补丁不重判旧 Trial，不承诺修复后此题必然得分。

### 3.3 train-fasttext

证据：[派生 JSON](agent-timeout-evidence/train-fasttext.json)。12 次请求完成，
input 61986、output 5038 token。19 次 bash，其中最后一次没有工具结束。
前面安装 build-essential、编译/安装 fasttext，完成间隔分别 43.833/73.212 秒；
读取 650000 条训练记录及 10000 条测试记录，生成约 462 MB 文本训练集。

最后工具在原 JSONL 末段创建 `/tmp/train_eval.py` 并运行 baseline：
`--dim 100 --bucket 200000 --epoch 5 --lr 0.5 --wordNgrams 1`；
代码默认 thread=40，任务原生资源只有 **1 CPU、4096 MB**。
训练后才 save_model，默认输出 `/tmp/m.bin`，任务要求的最终输出则是 `/app/model.bin`。
最后 assistant 明确表示开始 baseline 测量，而不是已交付模型。
整个工具没有显式 tool timeout；截止时仍未返回，不能给它编造返回码或精确训练耗时。
这里存在训练计算量/资源配置与时间规划问题，但本轮不调整 Agent 的参数。

三份 scope 累计记录 5 个进程，清理确认后无子进程；取消确认墙钟 27.630 秒，包含控制命令和 exec 等待。
这属于停止/确认阶段，未证明 Agent 又得到额外训练预算。
Verifier clone fastText 遇 TLS 错误，uv 下载连接 GitHub 超时（日志明确 133868 ms）、最终 uvx 缺失，
没有执行具体 pytest；原生 shell 仍返回 0 并写合法 Reward=0。

主因 A/B（高确定度）；E 的外网评分依赖失败单独记录。无 Deadline 算法错误证据。
Harbor 不应替 Agent 修正训练路径、线程数、epoch，也不应修改官方 test.sh。

### 3.4 regex-chess：Timeout 与 1.0 为什么同时成立

证据：[派生 JSON](agent-timeout-evidence/regex-chess.json)。30 次可见请求开始、29 次完成，
完整消息 usage 为 input 2856669、output 154174 token；最后请求没有完整 usage。
24 次 bash、3 次 edit、1 次 write，28 次工具均结束。
有一次模型 `ReadTimeout` 自动重试（delay=2000 ms、maxAttempts=3，日志 retry_end success）；
不能将逻辑请求数当成确切 HTTP 尝试数。

先生成 7961 条规则，再修订到 7962；原 JSONL 106164 行的生成工具结果在
04:03:57.820 UTC 记录 **7962 pairs、1172560 bytes**，满足条数/体积限制。
之后继续验证而没有立即结束：

- fuzz 命令内部 `timeout 1800 ... | tail -20` 的模型+工具间隔 1807.079 秒；返回码 0 来自 pipeline 尾部，不能证明 fuzz 上游成功正常退出。
- `timeout 900 python3 -u fuzz.py 3 1 ...` 的间隔 518.042 秒，输出 tested=352、fails=0。
- 多次规则数量、compile 时间和 legal move 检查。单个 `sed` 调用前后间隔 336.793 秒包含模型生成，不能误称 sed 本身运行五分钟。

截止前最后工具检查完规则编译/数量，随后模型请求仍未完成；没有正常 CLI completion marker。
取消确认墙钟 2.191 秒，全部 scope 均确认无子进程。Verifier 执行既有文件 `/app/re.json`，
原生 test-stdout 显示 **4 passed in 129.55s**，Provider exec=146.188 秒、return_code=0，Reward=1。
评分测试实际成功与 Agent 没有在时间内正常结束是两个独立事实。

主因 A/B：完成成果后继续验证及模型请求（高确定度）。重试是次要因素，不足以独立解释一小时预算。
记录缺陷 E：该流最后一个 `agent_end` snapshot 后还有 6 条完整 assistant 与 6 条 ToolResult，
旧转换器会丢弃这些消息；同时 lifecycle metadata 阻止 post-run 转换。
修复记录，但绝不抹去 `AgentTimeoutError + Reward=1.0`。
内部 shell timeout=1800/900 是否大于真实剩余预算不能由跨时钟日志精确确定；Harbor 取消没有因此失效。

### 3.5 biostatisticians/task1

证据：[派生 JSON](agent-timeout-evidence/biostatisticians--task1.json)。52 次请求完成，
input 2680226、output 74472 token。bash=41、write=6、edit=5、read=2；54 次工具，53 次结束。
外网参考资料获取有 curl/搜索失败；最长已结束间隔包括 jina/blogspot/Wayback 143.652 秒、
多个 searx 实例 103.217 秒、group sequential 数值计算 95.564 秒。

三个已实际保存并回收的成果：`Baseline_Subgroup_Analysis.xlsx`（22009 bytes）、
`Sample_Size_Justification.xlsx`（18030）、`Eligibility_Analysis.xlsx`（13513）。
不是“没有提交”。之后 Agent 修正双侧 alpha 计算，重复运行数值脚本；
最后工具（JSONL 73629 行）对 step=0.02、0.01、0.005、0.0025、0.001、0.0005 逐级细化，
构造 `GRID[:, None]` 密度矩阵，内含 60 次二分和重复积分。
其复杂度/内存随细网格显著增长；工具无显式 timeout，截止时仍未结束。
没有 CPU/内存采样，不能断言具体耗时份额或 OOM；确实没有工具返回记录。

生命周期三份 scope 累计 4 个进程，无残留；host 确认墙钟 6.682 秒。
官方 JobBench judge `status=ok`、44/72 分、5/8 rubrics 通过、judge_failures=0，
native Reward=0.6111111111111112；Verifier script exit=0。

主因 A/B：已经提交部分成果后继续高成本计算（高确定度）。外网检索是次要因素。
无 Harbor/Provider Deadline Bug 证据，不能以超时将有效部分分数强制归零。
应用通用记录修复，不修改 Agent 或任务文件。

### 3.6 civil_engineers/task1

证据：[派生 JSON](agent-timeout-evidence/civil_engineers--task1.json)。101 次可见请求开始、
100 次完成，input 3698626、output 43361 token；bash=91、read=12，共 103 次工具全部有结束。
大量操作用于 WSDOT PDF、代理、截图服务和 HTTP429 处理。
`/tmp/fetch_pages.py` 重试循环的模型+工具间隔 **1320.798 秒**，日志显示 page 7 第3/4次尝试仍429；
另有外网命令间隔 155.344、106.178 秒。

最后几步尝试替代截图/解码，最后工具是 read `/tmp/ss4.png`，然后模型流在 Deadline 被取消。
要求的 `Miller_Creek_Culvert_Estimate.xlsx` 没有保存到输出工件，artifacts 只有 manifest。
官方 JobBench 结果是 `status=empty_output`、0/50、judge_failures=0；这是明确的合法空输出零分，
不是 Judge API 故障。研究过程文件不等同于提交成果。

三份 scope 累计看到 2 个进程，清理确认墙钟 1.601 秒，无残留；Verifier exit=0。
主因 A/B：重复外网访问/等待，没有及时生成成果（高确定度）。
第三方页面的429不能误归为模型 Provider 限流或 Harbor 重试；没有 SSH/Remote Docker 故障证据。
不修改 OpenHarness 工具策略，只应用通用记录修复。

## 4. 官方链路、预算和取消审查

对照的官方源码是本地完整 checkout：
`/home/cky/.local/share/harbor-rsi/upstream/harbor-official-1e5c5c6db929a10a140d05e606882c671ae20729/`。
对照包括 Trial、SingleStepTrial、Verifier、queue、Job TaskGroup、BaseInstalledAgent。
不能将 RSI 的可选 owned-process barrier 描述成官方自带机制；它是已存在的通用增强，本轮继续复用。

正式链仍为：原生 Job/queue → Trial prepare/setup → 原生 Agent phase → 安全终止 barrier →
原生日志/Artifact 回收 → 原生 Verifier → TrialResult → 原生恢复/清理。
无新增 Job、Trial、Retry、TimeoutManager、TaskRunner 或生命周期调度器。

| 审查问题 | 结论与证据 |
|---|---|
| 原生 Task timeout 严格遵守吗？ | 预算解析正确、multiplier=1；asyncio 使用单调时钟。六题无预算扩大证据，但旧日志缺少单调 deadline，不能精确声称触发误差为0。新测试验证原生截止及墙钟倒退。 |
| 安装/执行/取消/Verifier 分离吗？ | setup 在 prepare；Agent scope.prepare/pwd/config 上传属于运行适配开销，在 Agent phase 内；取消确认与正常 release 是收尾；Verifier 有独立预算。日志回收不允许 Agent 继续运行。 |
| 长工具会让 Agent 超预算吗？ | 单个工具可以没有 timeout 或设很大值，但 phase 取消会触发 owned-process barrier；double-fork/setsid/长期 sleep 回归验证。预算到达不代表所有收尾已在同一瞬间结束。 |
| Provider 取消后能无限等吗？ | 已证实旧 transport 的 kill 后 process.wait 无预算。现加10秒退出确认上限，失败显式 RemoteDockerError；不声称 remote tree 已清理。任意第三方 Provider 若吞 CancelledError/无视 timeout 仍不可保证，属于 Provider 合作契约。 |
| Agent 结束后能确认无残留吗？ | 超时：六题都有 cleanup_confirmed、remaining=[]、kernel_no_children。正常成功：release 故意允许任务要求的后台服务存活，最后由原生环境 stop 清理。不能把正常成功定义为“所有服务立即杀光”。 |
| AgentTimeout 会误变 Infrastructure Error 吗？ | 六题没有；离线发现 deadline+cleanup 双故障会丢失 deadline。现 primary 保留 AgentTimeout，infra 单独记录 cleanup，且禁止 Verifier。 |
| 超时后 Verifier 按官方语义执行吗？ | 官方 SingleStep 捕获 AgentTimeout/非零退出再评分；RSI 仅增加清理确认前置条件。六题 script 均实际启动，exit0；三个TB具体pytest未启动，不能混淆。 |
| 有 Reward 是否保留 Timeout？ | 是，六题原始结果证明；0/部分分/1.0 回归均同时保留。 |
| cleanup 会覆盖原错误吗？ | 原有 release-failure note、恢复/stop errors 已保护多数场景；本轮补足 deadline+cancel失败、正常release失败漏诊断、以及 secondary phase failure 的记录。 |
| 一个 Trial 超时会取消其他吗？ | native queue/run 捕获并持久化单题失败；TaskGroup 并发 healthy/timeout Trial 和独立进程 scope 测试通过。Job 主动取消仍按官方语义传播。 |

官方 wait_for + 外层 `except TimeoutError` 本来也不能区分内部 Timeout 与 phase 到期。
不过六份原生`exception_info.exception_traceback`均显示同一条实际取消链：
`asyncio.tasks.wait_for`取消`execute` → OpenHarness适配层`run`第493行主exec →
`AgentEnvironmentScope.exec`第76行shield等待抛CancelledError → lifecycle第161行wait_for →
`asyncio.timeouts.__aexit__`第115行转TimeoutError。
没有一份是由transport内部短timeout抛出的异常；因此H4的离线误分类缺陷不能冒充这六题的历史主因。
本轮用 **标准 `asyncio.timeout(...).expired()`** 替换该 Agent 阶段的辨别，保持同一预算和取消/评分语义。
没有在 install/Verifier/环境阶段进行无关重构；这些阶段的类似边界不在六题真实故障证据内。

## 5. 已证实的通用缺陷与最小补丁

| 编号 | 证据 / 修复前失败测试 | 责任模块与修改 | 修复后契约 |
|---|---|---|---|
| H1 | 六题只有 lifecycle metadata，usage/trajectory为空；metadata-only hook 测试失败 | `Trial._populate_agent_context` 忽略 metadata 判断待回收状态 | 回收原始日志与usage，同时保留清理/Timeout metadata；既有0 token不覆盖 |
| H2 | regex snapshot后6+6完整消息；retry suffix测试漏消息 | RSI JSONL→ATIF converter 拼接最后snapshot之后完整 message_end | 不重复snapshot前历史，不臆造未完成usage |
| H3 | qemu-startup完成marker + 21MB stdout，主exec仍等待；慢输出fixture两种exit测试超时 | Harbor OpenHarness **运行适配层**停止成功后cat整份日志，失败仅输出有界tail | 原文件不变，由原生文件回收；模型/Agent loop不变 |
| H4 | 两种Agent内部Timeout被误转AgentTimeout的测试失败 | Agent phase 与既有managed helper使用标准asyncio.timeout.expired | 只有native预算到期变AgentTimeout；内部Timeout保留原异常并阻止继续评分 |
| H5 | Deadline+cancel失败测试仅得到AgentCleanupError | 既有scope给cleanup error附带native timeout；Trial记录primary+独立infra | 保留截止事实；未确认Agent终止仍禁止Verifier |
| H6 | 先timeout后Verifier失败没有独立结果记录 | TrialResult增加兼容默认的secondary_errors，复用phase/ExceptionInfo形状 | 不覆盖primary，也不把评分失败无差别标成infra |
| H7 | Provider kill后延迟wait fixture超出预算 | 独立Remote Docker transport给本地client退出确认10秒上限 | 不重放命令，不以SSH client退出冒充remote tree清理 |
| H8 | 正常Agent退出但release失败时lifecycle.json未生成 | 既有helper的诊断写入放入finally | cleanup失败和原始错误可审计，不绕过安全barrier |
| H9 | 原生VerifierResult不存script exitcode；0/非零+合法reward测试失败 | VerifierResult增加可选return_code，Verifier返回实际script_result.return_code | 同时保留原reward和真实退出码，不改变官方reward优先语义 |

新增单调诊断是观测修复：`agent_started_monotonic`、`agent_budget_sec`、`deadline_expired`、
`cancel_requested_monotonic`、`confirmed_monotonic`、`agent_elapsed_sec`。
原墙钟字段继续保留；这些字段没有写回历史六题。

H1/H4/H5/H6/H9 才需要最小 Harbor core 变更：单靠 Provider/安装适配层不能恢复
被 Trial guard 跳过的 post-run hook、区分 native Budget、或保存已被 primary-first 丢弃的次要失败。
优先在适配层和独立 Provider 处理 H2/H3/H7；没有改 Benchmark 分支。
所有修复均用 Fake Agent/Environment、离线 CLI shell 或本地故障注入复现，和任务名称无关。

## 6. pidfd fallback 的安全性

`process_supervisor.py` 的实现本轮**不改**，仅扩大测试。现有设计正确：先取得 pidfd，
再读 `/proc/<pid>/stat` 比较 start_ticks，然后通过 handle 发信号；finally 关闭fd。
Python wrappers 缺失时调用Linux syscall（支持 x86_64/aarch64/riscv64），不是 os.kill(pid)。
内核/API不支持或权限不足时失败闭合，Verifier不能通过未确认终止的barrier。

| 情况 | 验证 |
|---|---|
| Python提供pidfd API | 优先使用wrapper，不走raw syscall |
| Python没有API | 真实sleep进程测试：mismatch不杀，正确identity可杀 |
| 内核/syscall不支持 | 注入ENOSYS，传播错误，无PID-onlyfallback |
| syscall错误/权限不足 | EINVAL/EPERM传播；send错误也关闭fd |
| 已退出进程 | open ESRCH或/proc消失安全返回，不误杀 |
| PID重用 | start_ticks mismatch不发信号，已打开handle绑定旧进程 |
| 子树取消 | 已有setsid/double-fork、fork-during-cleanup、completed-command服务测试通过 |
| 取消超时 | 20秒stop_tree deadline必须失败，不能报告cleanup_confirmed |
| 并发Trial | 一题timeout杀自己子树；另一题后台服务仍存活 |
| /proc非原子扫描 | 必须同时具备kernel ECHILD和空descendants，不能只信空扫描 |

QEMU原始两次失败因managed Python缺wrapper，而不是kernel不支持。
恢复后的六题scope都具备kernel无子进程确认，足以证明该已知故障已解决。
不保证所有架构/旧内核都具备pidfd；不支持时应报告cleanup失败，不能绕过安全性。

## 7. 回归与验证

定向离线回归复用了既有 unit、native fake transport、fixture wheel 和本地子进程设施。
没有下载任务重新评分，没有真实模型调用，也没有连接远程Docker。

| 必须覆盖的契约 | 测试位置 |
|---|---|
| 正常Agent退出；native deadline；合法0/部分/非零reward | `test_lifecycle.py`、`test_deadline_contract.py` |
| cancel失败；cleanup失败；Agent/cleanup双错；Verifier失败 | 同上及既有`test_trial_cleanup.py`；secondary_errors单独验证 |
| 两个Trial并发，一题timeout | native Trial TaskGroup + 真正独立进程scope |
| 长工具不退出；双fork/setsid；取消延迟 | lifecycle长sleep与Remote Docker cancellation故障注入 |
| 无系统Python、managed interpreter | 既有`test_contract.py`安装bootstrap/uv路径及lifecycle私有interpreter测试 |
| pidfd fallback/API/errors/identity/timeout | `test_process_supervisor_pidfd.py` |
| Providertimeout、文件回收 | 既有`test_remote_docker_provider.py`超时传递、嵌套二进制archive/hash、failed-copy测试；新增transport cancellation |
| 完成后慢日志传输；metadata-only；retry后消息 | `test_timeout_recording.py` |
| Verifier脚本退出码与reward同时保存 | `test_verifier.py` |

最终核验见 [validation.json](agent-timeout-evidence/validation.json)：**294 passed、18 skipped**，
共312项；18项因缺少ALFWorld可选依赖跳过。逐项补丁实施前观察到13个失败回归，修复后全部通过。
Ruff check、全仓format与diff check通过；所有修改源码及新分析脚本的ty通过。
全仓ty仍有50个既有诊断（可选依赖/E2B SDK/legacy）；诊断所在8个文件与冻结基线逐字节相同，
没有掩盖它们，也没有为消除无关诊断增加依赖。

```bash
PYTHONPATH=packages/remote-docker/src uv run --no-sync pytest \
  tests/unit/rsi tests/unit/test_remote_docker_provider.py \
  tests/unit/test_remote_docker_cancellation.py tests/unit/test_trial_cleanup.py \
  tests/unit/test_single_step_trial.py tests/unit/test_trial_verifier_artifact_transfer.py \
  tests/unit/test_trial_verifier_separate.py tests/unit/trial/test_hooks.py \
  tests/unit/trial/test_network_policy.py tests/unit/models/test_trial_agent_config.py \
  tests/unit/test_trial_artifacts.py tests/unit/test_verifier.py \
  tests/unit/test_verifier_env_override.py tests/unit/test_verifier_factory.py \
  tests/unit/test_trial_queue.py -q
uv run --no-sync ruff check --fix .
uv run --no-sync ruff format .
uv run --no-sync ty check
uv run --no-sync ty check \
  src/harbor/trial/trial.py src/harbor/trial/agent_lifecycle.py \
  src/harbor/models/trial/result.py src/harbor/models/verifier/result.py \
  src/harbor/verifier/verifier.py src/harbor/agents/installed/open_harness.py \
  src/harbor/extensions/rsi/trajectory.py \
  packages/remote-docker/src/harbor_remote_docker/transport.py \
  scripts/analyze_agent_timeouts.py
git diff --check
```

上面的PYTHONPATH仅用于独立Provider源代码单测，不用于任何正式评测；没有改动正式wheel环境。
71份原始证据哈希重新核验；冻结报告所有已跟踪文件与e0f89d39逐字节相同。
Remote Docker仍是可选独立Provider；没有增加OpenHarness包依赖、Benchmark依赖或其他第三方依赖。

## 8. 交付结论与架构复核

1. 六次为什么发生：两题VM持续排查；fasttext长训练；regex成果后长验证；bio成果后细网格计算；civil反复外网获取。qemu-startup必须另记“CLI已完成，Harbor exec仍未返回”。逐题证据和确定度见第3节。
2. 正常模型/Agent预算耗尽：alpine、fasttext、regex、bio、civil符合A/B证据；startup含完成边界开销，不能简单全归Agent。没有为了消灭错误计数改变预算。
3. Harbor生命周期/Deadline问题：六题无计算扩大/延迟触发的确证；离线证明内部Timeout误分类、dual-error丢失和release诊断缺口，已修复。
4. Remote Docker：六题没有transport_lost/残留证据；Provider承担通信开销。通用local-client退出确认无限wait已离线复现并限时，和remote Agent树证明分开。
5. pidfd：足以解决Pythonwrapper缺失，保持身份校验；本轮只补测试，unsupported kernel仍失败闭合。
6. 超时后评分/保存：六题Reward+Timeout完整保留；轨迹/Token回收、retry suffix、secondary exception与exitcode确有记录缺口，已补。官方脚本自行写零分的外网失败不改判。
7. 是否继续改core：完成上述必要最小补丁后，无证据支持进一步重构core。需要补观测的未知项不能被称作“已修复”。
8. 实际源码修改：第5节H1–H9及单调诊断；均可跨任务/Provider复现，不含Benchmark名称条件。
9. 官方执行链：保留Job/queue/Trial/Verifier/result/recovery；没有替代runner、timeout或sandbox管理系统。
10. 能否继续接入新任务：可以按Task+Agent+可选Provider契约接入；正常Agent超时、官方外部依赖可用性和未观测的延迟仍需如实记录，不应按任务名补core。

四项原则重新核对：

- **① Sandbox解耦：满足。** Remote Docker实现环境通信和归属；core只调用既有Environment能力。
- **② 新Benchmark不随意改Harbor/OpenHarness：满足。** 本轮所有补丁只处理通用契约；OpenHarness2完全未改。
- **③ 官方标准执行、评分与恢复：满足。** 原生Reward、Timeout、两次基础设施失败和两版wheel历史均保留；不伪装成同版统一结果。
- **④ 职责边界：满足。** Harbor编排并记录；OpenHarness负责Agent决策；Provider负责具体环境与通信。

交付分支以`codex/final-4x10-runtime-freeze`为依赖基线；PR应以该冻结分支为base，
以避免把此前正式评测提交混入本轮最小补丁审阅。当前环境具有SSH推送能力，但没有GitHub API授权或已连接的PR工具；
分支可推送，无法在本会话创建PR，不自动合并。

**本轮无需进一步重构。** 精确HTTP/tool耗时、旧运行单调截止误差、marker创建/传输时序、
Reward精确写入时刻及外部网络故障原因属于证据不足F；没有将这些未知项描述成已修复。
本轮目的完成于区分Agent行为和通用可靠性缺陷，而非提高分数或降低六个错误数字。
