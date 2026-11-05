# 数据与监督合同

输入不是字符串拼接后的“看起来像聊天”。`sft.qwen35` 使用固定官方 Tokenizer / Chat Template 产生真正的 input_ids，再精确构造 labels，并逐 Token 检查边界。M1 的所有 Assistant 块参与监督；M2 只监督本次实际 Assistant 目标。System、User、历史 Assistant（M2）和 Tool Observation 都为 `-100`。不预先 shift labels，交给原生 CausalLM / Liger loss。

Thinking 使用原始 `reasoning_content` 或原生 `thinking` block；不从正文猜测推理，不生成不存在的内容。独立 Thinking 字段与正文 Think 标记同时存在时拒绝歧义。工具 ID 在审计索引中验证和保存；名称/参数、正文、Thinking、消息结束标记由固定模板编码。所有源 payload 和 Recorder 保持不变。

## M1

固定 HF revision：`7d74fd38a3bc437bbd2c377bd8a1effba64d79ba`。官方路径为 `data/messages/train.parquet` 与 `data/messages/holdout.parquet`；SHA 及 134 条既有剔除记录位于 `sft/policies/m1-quality.json`，不含轨迹正文或 Token 数组。保留原划分，复用历史质量剔除，再隔离全部原 markup 警告；不修改源文本。保留至最后一条真实 Assistant，后续原始 Observation 留在源文件，不伪造最终回答。

```bash
# 可以用 HF CLI 在固定 revision 下载上述两个小型 Parquet；不要下载其他模型的预编码 Token 替代。
python -m sft --workspace "$SFT_WORKSPACE" prepare-m1 \
  --train /path/to/train.parquet --validation /path/to/holdout.parquet
```

单 worker、Parquet batch 8、Arrow writer batch 8，精确核对5320/191及原监督 Token 总量。不满足就失败，不换一套较小数据。任务组不得跨 train/validation。已知评测指令归一化哈希排除；公开数据的 opaque ID 使更广泛的语义同题关系仍不能被完全证明。

已有 M1 用 `adopt-m1` 复用原生 Arrow 数据与 Manifest，无需重新编码。`check` 和启动入口核验数据文件清单、大小与完整 SHA；缓存损坏、样本全 mask、长度错配都不能静默进入模型。

## 独立 M2 采集

必须先有获准的非评测任务池。没有来源时保留 `m2-approved-sources.json` 的空 entries，禁止用 TB2.1 或 smoke fixture 补数。任务必须记录原始来源，不能改名、改写官方评测题掩盖污染。

`scope.json` 的最小结构：

```json
{
  "kind": "approved_independent_tasks",
  "tasks": [
    {"task_id": "actual-harbor-task-name", "task_group_id": "original-task-family", "split": "train", "path": "/approved/tasks/task-a", "origin": "authored_non_evaluation_task"}
  ]
}
```

真实训练批准必须最终具有独立 train 和 validation 任务组；同一任务不同运行版本不能跨组。`task_id` 必须与 Harbor `result.task_name` 一致，工具不会自动改名迁就输入。

复用已通过预检的 **Harbor 原生 JobConfig**，其中环境、后端、预算和模型 descriptor 必须符合当前批准的任务范围。freeze 不执行任务或调用 API：

```bash
python -m sft --workspace "$SFT_WORKSPACE" freeze-collection \
  --scope scope.json --base-job approved-native-job.json \
  --wheel /path/to/exact-harness.whl \
  --teacher "$ACCEPTED_DEEPSEEK_MODEL_ID" --version-basis "$PROVIDER_VERSION_BASIS"
harbor run --config "$SFT_WORKSPACE/configs/teacher-job.json" --print-config
# 任务和资源已获准才运行，不在本次迁移/CI中执行：
harbor run --config "$SFT_WORKSPACE/configs/teacher-job.json"
```

使用已被 provider 接受的 `deepseek/<model-id>`，不能填猜测别名。provider 未暴露权重 revision 时，如实记录实际模型 ID、descriptor/查询证据及版本依据，不能伪造版本号。freeze 固定 Harness/Harbor Commit、wheel SHA、完整任务文件哈希、任务组/划分和 agent options；新 profile 为 `native-cli-v1`、Recorder 开启。凭据只使用 `${DEEPSEEK_API_KEY}` 环境变量引用，不写值。

在对应任务环境内，通过固定 Harness 的原生 Recorder export CLI 产生导出；保留原始 Recorder。不要用 Session 累积 history 重建 compaction 前的上下文。原生 `manifest.sessions[]` 的所有 Session 都必须有各自的原始 manifest/events 证据，导出 calls/payload/response/tool 必须与原始记录一致。

```bash
# 在安装了固定 Harness wheel 的环境中；output 必须是新目录。
open-harness-traces validate /path/to/trial/agent/recordings
open-harness-traces export /path/to/trial/agent/recordings --output /private/exports/TRIAL_ID
```

实际 Recorder 位置按 Trial 工件填写，不假设所有旧 Trial 都叫 recordings。validate 检查完整性，不替代 Harbor verifier 的成功结果。

