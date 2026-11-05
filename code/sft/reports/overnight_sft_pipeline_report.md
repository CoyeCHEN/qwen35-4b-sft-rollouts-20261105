# Open-Harness 自产轨迹 SFT 闭环报告

日期：2026-10-14（Asia/Shanghai）
状态：**部分完成：已采集 5 条经污染复核后可用的真实正奖励轨迹，并在 A800 完成干净数据的按 Task Group 隔离 Tokenizer/Mask 检查和 1-epoch、5-step Full SFT；独立 dev 集上的 M0/M1 真实 Reward 对照仍未完成。**

## 完成情况

已经完成固定版本核对、Harbor Recorder 补丁审查、真实 Harbor Trial 数据导入、包含 Provider 工具定义的真实 TMax 2B Tokenizer/Mask 检查，以及一轮使用自产轨迹的 BF16 Full SFT smoke。训练没有覆盖官方模型或既有 Checkpoint。

本轮没有启动 TB2.1 或 M0/M1 真实 Agent Reward 对照。原始批量训练曾使用 5 个训练
Task Group，但其中一个后来被 canary 审计排除；清洗后使用 4 个训练 Task Group、保留
1 个组作小样本 holdout。由于任务池不足且 holdout 是事后冻结，结果只证明数据链路和
Trainer 参数更新正确，不代表泛化能力提升。

## 代码版本与来源

| 组件 | 版本或路径 | 证据 |
|---|---|---|
| Open-Harness2 | commit `03e65d03e0575fc77b40628bf58b8d375a94fca2` | `audits/openharness2-20261013/repos/open-harness2` |
| Open-Harness wheel（历史 Trial 配置） | SHA-256 `05bcd684f8c37beaa280927248dbb239f79807fe33e43cfb47b3d8e2c7851b83` | 原 wheel 文件已不在磁盘 |
| Open-Harness wheel（当前重建） | SHA-256 `7f74c3facee76b2b252f8a64a8ab83134451bf72972e9601288adc1626dcc037` | 从同一 clean commit 重建并验证 |
| Harbor-RSI 基线 | commit `34584831354e59c69059ca5fb5c2e569f8ee82b8` | `audits/openharness2-20261013/repos/harbor-rsi` |
| Harbor Recorder 分支 | Worktree `harbor-recorder-optin`, local commit `5715cc90`, 未推送 | `audits/openharness2-20261013/worktrees/harbor-recorder-optin` |
| openharness-rl | commit `5ed11a3fe5d9fed68475ff7ed4fd4a17d5b76252` | `audits/openharness2-20261013/repos/openharness-rl` |
| SFT adapter | 本地 `openharness-sft`, initial commit `766f71a` 加本地证据更新；包含真实 Payload 修复和 A800 数据构建脚本 | `git log` |
| 学生模型 | `allenai/tmax-2b`, revision `39227cc1b9d221c53140e56a66094d84d115d579` | A800 本地 checkout |
| Tokenizer | `tokenizer.json` SHA-256 `87a7830d63fcf43bf241c3c5242e96e62dd3fdc29224ca26fed8ea333db72de4`；chat template SHA-256 `273d8e0e683b885071fb17e08d71e5f2a5ddfb5309756181681de4f5a1822d80` | `reports/sft_data_validation.md` |
| Trainer 环境 | PyTorch `2.8.0+cu128`, Transformers `5.14.0`, Accelerate `1.15.0`, Liger `0.8.4`, Python `3.12.3` | `runtime-evidence/openharness-positive-sft-20261014/a800/environment.json` |

上游 Open-Harness2、openharness-rl 和基线 Harbor clone 的工作树均为 clean。真实运行源码副本 `harbor-rsi/` 与审计 Worktree 当前存在其他版本差异；本轮没有覆盖或同步它们。

## 新增教师批次（隔离验证）

`runtime-evidence/openharness-teacher-batch-20261014/` 目前包含 10 个独立尝试：其中
5 条 Verifier reward 为 1，4 条在安装/环境/生命周期阶段失败，1 条是早期人工取消。
另有上一轮独立保存的 `extra-instruction-path` 正轨迹，原始批次共有 6 条 Canonical
正轨迹；复核发现 `hello-user` 的 `solution/solve.sh` 含有明确的
`terminal-bench-canary` 字符串，因此已从训练数据排除。当前可用于训练的集合为 5 条。
清洗后的任务清单和哈希记录在
`runtime-evidence/openharness-teacher-batch-20261014/task_manifest_clean_v1.json`。
正轨迹包括 `hello-workdir`、
`hello-skills`、`hello-healthcheck` 和 `runtime-skill-merge`，另有独立的
`extra-instruction-path`；
共 24 个模型 Call、21 个 Tool Call，均有 Recorder `run_start/run_end`、完整
`call_payload` 和原始工具事件。批次 Canonical JSONL 的 SHA-256 为
`2eaa257c2da0a391437ebdf0dd64c61cd15f11c2920a556e6d869d14758045c3`。

