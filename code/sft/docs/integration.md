# TMax / Qwen 双 PR 集成

本分支从实际 main `076ab3fe0385fb13a2ea652aac3107961929044b` 派生，保留 PR3 `811eb55cbd3b4ba0e6897ae6c32cb45d85cd6076` 和 PR4 `c1ab50f5cb7eae50085416b98be46981d86dba5c` 的完整祖先关系。不修改两个源分支，不升级正在运行的旧队列，不启动正式训练。

## 冲突与归属

| 核对项 | 集成结果 |
|---|---|
| 文本冲突 | 两 PR 修改文件集合无交集，原生 Git merge 无冲突 |
| 删除根 Trainer/config | 原来是不可独立运行的外部 TMax stub；PR3 只加载自身 SHA 固定 sources，不引用被删文件 |
| 训练职责 | `studies/tmax32k` 保留 TMax 原生 Trainer；`sft/runtime` 为 Qwen LF；不重写或统一训练循环 |
| 数据合同 | 共享 `adapters` / canonical 文件合同；旧 TMax Tokenizer 不替代 Qwen 官方 Tokenizer |
| 依赖 | TMax Python≥3.12 / TF5.14，Qwen Python≥3.11 / TF5.8，vLLM 第三个环境；不合并 requirements |
| CI skip | stdlib contracts job 改用 Python3.12，避免新增 TMax 测试因解释器被静默跳过 |
| Recorder 生命周期 | 上游同时提供同步 close 和异步 create/aclose；两条真实契约测试共用固定 tree，未新增 adapter |
| 历史 wheel | TMax FAIR1/H0 固定轮子与当前 Qwen 采集身份分别保留；测试当前 reader 不授权升级历史 wheel |
| 运行管理 | TMax 原 runner 只管理自身研究，Qwen user Job 只管理自身训练；不互相调用，不共用输出目录或 GPU 锁命名 |
| 历史身份 | 8组训练、13组 NLL metadata 和原 Trainer/Collator/Serving SHA 不变；只在临时合成 scalar 上测试聚合分母 |
| 数据污染 | TMax 历史 TB2.1 同题适配性质保留；这些来源不能进入 Qwen 正式 M2，批准数仍为0 |
| 安装范围 | 根 wheel 打包 sft/adapters/templates；TMax study 与单独 vLLM 插件从审核后的完整 checkout 使用 |

## 独立环境与 CPU 验证

下面使用两个全新的、无 system-site-packages 的 venv；Python 3.12 或3.13。先安装 CPU Torch，再安装其余锁定依赖。DeepSpeed 在 CPU 测试中不编译 CUDA op，不等于 A800 环境构建通过。

```bash
git clone https://github.com/CoyeCHEN/openharness-sft.git clean-sft
cd clean-sft
git checkout <REVIEWED_INTEGRATION_COMMIT>
python3.12 -m venv /approved/tests/tmax-cpu
python3.12 -m venv /approved/tests/qwen-cpu
# 每个环境分别执行；使用官方 CPU wheel index 获取 Torch / torchvision。
<ENV_PYTHON> -m pip install torch==2.8.0+cpu --index-url https://download.pytorch.org/whl/cpu
# TMax：
/approved/tests/tmax-cpu/bin/pip install -r requirements/cpu-tmax.in -c requirements/cpu-tmax.lock
/approved/tests/tmax-cpu/bin/pip install --no-deps .
CUDA_VISIBLE_DEVICES='' TMAX_CPU_TESTS=1 TMAX_MODEL_PATH="$ORIGINAL_TMAX_TOKENIZER" /approved/tests/tmax-cpu/bin/python -m unittest \
  tests.test_adapters tests.test_batch_dataset tests.test_dataset tests.test_recorder_integrity \
  tests.test_security tests.test_tokenization tests.test_tmax_delivery tests.test_tmax_native_cpu tests.test_integration_contracts -v
# Qwen：CPU torchvision 必须与 CPU Torch 匹配，CUDA版不能混用。
/approved/tests/qwen-cpu/bin/pip install torchvision==0.23.0+cpu --index-url https://download.pytorch.org/whl/cpu
/approved/tests/qwen-cpu/bin/pip install torchaudio==2.8.0+cpu --index-url https://download.pytorch.org/whl/cpu
/approved/tests/qwen-cpu/bin/pip install setuptools wheel
DS_BUILD_OPS=0 /approved/tests/qwen-cpu/bin/pip install --no-build-isolation -r requirements/cpu-qwen.in -c requirements/cpu-qwen.lock
/approved/tests/qwen-cpu/bin/pip install --no-deps .
CUDA_VISIBLE_DEVICES='' QWEN35_MODEL_PATH="$QWEN_MODEL" \
  /approved/tests/qwen-cpu/bin/python -m unittest discover -s tests -v
/approved/tests/qwen-cpu/bin/python tests/check_native_deployment.py \
  --workspace "$CPU_TEST_WORKSPACE" --model "$QWEN_MODEL" --m1-manifest "$EXTERNAL_FROZEN_M1_MANIFEST"
/approved/tests/qwen-cpu/bin/python tests/remote_runtime_check.py --workspace "$CPU_TEST_WORKSPACE"
```

