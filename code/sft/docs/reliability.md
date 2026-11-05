# 持续训练可靠性审计

`CONFIRMED` 表示实际执行或确切源码证据；`INFERRED` 表示从固定实现推断；`UNVERIFIED` 表示尚无所需现场验证。CPU 证明不升级成 GPU 证明，静态配置不升级成训练通过。

调用链为 systemd 用户服务 → 单次 torchrun → 原生 distributed init / LF Trainer → DataLoader → 模型 / backward / optimizer → evaluation → 原生完整 ZeRO-3 checkpoint → CPU 归档 → 显式 resume → 原生及 cgroup cleanup。仓库没有替代训练循环。

## 已定位并修复

1. 历史 GPU 释放由有界测试的 `--stop-after-step 1` 主动触发；原生 Trainer 保存本身没有退出循环。生产 driver 已去掉该测试参数和 max_steps 入口，旧恢复测试队列独立保留。
2. Rank0 保存前 `stat/statvfs` 抛错时，旧观测包装可能在广播前退出，使其他 Rank 等待 collective。现在把该错误广播给所有 Rank 后一致失败；CPU 故障测试确认广播发生且没有进入原生保存。
3. systemd-run 应答丢失并不证明作业没启动。提交错误写独立文件，不覆盖已接受作业的 running/completed Manifest；相同 Job ID 永久拒绝重复提交，状态由实际 unit 与进程身份观察。
4. 完成归档发布后、队列清理前被中断，现在可验证已发布 SHA 并完成幂等清理，不重新复制或动原检查点。
5. 归档挂载身份变化时拒绝落到挂载点下层文件系统；损坏/失败队列移到 failed，保留 pin 与最后本地完整检查点。
6. Recorder reader 返回值和 `sessions[]` 结构已统一；不能仅凭相同 Session ID 把旧 export 与新 Recorder 相连，现核对实际 call/payload/response/tool 内容。

## 故障矩阵

