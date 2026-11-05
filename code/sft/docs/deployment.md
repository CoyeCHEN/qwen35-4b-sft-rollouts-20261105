# 部署、观察、停止与恢复

CalibForge的两个独立阶段为`m3-a-128k`与`c1-b-128k`，继续使用下文同一个
`run`/`status`/`--resume`入口，不创建另一个Trainer或GPU调度队列。
它们的runtime设置`training_recipe=calibforge_appendix_e`，指向同一份
`manifests/calibforge-128k.json`和Arrow缓存。两个实际YAML只允许初始化权重和
输出目录不同，其余输入顺序与训练配置必须一致。初始化模型Manifest由
`initial_models_manifest`和对应SHA冻结，M3-A加载已验收M2最终HF，C1-B加载
固定官方M0；两者初始Optimizer/Scheduler均为NEW，同阶段恢复才传`--resume`。

`check`会分别报告这两个阶段。当前明确批准的前序范围为M0/M1/M2各自预先指定的
首轮89题，共267个唯一Trial；已完成的重复采样另存为补充，不从中挑选较好的Attempt。
`prior_campaign_report`及其SHA绑定已有总控产生的首轮合并报告，核对原始r1 Job、
逐任务UUID及Result SHA。缺失或未评分结果明确保留，不补零。只有在途Trial真正结束、
Controller结束且Campaign容器清理的实时证据齐全，才可释放明确归属本项目的Serving
unit；其他用户的分配保持原样。启动时四张授权GPU仍须立即确认无现存分配。

C1-B还要求M3-A完成原生10Epoch预算并通过最终HF加载/生成验收，不能从某个
早停Checkpoint开始第二路线。正常周期保存继续由原生Trainer/DeepSpeed完成，
不退出Engine；两阶段各自保留每一Epoch的完整Checkpoint。训练入口强制离线读取
已经冻结的本地模型与预编码缓存；分布式训练使用本机通信，不需要外部下载。
当前仍未产生的新配方GPU证据或未批准的数据不得因这些代码存在而记为READY。

数据批准并发布后，用`prepare-calibforge-canary`只准备CPU/Arrow输入；它选择整个
冻结数据中最长输入和最大监督量的真实样本，为原有三步GA32测试生成独立缓存。
诊断重复384次真实样本，不改正式数据及其顺序，也不把Padding冒充长输入。
已有有界入口`sft.runtime.canary`读取该配置，仍先核实预定267个首轮Trial全部结束、
实际GPU和项目锁，再执行step1/save/step2同Engine及checkpoint2→新进程step3。
新配方诊断额外记录每个真实microbatch的input/labels摘要，四Rank都须覆盖两个
数据极值；旧容量样本、变更后的labels或遗漏最大监督样本不能使当前Corpus通过。
正式训练不计算这些逐batch摘要。若真实Corpus最长样本短于128K，报告必须写实际
Token数，不能把配置上限131072宣称为已经执行了131072个非Padding位置。

现有20分钟GPU Timer可调用一次`sft.runtime.calibforge_advance`，不添加第二个Timer、
训练队列或重试循环。该入口依次核实前序封存及资源释放、冻结语料、GA32 Canary，
再调用原有`jobs.submit`启动M3-A，验收最终HF，随后启动C1-B并验收HF。原Job失败或
UNKNOWN时只报告，禁止自动重跑；空标记不代表HF验收。它输出固定89题×1次的评测
交接清单，实际Harbor部署/派发仍由现有远端评测控制端接收。当前部署使用已有密钥
认证远端SSH ControlMaster；临时本地Agent销毁后，两机原生连接仍独立工作。既有
Harbor Timer交换封存报告与HF身份，核实真正Serving身份后冷切换原有评测服务，
继续原生Job。未运行新模型时只称CPU接线通过，不能声称实际GPU/评测已验收。
连接丢失时不重新认证或重复提交，先记录UNKNOWN；不因此停止健康训练。

这些命令面向获得授权的 Linux / A800 主机。训练源码、虚拟环境、运行数据分开；模型与数据不进入 Git。当前已有服务器继续使用既有环境和共享模型，不用本说明重装它们。下面的正式启动命令仅在 Readiness 全部通过、且用户明确批准对应阶段后执行。

## 新服务器安装

