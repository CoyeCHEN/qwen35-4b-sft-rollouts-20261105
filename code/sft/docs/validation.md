# 本次实际验证记录（2026-10-24）

本记录只保存脱敏结论。完整日志、真实数据、模型和 Checkpoint 保留在既有远端运行目录，均未提交 Git。正式训练授权仍为 false。

| 检查 | 实际结果与边界 |
|---|---|
| 本地轻量 CPU 回归 | CONFIRMED：69 tests，62 执行通过、7 跳过；包含固定上游真实 Recorder/exporter 合成契约，不加载权重 |
| 既有 A800 隔离环境 CPU 回归 | CONFIRMED：79 tests，77 执行通过、2 跳过；10 项固定 Qwen Tokenizer 黄金测试、原生 CPU Trainer 同 PID save→step2、真实 tensor guard 和保存边界均执行 |
| 原生 Recorder/exporter | CONFIRMED：真实固定 Commit 的 Recorder 写入合成数据、实际 export、读取 payload；同 Session 新增闭合 call 后旧 export 被拒绝；没有教师 API 调用 |
| 三个正式 LF 配置 | CONFIRMED：64K / 128K / 96K 均由实际 LF get_train_args 读取；CPU 检查显式关闭 DeepSpeed，不声称该项执行了 GPU ZeRO-3 |
| 实际 M1 数据加载 | CONFIRMED：复用原 Arrow，5320 train / 191 validation；完整缓存 SHA 检查通过，无数据复制或重编码 |
| 实际 LF Collator | CONFIRMED：首/末训练行，原文本3240/5657 Tokens，实际输入3312/5728；原 input_ids、labels 逐 Token 相等，dummy/padding labels 全 mask；不是全量训练验证 |
| 模型/依赖 | CONFIRMED：固定官方两份权重流式 SHA；实际版本及六个 LF 关键源码 SHA；266 项已安装 base dependency requirements 无不一致 |
| wheel 独立安装 | CONFIRMED：源码外 /tmp 运行新 wheel；模板和空 M2 拒绝可用；没有 ML 依赖导入，不依赖 checkout 资源 |
| SSH 断连 / linger | CONFIRMED：独立远端用户服务在提交 SSH 结束后继续15秒并完成；当前用户 Linger=yes；新提交入口也检查 linger |
| 重复与真实终止 | CONFIRMED：相同 Job ID 拒绝；只对独立 Fake Job 执行 TERM/KILL，原 PID 身份消失，Restart=no |
| 原生 elastic 清理 | CONFIRMED：两个真实 CPU/Gloo Rank，Rank1 退出19，torchrun 返回1并清理 Rank0；双方 CUDA 均未初始化 |
| 存储/保存故障 | CONFIRMED：临时 fixture 的不完整 Checkpoint、复制失败、挂载身份不符、SHA损坏、归档发布后中断重试、轮换后 pin 恢复均通过；没有卸载共享盘、填满 SSD 或杀真实训练 |
| 新增恢复身份约束 | CONFIRMED：本阶段 marker 必须包含匹配的 stage/config SHA；配置变化、跨阶段目录拒绝恢复 |

远端最终 CPU suite / native preflight 的独立 systemd unit 均以 `Result=success, ExecMainStatus=0` 结束；已有 GPU watch timer 与 archive path 保持 active。测试遗留的 failed unit 是有意故障证据，不代表仍有存活 Rank。

## 没有完成或没有重跑的项目

- **UNVERIFIED**：迁移后的真实 GPU 同 Engine save→第二步更新；128K 长监督目标的恢复第二步。沿用既有后台队列，不另开重复 GPU 测试。
- **CONFIRMED（既有证据）**：4×A800 短序列、M1 实际长样本、128K 容量两次更新及跨进程恢复；迁移没有重复执行它们。128K 容量 reserved 约75.60GiB/卡，不代表正式 GA4 长期稳定性已证明。
- **UNVERIFIED**：生产 NCCL 死锁、GPU OOM/Xid/ECC、真实保存途中断电、Ceph 不可中断内核 I/O、全阶段恢复数据进度；参见[故障矩阵](reliability.md)。
- **CONFIRMED**：正式 M2 批准数据仍为0；采集/审核/转换入口具备，但缺合法独立任务池，未执行教师生成，不用评测轨迹替代。
- **UNVERIFIED**：全新服务器从零构建 CUDA kernel 依赖。现有可运行隔离环境已直接复用和检查，未重装。

目前不是“只等 GPU”：还缺正式 M2 独立成功数据。没有执行正式全量 M1/M2，没有修改或停止 SGLang，没有新增保活 CUDA 进程。