| 层/触发条件 | 后果 | 当前保护 | 缺口及证据 |
|---|---|---|---|
| SSH/Windows/WSL/Codex 关闭 | 交互子进程可能收到HUP | user service + linger，manager作为父进程，无本地租约 | CONFIRMED：SSH断开后独立CPU Job继续15秒；既有30秒探针也通过 |
| linger未启用 | 最后会话结束后用户manager可停止 | 提交前检查 Linger=yes，拒绝不具备持续运行条件的主机 | CONFIRMED：缺linger guard；当前主机yes；未修改系统服务 |
| systemd主进程正常结束 | 子进程残留风险 | Type=exec、KillMode=control-group、Restart=no | CONFIRMED：CPU probe完成、原PID不再匹配；GPU最终释放待现场 |
| SIGTERM | 当前未保存步骤丢失 | 原生torchrun信号传播、所属cgroup清理 | CONFIRMED：只停止独立CPU Fake Job，进程消失；不承诺信号时新保存 |
| SIGHUP | torchrun可转为终止 | SSH不连接训练TTY；elastic注册HUP处理 | CONFIRMED源码；未对GPU进程注入HUP |
| SIGKILL/用户scope OOM | 无机会保存新状态 | OOMPolicy=stop / cgroup清理，保留最后完整CP | CONFIRMED：只对Fake Job主进程KILL，原身份消失；真实GPU OOM未注入 |
| 某Rank异常退出 | 其他Rank可能挂住 | torchrun max-restarts=0，elastic终止同组剩余Rank | CONFIRMED：两Rank CPU/Gloo中Rank1退出19，Rank0被清理；NCCL故障仍UNVERIFIED |
| 重复提交 | 重复更新或抢卡 | Job目录原子创建、worker已接受状态拒绝、阶段/项目flock | CONFIRMED：真实重复Job拒绝，mock仅提交一次 |
| 陈旧锁文件/PID复用 | 误判存活或杀错进程 | flock依据内核锁，PID+startticks+boot ID；不凭PID kill | CONFIRMED：失效文件锁不阻塞，活锁拒绝；PID identity变化测试 |
| 提交应答超时 | 把已运行Job当失联重发 | 独立submission-error、保留worker Manifest、禁止自动重试 | CONFIRMED：模拟已接受后应答丢失，running不被覆盖 |
| 主机重启 | transient unit消失，旧PID可被复用 | 观察boot ID和unit，人工选择最后CP恢复 | INFERRED：身份检查；未重启共享服务器 |
| 用户服务异常停止 | Rank被结束、资源释放 | cgroup包含launcher/torchrun/所有rank；不依赖本地控制器 | CONFIRMED CPU进程组；GPU清理未另测 |
| CUDA OOM | 更新或保存失败 | micro1/GC/ZeRO3/FA2/Liger；失败退出保留证据，不自动降长或重试 | 既有128K容量通过，无本轮GPU OOM；真实OOM路径UNVERIFIED |
| 128K临时峰值/碎片化 | 接近设备上限，偶发OOM | 原生kernel，记录逐rankallocated/reserved与逐GPU采样 | 既有容量reserved75.60GiB、长目标首步76.47GiB；长期/GA4/真实M2未证明 |
| ZeRO all-gather/reduce-scatter | rank失步或collective超时 | 固定DS/TF/LF；native barriers；所有rank保存 | 既有四Rank更新/恢复；故障注入仅CPU |
| NCCL collective timeout | 训练失败并终止进程 | 沿用ddp_timeout=1800，未无限放大 | CONFIRMED：TF实参传到Accelerate init PG；真实死锁未注入 |
| NCCL watchdog心跳停止 | monitor终止进程 | 保留Torch2.8默认watchdog/monitor，不关闭保护 | 官方v2.8源码默认monitor=true、heartbeat480秒、async error handling=3；未人为续命 |
| 长时间正常128K计算 | 容易与心跳超时混淆 | 心跳监控的是watchdog线程，不是主训练step时间 | INFERRED源码；不能靠单次util=0或固定step时限断言死锁 |
| GPU Xid/ECC/驱动重置 | CUDA context退出或不可用 | 保存日志；正常错误传播清理；最后CP恢复 | 当前NVML八卡volatile uncorrected ECC=0；没有注入故障，不证明无Xid |
| GPU index重排 | 跑到错误卡 | 授权按UUID核对，CUDA_VISIBLE_DEVICES使用核验的UUID | CONFIRMED代码/索引映射测试；未重置硬件 |
| 其他容器占卡 | 无法加载或显存竞争 | 检查compute进程、显存、UUID；启动前复查 | CONFIRMED：root SGLang持有八卡时拒绝；无法与root实现原子预约 |
| 保存时utilization=0 | 误认为释放GPU | 观察PID/上下文/真实allocation，不用util单值裁定 | GPU保存前中后新证据待原continuous队列；CPU同PID已测 |
| DataLoader卡死 | step长期不前进 | 固定num_workers=0，不引入多进程worker | 无worker退出/队列死锁；底层不可中断I/O仍UNVERIFIED |
| 缓存文件损坏 | 错样本或反序列化失败 | 启动前完整清单/大小/SHA，拒绝异常 | CONFIRMED：真实文件同尺寸改字节被拒绝 |
| DataLoader读取错误 | 当前step失败 | 原生异常向外传播，不修补/跳过坏batch | CONFIRMED：真实CPU DataLoader抛OSError，未吞异常 |
| 超长输入 | target或Observation被截断 | 离线整条拒绝；模型前长度guard；没有truncate | CONFIRMED：真实Tokenizer>64K样本拒绝；128K训练未重跑 |
| Thinking/role/模板损坏 | 错监督、上下文改变 | 固定模板SHA、native IDs一致、配对、历史Think投影检查 | CONFIRMED：10项真实Tokenizer黄金测试 |
| labels全mask | 无效loss/NaN | 准备统计、数据Manifest、模型前真实tensor guard | CONFIRMED：真实CPU张量与Manifest拒绝 |
| NaN/Inf loss或梯度 | 不可恢复更新 | callback检查loss/grad_norm及语言梯度有限性，不自动继续 | 原检查已用于既有GPU；本轮未向GPU注入NaN |
| 合法Warmup首步LR=0 | 将参数未变误报为失败并退出 | 原生step begin采集LR；零LR步正常记账，非零LR无更新及整次无更新仍拒绝 | CONFIRMED：真实CPU Trainer首步全参数组LR0、第二步参数改变；非零LR无更新负例；正式warmup不改 |
| Optimizer/master状态异常 | resume语义不一致 | FP32 master/Adam抽样指纹、Scheduler/RNG原生恢复观测 | 既有四Rank恢复；当前迁移GPU入口仍UNVERIFIED |
| 步骤完成、日志未刷盘 | 误判进度 | 重要step/save/end事件flush+fsync | CONFIRMED代码；日志不能代替完整CP的恢复承诺 |
| SSD空间不足 | checkpoint不完整 | 新正式启动256GiB、每次保存前96GiB；错误广播 | CPU故障路径；未填满生产SSD |
| Inode/配额耗尽 | write/mkdir失败 | 原生保存错误向外、已有完整CP保留；归档错误单独隔离 | 未耗尽inode/配额；free bytes不等于配额保证 |
| 热盘/共享盘挂载丢失 | 写入错误下层目录或阻塞 | 记录st_dev并检查；归档失败保留本地pin | CONFIRMED：mount identity不符拒绝；未unmount共享盘 |
| Ceph临时不可用 | 归档停顿/失败 | CPU服务隔离、rsync timeout、服务时限、failed队列 | CONFIRMED：模拟I/O失败保留原件/pin；真实Ceph中断未注入 |
| Ceph永久D-state | SIGKILL也无法立即回收线程 | 不在训练同步路径归档；原生保存用本地SSD | UNVERIFIED：Linux不可中断内核I/O不能保证立刻结束，需要存储负责人处理 |
| 保存中进程失败 | 分片或marker不全 | 所有native callbacks结束、barrier、fsync后才标完整 | CONFIRMED：未完成fixture拒绝恢复；GPU中途杀保存未执行 |
| ZeRO分片缺失/step不齐 | 非完整恢复点 | 四rank文件、latest/global_step、Trainer state和完整标记检查 | CONFIRMED：缺rank状态拒绝；完整56.1GiB旧CP备份/CPU恢复已完成 |
| 归档时CP被轮换 | 复制源消失 | 已关闭文件同卷硬链接pin，成功后只解除pin | CONFIRMED：删除临时fixture原目录后仍完整归档/恢复；不删除真实旧CP |
| SHA不一致 | 归档不可恢复 | 源/目的逐文件SHA、临时目录、完成标记、原子rename | CONFIRMED：改字节后verify拒绝；真实旧CP全量校验通过 |
| 发布完成后worker崩溃 | 重复归档/清理失败 | 已发布key与SHA核验后幂等确认，不重复制 | CONFIRMED：已删除pin情况下重新处理成功，禁止copy的测试通过 |
| 原生保存性能停顿 | GPU暂时无计算 | 同Engine同步native save；分阶段采样与计时，归档在CPU后台 | 新SSD GPU保存提速未测；不得把46秒归档当成87.87秒native save优化值 |
| M1→M2误恢复旧优化器 | 阶段目标与LR日程错误 | M2只读M1最终HF导出，新Trainer/optimizer；禁止跨stage resume | CONFIRMED配置/入口；正式M2数据仍0 |
| 同阶段恢复数据位置/RNG/Scheduler偏移 | 重复/跳样本，训练轨迹改变 | 原生完整Resume，固定seed/data_seed，ignore_data_skip不改 | 既有GPU完整Resume已证明；正式全阶段/故障边界未验证 |
| 重启后自动重复已完成步骤 | 重复优化或新一轮SFT | Restart=no、无自动checkpoint选择、同Job拒绝复用 | CONFIRMED：不自动replay；人工从旧CP回滚会损失CP后的未提交计算，必须明示 |

