# Harbor OpenHarnessAgent Recorder v2 最小集成

日期：2026-10-14（Asia/Shanghai）
状态：**已完成静态审查、定向回归和一条真实 Trial 验证；补丁仅在本地 Worktree，未推送。**

## 结论

当前没有满足目标的零改动配置：OpenHarness CLI 已支持 `--trajectory-dir`，但
Harbor 的 `OpenHarnessOptions` 原先没有暴露开关，也不会把该参数加入 CLI。最小通用
改动已经在独立 Worktree 完成，只改 `OpenHarnessAgent` 和对应契约测试。Recorder
写入已有的 `/logs/agent`，Harbor 原有递归日志下载会保存其目录，因此没有新增传输、
ArtifactHandler、Sandbox 生命周期或清理逻辑。

## 版本与工作树

| 项目 | 版本/状态 |
|---|---|
| Harbor 基线 | `34584831354e59c69059ca5fb5c2e569f8ee82b8` |
| Recorder 补丁 Worktree | `harbor-recorder-optin`, commit `5715cc902859d451ea162d3c7d72285d28196304` |
| Open-Harness2 | `03e65d03e0575fc77b40628bf58b8d375a94fca2` |
| 历史真实 Trial 配置中的 Open-Harness wheel | SHA-256 `05bcd684f8c37beaa280927248dbb239f79807fe33e43cfb47b3d8e2c7851b83`（原文件已不在磁盘） |
| 当前从同一 Open-Harness commit 重建的 wheel | SHA-256 `7f74c3facee76b2b252f8a64a8ab83134451bf72972e9601288adc1626dcc037` |
| 上游 clone 工作树 | Open-Harness2、openharness-rl、Harbor 审计 clone 均 clean |

实际 Harbor 运行使用 `/home/cky/workspace/RSI/harbor-rsi/.venv/bin/harbor` 和该
目录下的 editable 源码；它不是上面的 Git Worktree，且 `OpenHarnessAgent` 的安装、
模型环境和选项存在其他版本差异。本报告不把两份源码宣称为同一完整版本。实际运行
源码的 Recorder 参数位置通过只读检查确认与补丁逻辑一致；正式复现实验应先固定
运行 wheel/source 的 commit 和文件哈希。

## 最小 Diff 计划与实现

门禁审查确认只需以下变更：

1. 在 `src/harbor/agents/installed/open_harness.py` 的 `OpenHarnessOptions` 增加
   唯一配置项 `record_trajectory: bool = False`。
2. 在 `OpenHarnessAgent.run()` 构造现有 argv 后，仅在该值为真时追加：
   `--trajectory-dir /logs/agent/openharness-rollout`。
3. 在 `tests/unit/rsi/test_contract.py` 增加开启/关闭两条契约测试，并保留原命令
   前缀断言。

补丁统计：

```text
src/harbor/agents/installed/open_harness.py |  6 ++++++
tests/unit/rsi/test_contract.py             | 32 +++++++++++++++++++++++++++++
2 files changed, 38 insertions(+)
```

关闭 Recorder 时，新增字段只取默认值，argv 不包含 `--trajectory-dir`；stdout、
stderr、ATIF、Verifier、超时、重试和清理路径均未改变。开启时使用已有
`environment_logs_dir`，没有 task、benchmark 或模型判断，也没有新增可任意指定的
路径参数。

## 工件持久化证据

`Trial._download_agent_logs()` 调用已有 `download_dir()`，源目录是 agent 环境的
`/logs/agent`，目标是 Trial 的 `agent` 目录。Recorder 的
`openharness-rollout/manifest.json`、`events.jsonl` 和 content-addressed
`artifacts/` 因此随普通 agent 日志递归下载。没有修改 Trial、Sandbox、Verifier
或 ArtifactHandler。

## 定向验证

在补丁 Worktree 使用 Harbor 虚拟环境执行：

```text
PYTHONPATH=<worktree>/src <harbor-rsi>/.venv/bin/pytest -q tests/unit/rsi/test_contract.py
28 passed in 0.37s
<harbor-rsi>/.venv/bin/ruff check src/harbor/agents/installed/open_harness.py tests/unit/rsi/test_contract.py
All checks passed!
git diff --check 34584831..5715cc90
passed
```

