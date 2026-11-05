# 获取、检查和运行入口

这是历史执行链路的源码交付，不是重新运行历史任务的指令。已完成的训练与评测不应重复派发。历史绝对路径保留用于溯源；在新机器上必须建立自己的独立 workspace、输出目录、GPU 授权及工件清单。

## 公开代码的离线检查

```bash
git clone https://github.com/CoyeCHEN/qwen35-4b-sft-rollouts-20261105.git
cd qwen35-4b-sft-rollouts-20261105
python3 scripts/verify_source.py
python3 -m venv .venv-base
.venv-base/bin/python -m pip install -e ./code/sft
.venv-base/bin/python -m sft --workspace "$PWD/workspace-inspection" --help
```

基本 CLI 只需 Python/PyYAML；训练、真实 Tokenizer 测试另需完整训练环境。源码校验不读取密钥、不访问模型、不分配 CUDA。

## 依赖安装与角色分工

- 训练：`code/sft/requirements/train-cu128.in`、对应 `.lock` 和 `code/sft/pyproject.toml`。锁定 LF commit，不用最新 main。
- Serving：`metadata/VERSION_SETS.json` 中独立 Serving 环境；`code/serving-installed-reference` 与 `code/patches-and-diffs/installed-serve` 是实际模块和差异，不能把训练 Transformers 5.8.0 覆盖到 Serving 5.3.0。
- Harbor：`python -m pip install ./code/harbor-rsi`，原生 CLI 的 JobConfig 与 `metadata/evaluation-configs` 对照；不自建第二套评测 Runner。
- OpenHarness：需授权取得 [私有依赖](PRIVATE_HARNESS_DEPENDENCY.md)，校验 SHA 后安装。公开 Git 不提供该 Wheel。
- 真实任务环境、Docker 镜像、模型权重和 772 任务监督数据从有权限的原工件目录取得；本仓库只提供身份/索引及处理代码。不能从 Release 的学生失败轨迹构造教师成功数据。

## 教师与数据处理入口

1. `code/teacher-collection/historical-scripts/inventory_public_tasks.py`、`select_tmax500.py` 等保存实际选题/去重/环境准备逻辑。
2. `run_collection_stream_r9.py` 及同目录依赖保留原生 Harbor 连续调度与计费/尝试账本。参数在 `metadata/teacher-collection`。这些脚本绑定历史 Manifest 和 host；没有授权凭据或准备证据会明确失败。
3. 原始 Recorder → `code/data-processing/historical-assembly/teacher-exporter-r8.py`：使用真实 Payload，输出调用级导出和来源 SHA；原生响应与 SSE 不一致拒绝。
4. 导出 → `assemble_primary_native_cache_nfc17_r372.py` / `assemble_final_corpus_nfc17_r374.py`；接口可用 `--help` 检查。最后冻结和原生 Loader 验收对应 `code/operations-historical/node18/freeze-final772-native-r3.py`。
5. `prepare-formal772-native-r1.py` 建立实际两阶段配置和数据 Manifest；`sft.public_corpus`、`sft.teacher_segments`、`sft.qwen35` 负责可测试转换，不用普通字符串拼接补造历史。

## 原服务器上的实际训练入口（历史命令，勿重复已完成 Run）

历史训练 Python、workspace 和完整配置分别是：

```bash
PY=/ssd/chenkeyi/qwen35-sft-772-20261101/env/train-r1/bin/python
SRC=/ssd/chenkeyi/qwen35-sft-772-20261101/new-sft/source-r4/repository
W=/ssd/chenkeyi/qwen35-sft-772-20261101/new-sft/workspace
cd "$SRC"
"$PY" -m sft --workspace "$W" status new772-new-cf416-m1
"$PY" -m sft --workspace "$W" status new772-new-cf416-tmax356-m2
```

原生提交语法（新复现实验须替换为新 workspace/Run ID；禁止对本历史输出重跑）：

