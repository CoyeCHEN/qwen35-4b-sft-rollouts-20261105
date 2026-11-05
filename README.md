# Qwen3.5-4B：54 条分 Checkpoint 诊断轨迹

这个仓库保存 2026-11-05 已冻结审查的 **54 条 SFT 模型评测记录**，用于研究工具调用、Thinking、运行故障和任务失败。

| Checkpoint | 记录数 |
|---|---:|
| NEW_M1_E5 | 12 |
| NEW_M2_E1 | 14 |
| NEW_M2_E3 | 14 |
| NEW_M2_E5 | 14 |

零调用、超时、Recorder 缺失和评分 UNKNOWN 均按原状保留。记录数不等于完整成功轨迹数；这是选定任务的诊断材料，不是完整 TB2.1 的官方成绩或未见任务泛化报告。未将 M0、旧 M1/M2 历史评测或 DeepSeek 教师轨迹混入。

## 文件发布状态

**正在执行公开前检查和 Release 上传，当前尚未宣布数据上传完成。**

完整 ZIP 约 6.5 GB，包含原始 Result、Recorder、请求/响应及工具附件、Verifier 和 54 个离线页面。大文件使用 GitHub Release 分块分发，不写入 Git 历史。完成后会提供分块 SHA、合并命令及独立的离线阅读 ZIP。

[54 条公开索引](PUBLIC_TRIAL_INDEX.json)

## 使用范围与来源

模型是 Qwen3.5-4B 的训练后 Checkpoint，运行链路为 Harbor-RSI / OpenHarness。每条原始配置、身份与异常证据随原始包保留。

Terminal-Bench 上游见 https://github.com/harbor-framework/terminal-bench 。任务、软件及第三方附件保留各自原始版权和许可证；本仓库不以统一许可证重新授权第三方内容。

数据用于故障分析；请勿将其中的基准任务或 Verifier 输出直接混入声称无评测污染的训练数据。