关闭/开启 argv 对照：

```text
关闭（原有命令）：
/tmp/harbor-open-harness-venv/bin/open-harness --cwd <task-cwd> --print --mode json \
  --config <runtime>/config.json --prompt-file <runtime>/instruction.txt

开启（仅新增尾部参数）：
同上 --trajectory-dir /logs/agent/openharness-rollout
```

## 真实 Harbor/E2B Trial

已有一次使用上述 Recorder 能力的真实 smoke。该历史 Trial 的配置记录了旧 wheel
SHA `05bcd684f8c37beaa280927248dbb239f79807fe33e43cfb47b3d8e2c7851b83`；旧文件已
丢失，因此不能用当前重建 wheel 的哈希替代历史工件身份：

- Task：`harbor/extra-instruction-path`（独立开发任务，不是 TB2.0/TB2.1）；
- Trial：`98a24372-de12-4897-81f0-33047af13e16`；
- Model：`deepseek/deepseek-flash`；
- Reward：`1.0`，completed；
- Recorder 目录：
  `runtime-evidence/harbor-recorder-smoke-20261013/recorder-optin-smoke/runtime-extra-instruction__G47Fgs6/agent/openharness-rollout/`；
- `manifest.json` SHA-256：
  `0f1b6fa3d26daf97e8cd986288f29de044075a1ef9d2105093bbf49a3e749e3e`；
- `events.jsonl` SHA-256：
  `b5ce2316b15f2517bd435dbd66bdbad9c5e5fd79dd063414923830f77d7a35b5`；
- 轨迹：3 次模型请求、2 次结构化 Tool Call、2 次 Observation，Provider Payload
  可恢复；Trial 结果和 Recorder 位于同一 Trial 目录。

这是同一 Trial 的目录关联，不是通过时间戳或任务名拼接。Sandbox 结束后文件仍可
读取，说明已有日志下载路径足以持久化 Recorder 工件。该 Trial 没有改变默认
Verifier 或清理行为。

## `openharness-sft` 验收

现有 Open-Harness v2 Adapter 已用该真实目录回归：Provider Payload 中的请求消息数
为 `2/4/6`，Tool Call 与 Observation 配对成功，非法 JSON 参数会拒绝。随后使用
固定 `allenai/tmax-2b` revision `39227cc1b9d221c53140e56a66094d84d115d579` 的
真实 Tokenizer 生成 3 条按 Call 样本：总上下文 2754 tokens、监督 216 tokens。
System/User/Tool 和历史 Assistant 被屏蔽，当前 Assistant 输出及结束标记被监督，
没有静默截断或重复 shift。此前 A800 的 1-step BF16 Full SFT 已保存独立 checkpoint；
这份报告不把它当作泛化或正式训练结果。

## 风险与边界

- Recorder 是 opt-in；未设置 `record_trajectory` 的已有任务不产生该目录。
- 只要任务配置的日志下载没有 include/exclude 过滤掉该路径，递归下载就会保留它；
  若未来使用过滤列表，必须显式包含 `openharness-rollout/**`。
- 运行源码和审计 Worktree 不是同一完整版本，不能只凭本地补丁 commit 声称线上
  Harbor 已切换；部署前要固定并记录实际 Harbor wheel/source 版本。
- Provider Payload 可能包含密钥、任务数据或其他敏感内容。训练导出仍由
  `openharness-sft` 做脱敏和来源审计，Harbor 不做 SFT 清洗。
- 本次只验证一条低成本 Trial；不等价于完整 Benchmark、并发运行或排行榜成绩。

## 当前建议

可以在固定 Harbor 运行版本、Open-Harness wheel SHA 和 `record_trajectory=true`
后，继续采集不属于 TB2.0/TB2.1 的成功教师任务。保持 Harbor、Open-Harness 和
RLBridge 核心代码不变，训练侧只读取 Trial `agent/openharness-rollout` 并通过
现有 Adapter 关联同 Trial 的 Reward。当前补丁未推送、未创建 PR，也没有覆盖原有
Checkpoint。
