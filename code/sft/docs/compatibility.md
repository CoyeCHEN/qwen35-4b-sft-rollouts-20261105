# 兼容性与迁移范围

基线：`CoyeCHEN/openharness-sft@076ab3fe0385fb13a2ea652aac3107961929044b`，private。该 main 已包含 `4cea869` 的 Recorder / Reward 完整性修复，不重复 cherry-pick，也不覆盖其他工作树的未提交报告。

本轮真实读取 GitHub refs 后：Open-Harness main 仍为 `23636e329521746e7632a020fce045967c24aec5`；已审计 Commit `4b136692905ba5818620f99d55a7d9d77f2c0b9a` 与其 tree 同为 `04fdbd939c8acc921fc50894a486d72c241151a8`。新采集固定后者。Harbor main 为 `ad898548b1a61e93900df35893a3547e05af9d0a`。这都是本轮读取的结果，不将它们永久称为“最新版”。

| 旧实现 | 当前上游合同 | 复用与最小修改 | 验证 |
|---|---|---|---|
| SFT v2 reader | `open-harness-rollout-v2`；闭合的 run/call/tool；完整性与 reward 分开 | 保留已合并的完整性检查；补 export 中重复 call ID 拒绝 | 原 reader / integrity 回归 |
| Evidence M2 按三个返回值解包 `_raw_rows` | 主仓 reader 返回 manifest / calls / tools / runs / integrity 五项 | 统一使用主仓 reader 和闭合检查，不复制旧 adapter | 原生 exporter 合成契约 |
| 单一顶层 session_id | 原生 exporter `manifest.sessions[]`，可含子 Session | 新来源合同为 `raw_recorders[]`；全部 session SHA / 闭合证据必须齐全 | Recorder→export 实测；旧 export 对新 Recorder 拒绝 |
| 只按 Session ID 关联 export | 同一 Session 可重开并新增运行 | 比较原始与导出 call/payload/response/tool 内容投影，不接受过期导出 | 实测同 Session 新增闭合 call 后旧 export 被拒绝 |
| 累积 history 或 canonical 排序后的工具参数 | 每个 call 的 actual provider payload；compaction 已体现在请求中 | 优先实际 payload，先核对 canonical 语义；保留参数顺序 | 真实 Tokenizer compaction / 参数顺序黄金测试 |
| 默认 OpenAI→LF 转换 | Assistant 正文、reasoning_content、toolCalls；Qwen 固定模板 | 绕过有损默认转换，预编码 input_ids / labels；不修改 Harness | 10 条黄金测试及真实 LF Collator |
| TMax Tokenizer / 8K / 外部 tmax_sft | Qwen3.5-4B 固定版本；LF 原生模型加载 | 删除旧训练 stub 和配置；M1 64K、M2 128K/96K；全语言训练、冻结视觉 | LF parser / 参数范围及既有 GPU 证据 |
| 旧 legacy-eval CLI profile | Harbor `native-cli-v1`、`record_trajectory=true`、显式 wheel SHA | 新 collection 只接受 native profile；Harbor 自己执行任务 | 实际上游 options、artifact.json、JobConfig / CLI 源码核对 |
| Reward=1 便当成功；布尔 reward | Verifier success + exact task/trial + recorder closure + installed wheel | 有限 numeric reward=1，拒绝 bool、基础设施错误、身份错配；绑定 Trial 内原始工件 | 原 reward 回归；来源校验 |
| 只接受 status=completed 的工具 | 闭合的 error tool 同样产生合法 Observation | 允许有结果的闭合 error；缺失执行、孤立结果仍拒绝；Observation 不进 loss | reader 闭合回归 / 角色与 mask 黄金测试 |
| SSH 控制临时脚本 | systemd 用户服务，linger，独立 cgroup | Job ID + config SHA + PID/startticks/boot ID；Restart=no；不凭 PID 自动重启 | 断连、重复、TERM/KILL、CPU elastic Rank 退出实测 |
| 保存后受控退出的 smoke | 正式 Trainer 正常保存后继续循环 | 生产 driver 不提供 bounded stop/max_steps 参数；旧 GPU 测试队列保留独立 | 原生 CPU Trainer 保存后继续 step2；GPU continuous 待原队列 |
| 系统盘输出 / 同步共享盘归档 | SSD 热路径、CPU 归档、完整 native ZeRO-3 | 文件硬链接 pin、完整性标记、SHA、原子发布；挂载身份检查 | fixture 故障；既有 56.1GiB 真备份/恢复证据 |
| 松散依赖、旧 uv.lock | 固定 LF commit、Torch2.8 / TF5.8 / DS0.19.8 与 kernels | 实际环境生成约束锁；检查六个 LF 关键源码 SHA | `.17` 实际依赖 / 配置检查 |

没有新增 Legacy Adapter、Provider、Agent Loop 或模型协议层。历史诊断格式仅保留在原 reader / examples；新 M2 的审核与训练路径不从 RLBridge、TMax Token IDs 或未验证别名回退。

原生固定 Qwen 模板不在模型输入里编码 tool-call ID，故转换器在审计索引中保留并验证 ID 对应、按原顺序投影；并行工具结果乱序而模板无法无歧义表示时拒绝。模板把 Assistant 的文本正文放在 tool XML 前，保留正文片段间的顺序；原始 block 顺序保留在不可变 Recorder。原生模板若删除历史 Thinking，转换器明确拒绝，不伪造历史。