## M2 审核与编码

候选文件为 `{"entries": [...]}`。每项包含：

| 字段 | 意义 |
|---|---|
| task_id / task_group_id / trial_id / split | 原始任务与 Harbor Trial 身份、固定划分 |
| origin | kind、原始 source_files 的 path/SHA；不得有 upstream_benchmark/evaluation_split |
| collection_manifest / collection_manifest_sha256 | freeze 产生的批准范围 |
| harbor_result / harbor_result_sha256 | 官方结果，要求 exact ID、无基础设施错误、有限 numeric reward=1 |
| installed_artifact / installed_artifact_sha256 | Trial 内 `agent/artifact.json`，实际 wheel 与 profile |
| rollout_export_dir / recorder_manifest_sha256 | 原生 export 目录与完整性证据 |
| raw_recorders | 数组，每项 path、manifest_sha256、events_sha256；原始目录必须属于实际 Trial |

```bash
python -m sft --workspace "$SFT_WORKSPACE" approve-m2 candidates.json
python -m sft --workspace "$SFT_WORKSPACE" prepare-m2 \
  "$SFT_WORKSPACE/manifests/m2-approved-sources.json" --length 131072
# 经真实技术失败审查允许回退，才另外生成：
python -m sft --workspace "$SFT_WORKSPACE" prepare-m2 \
  "$SFT_WORKSPACE/manifests/m2-approved-sources.json" --length 98304
```

审核要求真实 provider-payload fidelity、成功完整轨迹、实际教师模型、原始 Recorder 闭合及全部工具配对。正常闭合的工具错误输出可以成为 Observation；缺工具执行或孤立结果属于协议缺失。辅助 compaction 调用不成为 Agent 决策 target，但下一次 Agent 真正收到的压缩上下文保持原样。

M2 按完整决策拒绝超长样本，不截断。固定 LF collator 有66个 dummy-image token开销，预算为 cutoff-66，并由实际输入长度 guard兜底拒绝异常。Manifest 分别记录完整轨迹、任务组、决策、监督 Token 覆盖；编码/质量拒绝与长度拒绝分开，不能把一种覆盖率称作另一种。

每个保留行另有只含身份、哈希、loss范围和tool链接的审计索引。数据未全部完成并通过两组质量检查，不发布 eligible Manifest；旧数据、旧索引和旧输出均不覆盖。全量原始数据与日志留在 workspace，不提交 Git。
# Public Harbor task provenance

Public datasets keep `origin.kind=published_harbor_task`; they must never be
renamed to authored tasks. `freeze-collection` accepts a frozen
`approved_published_harbor_tasks` scope only after its status is `APPROVED`.
The scope records dataset, immutable revision, license, original source split,
instance ID, source task path, full source-file hashes, task group and the
separate SFT split. Its hashed isolation review must approve each exact source
identity against the retained evaluation sets, including Terminal-Bench 2.1.
A lexical screening report or a pending review cannot grant approval.

The public scope pins its own audited Harness/Harbor commits and wheel SHA;
it does not silently upgrade the historical authored-task collection contract
or the training dependency lock. `freeze-collection` writes the native Harbor
Job configuration but does not run it. Actual trial admission additionally
requires the installed wheel, successful native Verifier, normal Agent exit,
no primary/secondary/infrastructure errors, exact raw Recorder hashes, closed
run/call/tool records and genuine provider payloads. Native single-session
Recorders need no invented `integrity`/`sessions` export fields: their journal
and artifact integrity are checked directly by the existing reader.

These checks are implemented in `sft.published`, `sft.collection` and
`sft.sources`, with CPU regression tests in `tests.test_published_sources`.
Adding this source contract does not approve a dataset, freeze a train/validation
split, or enable a new formal training stage by itself.

After the frozen public scope and real successful native trials pass review,
`approve-calibforge candidates.json` validates source/Recorder/Reward evidence
and writes a separate `calibforge-approved-sources.json`. Both task-group splits
must contain verified success. `prepare-calibforge` consumes that approval and
the frozen tool contract:

```bash
python -m sft --workspace "$SFT_WORKSPACE" approve-calibforge candidates.json
python -m sft --workspace "$SFT_WORKSPACE" prepare-calibforge \
  "$SFT_WORKSPACE/manifests/calibforge-approved-sources.json" \
  --tool-contract /path/to/frozen-tool-contract.json
```

This produces one complete multi-turn sample per accepted trajectory, in frozen
approval order for each split; it never expands history into duplicated targets.
Each recorded decision must be an exact encoded prefix of the saved sample.
Compaction or rewritten history that breaks this property rejects the whole
trajectory. The pinned native LF text-only collator adds 66 masked multimodal
placeholder positions. Real text therefore has an explicit 131006-token budget
under the unchanged 131072 total limit, including native 8-position alignment.
Overflow rejects the trajectory; inputs and targets are never silently truncated.
The common Arrow cache and row identity manifest are reused by both A/B routes.