新增 `hello-user` Trial 为 `8405589b-86b1-48a9-a0d7-385c0693f57b`，Reward `1.0`，
4 calls/5 tools/5 observations，模型费用记录 `$0.000659796`；该 Trial 仅保留作污染
审计证据，不能进入训练。`hello-multi-step-simple`
在 Harbor managed-agent 生命周期预检阶段被拒绝（当前版本只支持单步任务），
`hello-computer-use` 因没有 Dockerfile、Compose 或 `docker_image` 被环境预检拒绝；
两者都没有调用模型，均未进入数据集。

本批次 Harbor 结果中可核对的 DeepSeek 模型费用合计为 `$0.003221244`（包含被排除的
`hello-user`）；清洗后训练可归属费用为 `$0.002561448`。E2B 实际账单没有从本地
Harbor 结果暴露，不能伪造 Sandbox 费用总额。由于任务池和独立 dev 集不足，已停止继续派发。

本轮结束后使用 Harbor 虚拟环境的 `AsyncSandbox.list` 做只读清理核查：看到 8 个
现存 sandbox，按本批次任务名匹配到 0 个，未发现本轮残留运行实例；其他任务的 sandbox
未触碰。

该批次尚未成为正式训练集：`hello-skills` 与 `runtime-skill-merge` 需要按相关
skill 任务组保守合并，原先标作 dev 的两个 no-op 环境任务不能作为模型能力 dev
集，且 `runtime-skill-merge` 是在观察早期失败后追加的任务，不能声称为预注册样本。
因此不把这批数据当作正式泛化实验。A800 上的真实 Tokenizer/Mask 检查已完成，批量
原始训练 split 为 21 rows/5 groups/1422 supervised tokens，其中包含已排除的
`hello-user`，因此原始 checkpoint 不可用于训练结论。清洗后的训练 split 为 17 rows/4
groups/1101 supervised tokens，holdout 为 3 rows/1 group/216 supervised tokens，最大
上下文 1854，未发现全部 label 为 `-100` 或静默截断；
部署端工具执行兼容性仍未验证。

## Recorder 补丁

Harbor Worktree 只改了两个文件：

```text
src/harbor/agents/installed/open_harness.py |  6 ++++++
tests/unit/rsi/test_contract.py             | 32 ++++++++++++++++++++++++++++++++
```

`OpenHarnessOptions.record_trajectory` 默认值为 `False`。开启时，`run()` 只在原 CLI 后追加：

```text
--trajectory-dir /logs/agent/openharness-rollout
```

关闭时 argv 完全不含该参数；路径复用已有 `/logs/agent` 下载目录，不增加 Artifact、Sandbox 生命周期或清理逻辑。正确的 Worktree 定向测试为 `28 passed`，Ruff 与 `git diff --check` 通过。补丁已在独立 Worktree 提交为本地 `5715cc90`，未推送或创建 PR。

## 真实 Harbor Trial

Trial：`98a24372-de12-4897-81f0-33047af13e16`
Job：`cbb2e9f2-963f-46eb-be02-a475170ddd1e`
Task：`harbor/extra-instruction-path`（独立开发任务，不是 TB2.0/TB2.1）
Model：`deepseek/deepseek-flash`
Reward：`1.0`，状态 completed，无 Agent/Verifier/基础设施异常。

Recorder 原始目录：

```text
/home/cky/workspace/RSI/runtime-evidence/harbor-recorder-smoke-20261013/recorder-optin-smoke/runtime-extra-instruction__G47Fgs6/agent/openharness-rollout/
```

其中有 `manifest.json`、`events.jsonl` 和 content-addressed `artifacts/`。Manifest SHA-256 为 `0f1b6fa3d26daf97e8cd986288f29de044075a1ef9d2105093bbf49a3e749e3e`，events SHA-256 为 `b5ce2316b15f2517bd435dbd66bdbad9c5e5fd79dd063414923830f77d7a35b5`。三次模型请求、两次结构化 Tool Call、两次 Observation、每次 Provider Payload 均可恢复；结果 JSON 和 Recorder 位于同一 Trial 目录，没有时间戳或执行顺序启发式关联。

