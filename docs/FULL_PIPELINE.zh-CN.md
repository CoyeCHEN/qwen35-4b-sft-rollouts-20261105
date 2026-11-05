# Qwen3.5-4B 实际全链路源码导航

本仓库对应已公开的 **54 条分阶段 Checkpoint 评测轨迹**。公开自有代码；OpenHarness 为私有依赖。这里是实际执行版本的源码快照和运维档案，不会启动任何训练、采集或评测。原有运行目录、模型和服务没有被修改。

## 版本及实验身份

- 学生：`Qwen/Qwen3.5-4B`，revision `851bf6e806efd8d0a36b00ddf55e13ccb7b8cd0a`。
- 新路线：原始 post-trained Qwen → CalibForge 416 个成功任务 M1 → TMax 356 个成功任务 M2。不要与旧 5320 条 M1、TB2.1 同题 M2 混淆。
- SFT Git 基线：`6f3cae79028b5c2d313a3cd35ee7e7473c9b2f42`；实际执行为 `source-r4` 文件快照。训练源码指纹 `293ba2a7dca8569bb39e11bc0137a0e1180a0391402f10d49ff5b4ad00ce6c93`。
- Harbor：`5ff23f631822aee52dd69febcbae279c5d777303`，与生产工件来源 `d195f4c693e5d13aef4b51f9e5d609031a6600f6` 同 tree，版本 `0.23.0+rsi.5`。没有用后续 main 替换历史执行版本。
- 本次公开源码不是 54 份轨迹对应全部实验均成功的证明；评分、Recorder 完整性和执行异常仍按原始记录区分。

## 各阶段代码

| 阶段 | 入口与源码 | 输入 / 输出 |
|---|---|---|
| 选题、任务身份及环境准备 | [teacher-collection](../code/teacher-collection/historical-scripts/)，`inventory_public_tasks.py`、`select_tmax500.py`、`prepare_tmax_tasks.py` | 官方任务、revision、任务组、去重清单、镜像准备；不把任务当成功轨迹 |
| DeepSeek 教师采集 | `run_collection_stream_r9.py` 及同目录冻结依赖、attempt/accounting/readiness 脚本 | Harbor 原生 Trial、Verifier、Recorder；凭据从环境读取 |
| Recorder 导出 | [teacher-exporter-r8.py](../code/data-processing/historical-assembly/teacher-exporter-r8.py)、`teacher_call_dispositions.py`、`native_export_cache_r8.py` | 真实 Provider Payload、SSE/原生响应核验、调用账本；Compaction 辅助调用不冒充 Agent Target |
| 成功语料及 Token 编码 | [data-processing](../code/data-processing/historical-assembly/)、[sft/qwen35.py](../code/sft/sft/qwen35.py)、[teacher_segments.py](../code/sft/sft/teacher_segments.py) | 任务级划分、128K 拒绝清单、input_ids/labels、Arrow；每个目标监督一次 |
| 训练 | [LF 入口](../code/sft/sft/runtime/lf_train.py)、[launch.py](../code/sft/sft/runtime/launch.py)、[jobs.py](../code/sft/sft/runtime/jobs.py) | 原生 LF/Transformers/DeepSpeed；远端用户 systemd、锁、Rank 身份、训练日志 |
| 保存、恢复、归档 | [checkpoint_archive.py](../code/sft/sft/runtime/checkpoint_archive.py)、[checkpoint_observer.py](../code/sft/sft/runtime/checkpoint_observer.py) | 原生 ZeRO 完整 Checkpoint；同进程继续训练、SSD 热保存、后台归档、完整恢复 |
| HF 导出与验收 | [hf_export.py](../code/sft/sft/runtime/hf_export.py)、`operations-historical/node18/snapshot-epoch-hf18-r2.py`、`final-hf-admission18-r2.py` | 完整 HF 权重身份、Tokenizer、加载/生成验证；ZeRO 分片不是 HF 模型 |
| Serving | [serving-installed-reference](../code/serving-installed-reference/)、[SGLang 差异](../code/patches-and-diffs/installed-serve/)、`operations-historical/node18/cold-native-serving18-r2.py` | 实际 SGLang 解析器/HTTP/模型代码、冷启动服务和模型身份；不含权重 |
| Harbor 评测 | [完整 Harbor 源码](../code/harbor-rsi/)、[冻结 Job 配置](../metadata/evaluation-configs/)、[历史评测脚本](../code/operations-historical/node18/formal-native-eval-r1/scripts/) | 原生环境/Trial/Verifier/结果回收。OpenHarness 通过已校验私有 Wheel 运行 |
| 总控、巡检与故障证据 | [operations-historical](../code/operations-historical/)；`run-native772-advance-r41-env-repair.py`、`read-only-monitor18-r36-current-node17-phase.py` 等 | 持久运行、真实进展、资源身份、阶段交接；未在本次重新部署或派发 |
| 轨迹分析与打包 | [trajectory-review](../code/trajectory-review/)、`forensics/viewer.js`、`build_report.py`、`package_54_zip.py` | 54 条冻结选择、离线 HTML、逐文件 SHA、ZIP、脱敏与导航校验 |