```bash
"$PY" -m sft --workspace "$W" run --stage new-cf416-m1 --gpus 0,1,2,3 --job-id replay-cf-m1-UNIQUE
"$PY" -m sft --workspace "$W" run --stage new-cf416-tmax356-m2 --gpus 0,1,2,3 --job-id replay-tmax-m2-UNIQUE
```

入口会检查显式阶段授权、完整数据 SHA、模型身份、实际 GPU UUID/进程、磁盘和项目锁；`runtime.json` 是历史授权证据，不是给任何机器的资源授权。提交后使用远端用户 systemd，与本地 SSH 生命周期分离；不能复制旧锁/状态文件冒充新 Job。

## Checkpoint、Resume、HF 导出

- 同阶段恢复：`sft ... run --stage <同阶段> --resume <明确的完整 checkpoint-N> --job-id <新恢复 Job ID>`；checkpoint 必须属于该阶段输出且身份一致，恢复原生模型、Adam、Scheduler、RNG/Trainer 状态。不存在自动选择不明 `latest`。
- 跨阶段：M2 的 `model_name_or_path` 指向 M1 最终 HF；不设置 M1 的 `resume_from_checkpoint`，新建优化器和调度器。
- LF 最终原生保存产生 HF 权重；`sft.runtime.hf_export` 负责校验/封存，不能把 ZeRO 中间分片称作 HF 导出。

原历史模型的只读身份/加载检查接口：

```bash
"$PY" -m sft.runtime.hf_export /ssd/chenkeyi/qwen35-sft-772-20261101/runs/new-m1-cf416-128k-e5
"$PY" -m sft.runtime.hf_export /ssd/chenkeyi/qwen35-sft-772-20261101/runs/new-m2-tmax356-128k-e5
```

`--smoke` 会实际 CPU 加载/生成并写入验收文件，需充足内存和写入授权，不应在 6GB WSL 上执行。Epoch1/3 HF 导出实现见 `snapshot-epoch-hf18-r2.py`，只接受完整原生 Checkpoint。

## Serving、评测、巡检

- 冷加载入口：`code/operations-historical/node18/cold-native-serving18-r2.py` 及其后续已记录修订；参数来自真实模型 SHA 和冻结 Serving 命令。`metadata/training-identity/checks/M0_NEW11_NATIVE_SERVING_COMMAND_R2.json` 保存原命令。不要热切换模型后只看 ACK 就声称身份相同。
- HTTP、Thinking、工具 parser 的实际实现见 SGLang 快照及补丁。必须真实检验两轮工具交互、历史 Thinking、top_p 和输入 Token IDs。
- Harbor JobConfig、profile、Wheel6 合同见 `metadata/evaluation-configs`。以原 Job 为单位调用 Harbor 原生入口，保留官方 Task/Verifier/Reward，不自行复写结果。
- 监控、阶段推进、恢复和归档的自有脚本保存在 `operations-historical`；版本按冻结 Source SHA 对应，不按最高 r 编号猜测。只读监控失败不能杀死健康训练/Trial，不能在新机器盲目安装这些历史总控。
- 本次上传没有启动新的监控、训练、模型服务或评测，也没有触碰原总控。

## 查看这 54 条轨迹

原始完整包和轻量离线查看包在仓库 Release `v2026.11.05`。分片顺序及 SHA 见仓库根目录的 parts/release manifest。`code/trajectory-review/forensics` 提供实际生成页面、逐回合查看、原始证据读取和校验的 10 个文件；其 SHA 与 `metadata/VIEWER_SOURCE_PROVENANCE.json` 一致。分析包有额外对照记录，不应把其全部页面计为这 54 条 SFT 轨迹。

## 许可证与公开范围

Harbor 保留 Apache-2.0；公开上游模块与 Tokenizer 保留各自来源/许可证。自有工程原先未声明统一开源许可证，本次公开不擅自替作者追加一个覆盖所有第三方文件的总许可证。私有 Harness 的授权与公开代码彼此独立。