Adapter 的真实回归现在使用 Provider Payload 中的完整 `messages`：三次请求消息数为 `2/4/6`，均包含 system prompt。历史 Tool Call 的 JSON 字符串参数会被解析为 mapping；非法 JSON 直接拒绝。修复文件是 `adapters/openharness_v2.py`，对应真实回归断言位于 `tests/test_adapters.py`。

## TMax Tokenizer 与 Mask

真实 canonical 轨迹：`runtime-evidence/harbor-recorder-smoke-20261013/canonical_positive.json`。按 Call 拆分后 3 条样本；本次检查把每次 Provider Payload 的 `tools` 定义原样传入 TMax Chat Template：

| Call | 输入 tokens | 监督 tokens | 工具 |
|---|---:|---:|---|
| `5634f46d...` | 851 | 145 | `write` |
| `a32cb248...` | 914 | 39 | `bash` |
| `81225992...` | 989 | 32 | 无（最终文本） |

总上下文 `2754` tokens，监督 `216` tokens。System/User/Tool 和历史 Assistant 被屏蔽；当前 Assistant 的 reasoning、工具 XML、文本和 `<|im_end|>` 被监督；没有重复 shift，也没有静默截断。A800 上真实渲染通过，Transformers 仅提示模板没有 `{% generation %}`，使用已有 offset-mask 路径。工具定义传递检查输出哈希为 `27cacc03a4a6d05873c5ceaf8498015e4b28f64f99e195f216d776107fa532af`，位于 `runtime-evidence/harbor-recorder-smoke-20261013/tmax2b-tools-forwarding-check.txt`。

第一 Call 使用 `write`。Open-Harness 工具协议支持该工具，且本次训练保留原始工具语义；A800 上已有探针只验证了 TMax 生成 `bash` 的能力，没有证据证明某个未来部署只支持 bash。因此不能把本次结果解释为“所有 TMax 部署都已验证 write 兼容”；正式扩展前应在目标部署中固定同一工具集合，或对 `write` 做有执行验证的显式协议转换。

## A800 Full SFT Smoke

训练数据由 `examples/build_tmax_dataset.py` 从该正奖励 canonical 生成，训练 3 个 Call，holdout 选取不同 task group 的一个已有完整外部样本，仅作为 Trainer 的独立评估接口，不作为自产数据量。未使用 TB2.0/TB2.1。

配置：BF16 Full SFT，8K，学习率 `2e-6`，batch 1，梯度累积 4，Liger fused CE，单张 A800，`CUDA_VISIBLE_DEVICES=9`，`warmup_ratio=0`（1-step smoke 必须避免唯一优化步学习率为 0）。为避免单步 smoke 在满盘时保存中间 optimizer 快照，本次仅在远程临时训练副本把 `save_strategy` 设为 `no`；模型仍由原 Trainer 的 `save_model()` 保存，并通过原脚本的 reload gate 验证。

结果证据：`runtime-evidence/openharness-positive-sft-20261014/a800-tools-forwarding/`。远程 Checkpoint：

```text
/home/chenkeyi/openharness-sft-train-tools-20261014010214/runs/openharness-positive-tools-1step-r4/final
```

模型权重 `model.safetensors` 大小 `3,763,692,048` bytes，SHA-256 `a2b787786df29c33ffd0596aa138aaf6251f65a96d3afff514613c2d08b815ef`。Checkpoint 的 `missing_keys`、`unexpected_keys`、`mismatched_keys` 和 `error_msgs` 均为空，重载后 tensor 完全相等。新的 pretokenized train parquet SHA-256 为 `4ad46bb44cdcf69a9128abc1de9334852216f3978a230985e24f8123b65390fa`。

| 指标 | 训练前 | 训练后 |
|---|---:|---:|
| 独立 holdout loss | `0.5935968` | `0.5841535` |
| 训练样本 loss | `1.1504825` | `0.7804408` |

Optimizer step 为 `1`，train loss `0.8751935`，梯度全部有限；抽查参数发生更新（layer 0 down projection 441 个元素变化）。峰值显存 `14.0377 GiB`，训练耗时 `2.68 s`（不含模型加载和最终保存）。这只是过拟合式数据链路 smoke，holdout 仅一条且来自外部数据，不能用于宣称泛化改善。

### 原始批量自产轨迹 1-epoch smoke（已废弃）

在独立临时 Trainer 副本 `/tmp/openharness-sft-train-v2` 中，使用原始 5 个训练组
和 1 个保留组完成 1 epoch、6 optimizer steps：BF16 Full SFT、8K、学习率 `2e-6`、
batch 1、gradient accumulation 4、单张 A800 `CUDA_VISIBLE_DEVICES=9`。结果如下：