```bash
git clone https://github.com/CoyeCHEN/openharness-sft.git
cd openharness-sft
# 使用经审查的本次 PR Commit，部署后不在运行中的 checkout 上改代码。
git checkout <REVIEWED_SFT_COMMIT>
python3.11 -m venv /path/to/isolated-sft-env
source /path/to/isolated-sft-env/bin/activate
python -m pip install torch==2.8.0 --index-url https://download.pytorch.org/whl/cu128
python -m pip install -r requirements/train-cu128.in -c requirements/train-cu128.lock
python -m pip install --no-deps .
```

FlashAttention / causal-conv1d 的二进制必须匹配 Torch 2.8、CUDA 12.8、Python ABI 和 C++11 ABI；若无匹配官方 wheel，需要已有 CUDA build toolkit，单线程编译并参考官方安装方法。不要修改驱动、系统 Python 或为了安装而更换已冻结版本。`train-cu128.lock` 记录实际运行环境的精确版本；新服务器从零安装的耗时和二进制构建本轮未实测。已有环境的导入、版本、原生 API 和六个 LF 关键源码 SHA 已核验。

使用固定 revision 获取模型，随后由 `verify-model` 验证官方两份权重 SHA。当前 `.17` 直接指向已有共享模型，不再下载副本。

管理员应只提供个人子目录权限；普通用户先验证写入、rename、fsync、读取和删除自身测试文件。热存储必须是获准的 SSD，归档路径为获准共享存储。用户 manager 的 linger 必须为 yes：

```bash
loginctl show-user "$USER" -p Linger
# 尚未启用时由主机管理员处理；不安装系统级训练服务。
```

## 初始化并复用数据

```bash
export SFT_WORKSPACE=/ssd/<user>/openharness-sft/workspace
export SFT_HOT=/ssd/<user>/openharness-sft/hot
export SFT_ARCHIVE=/data/<user>/openharness-sft/archive
export QWEN_MODEL=/path/to/pinned/Qwen3.5-4B
nvidia-smi --query-gpu=index,uuid,memory.used,memory.total --format=csv
# 只填写负责人授权的 GPU UUID，不能因 utilization=0 就认为得到使用权。
export AUTHORIZED_GPU_UUIDS=GPU-uuid0,GPU-uuid1,GPU-uuid2,GPU-uuid3

python -m sft --workspace "$SFT_WORKSPACE" init \
  --model "$QWEN_MODEL" --hot "$SFT_HOT" --archive "$SFT_ARCHIVE" \
  --gpu-uuids "$AUTHORIZED_GPU_UUIDS"
python -m sft --workspace "$SFT_WORKSPACE" verify-model
python -m sft --workspace "$SFT_WORKSPACE" adopt-m1 /path/to/existing/manifests/m1-64k.json
python -m sft --workspace "$SFT_WORKSPACE" evidence --source /path/to/existing/preflight
python -m sft --workspace "$SFT_WORKSPACE" check
```

`adopt-m1` 检查已冻结数据的完整文件清单/SHA、模型/模板、5320/191 划分，不复制 Arrow 文件，不重算 Token。新服务器没有旧数据时按 [数据合同](data.md) 重建。首次 `verify-model` 流式校验约 9.3GB 权重，后续检查使用已验证文件的大小/mtime；不是把整模型载入内存。

`evidence` 只读取既有 rank 证据，不执行训练。原队列补完 continuous / 长目标恢复后，重新执行 `check` 即可读取最新记录。96K 需要另外存在真实 128K 失败审查和已通过的 96K 证据。M2 数据未准备时会明确保持 false。

## 用户级服务

```bash
python -m sft --workspace "$SFT_WORKSPACE" install-archive
python -m sft --workspace "$SFT_WORKSPACE" install-monitor
python -m sft --workspace "$SFT_WORKSPACE" monitor
```

初始化的 `configs/runtime.json` 包含独立 `service_prefix`；归档服务名在 `configs/checkpoint-storage.json`。每个 workspace 的 unit 名不同，不覆盖原有服务。监控每20分钟采样，连续两次跨度至少1195秒、没有现存进程、剩余显存至少98%、utilization为0且UUID获准才标记稳定空闲；启动训练时仍立即复查。仓库内监控只观察，不自动启动正式训练或另建验证队列。日志2MiB×6轮转。

当前 `.17` 原有 `qwen35-gpu-watch.timer` 和既有验证队列继续运行，本次不对它们执行 install / stop / 切换。新的 CPU 故障测试只有独立 Fake Job，未派发额外 GPU 测试。