## 性能与现场边界

既有存储验证：56.1GiB native checkpoint 归档复制46.0秒，全SHA153.3秒；独立恢复总266.0秒，其中复制69.3秒。1GiB样本复制到Ceph，两路约688MiB/s、单路403MiB/s；这是特定主机带缓存的小规模测试，不保证新服务器带宽。因此新workspace默认单路，测得收益后显式用两路。

Native保存耗时还包含GPU/CPU状态整理、ZeRO分片和最终导出；包装计时的部分指标是嵌套关系，不能相加。没有未经验证的异步tensor快照、DCP替代或自定义kernel补丁。

当前新仓库已执行 CPU / 固定Tokenization / 原生Recorder契约和远端FakeJob测试。真实 Qwen 4B GPU continuous 保存前中后PID/显存、长目标第二步及正式GA4长期稳定性仍待验证。根SGLang服务没有被修改、停止或迁移；没有证据据此指认其主动杀死了活跃训练。共享服务器的外部root操作、驱动故障和电源中断无法由用户级脚本排除。

参考固定实现：[PyTorch v2.8 ProcessGroupNCCL](https://github.com/pytorch/pytorch/blob/v2.8.0/torch/csrc/distributed/c10d/ProcessGroupNCCL.cpp)、[DeepSpeed原生Checkpoint合同](https://deepspeed.readthedocs.io/en/latest/model-checkpointing.html)、[systemd service](https://www.freedesktop.org/software/systemd/man/latest/systemd.service.html)、[systemd.path](https://www.freedesktop.org/software/systemd/man/latest/systemd.path.html)。本轮以实际安装的2.8.0/0.19.8源码为准，网页新版不替代现场版本。