| 指标 | 训练前 | 训练后 |
|---|---:|---:|
| 训练 split loss | `0.9301561` | `0.7120952` |
| 保留组 holdout loss | `1.1304764` | `0.8732879` |

训练耗时 `27.64 s`，峰值显存 `18.3046 GiB`，实际处理上下文 `22928` tokens、监督
`1422` tokens；梯度有限且非零，参数发生更新，Checkpoint reload 的 320 个 tensor
完全一致。持久化 Checkpoint：
`aibox-167:/home/chenkeyi/openharness-sft-batch-v2-20261014/runs/batch-v2-1epoch-r2/final`，
`model.safetensors` SHA-256 为
`91333edd4e8e0dd506653534158592252c7fd086941f0eb5bd4564a317b9020d`。

这次结果**作废**：训练 split 包含后来发现的 `hello-user` Terminal-Bench canary，
不能作为无污染 SFT 结果或 checkpoint 推荐依据。holdout 也只是事后选出的接口验证组，
不代表泛化能力。

### 清洗后自产轨迹 1-epoch Full SFT（当前有效）

从 `canonical_positive_batch_clean_v1.jsonl` 中排除 `hello-user` 后，在独立临时 Trainer
副本 `/tmp/openharness-sft-clean-train-v1` 使用 4 个训练组和 1 个 holdout 组完成 1
epoch、5 optimizer steps。配置仍为 BF16 Full SFT、8K、学习率 `2e-6`、batch 1、梯度
累积 4、单张 A800（`CUDA_VISIBLE_DEVICES=9`）。

| 指标 | 训练前 | 训练后 |
|---|---:|---:|
| 训练 split loss | `0.9384218` | `0.7041373` |
| 独立 holdout loss | `1.1304764` | `0.8820326` |

实际处理上下文 `19077` tokens、监督 `1101` tokens；训练耗时 `25.68 s`，峰值显存
`18.3046 GiB`。320 个参数张量均有有限非零梯度，参数发生更新，checkpoint reload
通过精确 tensor 匹配。有效 checkpoint 位于：
`aibox-167:/home/chenkeyi/openharness-sft-clean-v1-20261014/final`，
`model.safetensors` SHA-256 为
`cea62b2925205b48a4a88247c3c5eff37d7a8c402fe3f08b4423c9dcb5706658`。
该结果仍是 5 个任务组的小样本 pipeline smoke，不代表泛化提升。

## 尚未完成

- 当前有 5 条经 canary 复核后有效的非 TB 教师轨迹，仍少于计划的 8～12 条；没有足够独立的 4～8 条 dev 集。
- 已审计但未冻结的 dev 候选及其原因记录在 `reports/dev_candidate_audit.json`；当前没有四条同时满足低成本、确定性 Verifier、无污染且可复现实跑的候选。
- 尚未进行 M0/M1 在独立开发任务上的真实 Agent Reward 对照；当前 A800 没有可用的 TMax 推理服务。
- 阻断证据：`/home/chenkeyi/tmax_sft/.venv` 没有 `vllm` 或 `sglang`，A800 当前也没有
  TMax 服务监听；RLBridge 的 Qwen3.5 serving recipe 还需要完整的 Qwen3.5-2B vision
  snapshot，而服务器根分区在本次训练后仅余约 `2.7G`，不能在本轮安全下载或部署。
- 已完成 4 个训练组的干净 1-epoch 小样本 smoke，但尚未执行 256～512 条轨迹的正式训练。
- 原始批量数据中的 `hello-user` 已确认污染并被排除；任何使用旧 `batch-v2-1epoch-r2` checkpoint 的结论均应撤回。
- Harbor Recorder 补丁已本地 commit `5715cc90`，没有推送或创建 PR。
- TMax `write` 工具在目标部署中的端到端执行兼容性仍需固定工具配置后验证；本次已证明教师原始工具定义可被 TMax Chat Template 正确编码，但没有把教师工具调用改写成 bash。

## 下一步

优先补足至少 4 条真正独立、可运行且通过 canary 审计的 dev 任务并固定清单；随后在 A800 部署与 M0
相同协议的 TMax 2B 服务，使用同一 Harbor 配置对 M0/M1 做并发 1 的逐任务 Reward
对照。最后再扩大教师任务池到 8～12 个独立组和 256～512 条合格 Call 样本；保持
现有 Harbor、Sandbox、Verifier 和清理链路不变。