`historical-scripts`、`operations-historical` 保存确实存在的历史修订和辅助脚本，供追溯调用关系；编号较大不代表适用于每个历史 Trial。**不要自动选最高 r 编号执行，更不要对仍活动的工程批量执行这些脚本。** 实际 Job/config/source SHA 优先于文件名。

## 真正使用的训练配置

两阶段均为 128K、5 Epoch、LR `1e-5`、DP4 × MB1 × GA8，名义全局 Batch 32；末尾实际累积 6、全局 24。AdamW β=(0.9,0.999)、ε=1e-8、WD=0、clip=1、warmup=5%。Scheduler 为 **cosine_with_min_lr，min_lr_rate=0.1**，不是 cosine-to-zero。BF16 计算 + FP32 Master/Adam，ZeRO-3、Activation Checkpointing、FA2、Liger，冻结视觉及 projector，seed/data_seed=42，禁用 packing/neat_packing。

| 阶段 | 原成功任务 | train/validation 任务 | train/validation 编码行 | train/validation 监督 Tokens | 实际最终 Steps |
|---|---:|---:|---:|---:|---:|
| CF M1 | 416 | 374 / 42 | 1270 / 146 | 14,562,564 / 1,581,455 | 200 |
| TMax M2 | 356 | 325 / 31 | 792 / 86 | 7,815,211 / 856,073 | 125 |

30,193 个原 Agent Target 中，3,886 个超长 Target 被明确隔离；保留 26,307 个 Target，编码为 2,294 行。任务数、原始决策数、分段行数、Token 数和优化步数不能混为一谈。任务级 train/validation 隔离；同一 Target 不因历史重复监督。M2 加载 M1 最终 HF，重新创建本阶段 Optimizer/Scheduler。

精确 YAML、DeepSpeed、数据 Manifest、resolved config 和训练状态见 [metadata/training-identity](../metadata/training-identity/)。部分旧证据是既有脱敏副本，需结合文件指纹索引，不把脱敏字节冒充原始 SHA。

## 依赖和复现边界

训练环境：Torch 2.8.0、Transformers 5.8.0、LF 0.9.6.dev0（`c683e59edd8f893abc5e1403184a1d0644817d2a`）、Accelerate 1.11.0、DeepSpeed 0.19.8、FA2 2.8.3、FLA 0.5.2、Liger 0.8.4。Serving 环境：Torch 2.9.1、Transformers 5.3.0、SGLang 0.5.10 及 RSI reliability overlay。两个环境分开。

源码、依赖锁定、已安装模块快照和许可证均已保留。实际训练语料、模型权重、系统依赖缓存、SSH/API 凭据及私有 Harness 不在 Git 中；需要有权限的执行者另行提供。不能把公开源码宣称为无需这些工件的一键完整复现。

更多命令见 [运行手册](RUNBOOK.zh-CN.md)，私有依赖见 [PRIVATE_HARNESS_DEPENDENCY.md](PRIVATE_HARNESS_DEPENDENCY.md)。