可选 `OPENHARNESS_SOURCE` / `TMAX_AUDIT_HARNESS` 仅指向独立的固定上游测试 checkout，运行两条 Recorder 契约测试；生产训练不导入上游源码。仓库外 wheel 安装必须从 checkout 外执行 CLI，不能依赖开发环境 PYTHONPATH。

2026-10-25 实测使用 Python3.13.16、两个新建 venv，`system-site-packages=false`。远端 PyPI 连接超时后，改用官方源取得并校验的 CPU wheel / wheelhouse 离线安装；LF wheel 来自固定 c683e59 源码，六个关键文件 SHA 与 GPU 环境相同。DeepSpeed 0.19.8 源包 SHA 校验后以 DS_BUILD_OPS=0 构建。没有修改旧环境、驱动或系统 Python。

| 实际检查 | 结果与范围 |
|---|---|
| TMax 完整 CPU suite | 55项，54通过/1个原有真实Trial可选项跳过；固定原始Tokenizer/Thinking/当前target mask、原生Collator、微型原生Trainer保存/恢复/继续更新均执行 |
| TMax 加强恢复检查 | 3项通过，逐张量比较恢复的Adam状态、Scheduler与权重；不重训8组或重算13组NLL |
| Qwen 完整 CPU suite | 94项，90通过/4跳过：原有真实Trial1项、仅在TMax环境执行的3项；10项真实Tokenizer黄金测试执行，无新增失败 |
| 当前 Recorder 合同 | 两种生命周期均用真实固定上游Recorder/exporter执行；没有生产Wheel升级 |
| 原生 LF 部署 | 三个正式配置读取通过；实际M1 5320/191；首/末行 input_ids/labels 与Collator逐Token一致；无CUDA初始化、无4B权重加载 |
| 独立安装 | sft从新venv的site-packages导入；sys.path不含RSI/runtime-evidence源码，数据与模型作为显式外部工件读取 |
| 依赖 | 两个实际环境分别55/121个distribution，uv pip check均无不一致；CPU完整约束另存cpu-*.lock |
| Serving插件 | 单独wheel安装、vLLM entrypoint函数加载及生产源码SHA一致；不把它称为真实vLLM GPU Serving验收 |
| GA4 profile | 已准备32条真实M1训练行、4条验证行、4rank×GA4×2updates的原生driver配置；未执行、未注册新队列 |

所有CPU结果均来自干净独立checkout和实际新依赖环境；不宣称CUDA Kernel、ZeRO-3 GPU更新或新服务器完整A800部署已通过。完整逐层故障边界仍见[可靠性矩阵](reliability.md)。

还修复了正式入口的真实启动缺陷：标准Warmup首步LR=0，原参数更新检查会误判失败。现在在原生on_step_begin捕获实际LR；零LR步记录真实Optimizer Step而不要求参数改变，非零LR无参数更新仍失败，整个调用没有实际参数更新也失败。真实CPU Trainer已验证首步零LR/第二步更新、两个参数组及负向检查。正式阶段warmup_ratio保持0.03，仅两步GPU canary显式设为0.0，使两步都能证明参数更新；配置差异写入canary plan。

## GPU / M2 与合并顺序

原20分钟 GPU monitor / 验证队列保持独占的旧身份。集成入口的 GA4 continuous 必须另有明确、有限的测试配置和独立输出，不能偷换旧 queue 指向；八卡被占时不另建抢卡队列。已通过128K容量不重跑，长目标第二步继续等待原队列。

当前 M2 来源仅发现旧 TB2.1 和集成 fixtures，均不满足正式数据要求；任务来源/Verifier/任务组批准及教师访问仍须具备，不能用测试目录生成正式样本。

推荐将本 Integration PR 作为包含两个 PR 的统一合并单元；它保留两边提交祖先及集成修正，合并后再关闭已被包含的 PR3/PR4。若必须逐个合并，则 PR3→PR4→集成修正；不要 squash 三份各自重复的实现，也不要自动合并。CI被账户计费阻断时明确记录 blocked，不能写通过。