查看与停止模板：

```bash
systemctl --user list-timers '*gpu-monitor*'
systemctl --user status <service_prefix>-gpu-monitor.timer
tail -n 20 "$SFT_WORKSPACE/logs/gpu-monitor.log"
systemctl --user disable --now <service_prefix>-gpu-monitor.timer
systemctl --user enable --now <service_prefix>-gpu-monitor.timer
journalctl --user -u <archive_service> -n 30 --no-pager
ls "$SFT_HOT/archive-queue" "$SFT_HOT/archive-failed" "$SFT_HOT/archive-results"
```

## 正式阶段与恢复

只有拿到对应阶段的明确启动授权，并且 `check` 已显示该阶段 ready，才在 workspace 的 `configs/runtime.json` 设置 `formal_training_authorized=true`、`formal_authorized_stage="m1-64k"`。默认 false 不自动改变。随后只提交一次：

```bash
python -m sft --workspace "$SFT_WORKSPACE" run --stage m1-64k --gpus 0,1,2,3
```

返回唯一 `job_id` 和 systemd `unit`。可以立即断开 SSH；远端继续运行。不要因为本地终端断开而重发一次。观察、正常停止：

```bash
python -m sft --workspace "$SFT_WORKSPACE" status JOB_ID
tail -f "$SFT_WORKSPACE/jobs/JOB_ID/training.log"
tail -n 5 "$SFT_WORKSPACE/jobs/JOB_ID/gpu-samples.jsonl"
python -m sft --workspace "$SFT_WORKSPACE" stop JOB_ID
```

停止不承诺在信号到达时再保存一次。恢复只能选最后一个含 `CHECKPOINT_COMPLETE.json` 的完整本阶段检查点。确认回滚位置和未保存的计算损失后，以**新 Job ID**显式提交一次：

```bash
python -m sft --workspace "$SFT_WORKSPACE" run --stage m1-64k --gpus 0,1,2,3 \
  --resume "$SFT_HOT/runs/m1-64k/checkpoint-N"
```

不得从 `checkpoint-N/global_stepN` 分片子目录启动，不能把它当作 HF 最终模型。配置 SHA、阶段身份、所有 rank 状态/完整标记不符会拒绝恢复。机器重启后检查 boot ID / unit 状态 / 最后完整检查点；没有自动 Restart 或自动选点，不会悄悄重做已提交阶段。

从共享归档恢复到一个**不存在**的新目录：

```bash
python -m sft --workspace "$SFT_WORKSPACE" restore \
  --archive "$SFT_ARCHIVE/checkpoints/ORIGINAL_JOB_ID/checkpoint-N" \
  --destination "$SFT_HOT/runs/m1-64k/checkpoint-N"
```

先全 SHA 核验、临时目录复制、再次校验，再原子发布；不覆盖既有目的目录。归档失败项保留 pin 和原生检查点，修复真实原因后人工处理，不通过删除旧检查点腾空间。

M1 真正完成、正式 M2 独立数据及128K验收通过后，重新 `check` 并经明确 M2 授权，将授权阶段设为 `m2-128k`，再提交：

```bash
python -m sft --workspace "$SFT_WORKSPACE" run --stage m2-128k --gpus 0,1,2,3
```

M2 自动读取本 workspace 的 M1 最终权重，**不传 M1 的 `--resume`**。只有 M2 自身中断才使用 `--resume "$SFT_HOT/runs/m2-128k/checkpoint-N"`。96K 使用独立配置/数据/输出目录和明确失败审查；不会静默降到64K或32K。

## 独立测试

```bash
python -m unittest discover -s tests -v
QWEN35_MODEL_PATH="$QWEN_MODEL" python -m unittest tests.test_qwen35_codec -v
OPENHARNESS_SOURCE=/path/to/exact/audited/checkout python -m unittest tests.test_upstream_contract -v
# 只在专门测试 workspace 上运行 CPU systemd / 两个 Gloo Rank 故障 canary。
python tests/remote_runtime_check.py --workspace "$TEST_WORKSPACE"
```

CPU canary 不分配 GPU。生产 GPU OOM、NCCL 死锁、Xid/ECC、真实128K持续训练故障注入未执行；不得拿 CPU 测试替代对应验收。
