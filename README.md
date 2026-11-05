# Qwen3.5-4B：54 条分 Checkpoint 诊断轨迹

这里保存 2026-11-05 冻结审查的 **54 条 SFT 模型评测记录**，用于分析 Thinking、工具调用、运行故障与任务失败。

| Checkpoint | 记录数 |
|---|---:|
| NEW_M1_E5 | 12 |
| NEW_M2_E1 | 14 |
| NEW_M2_E3 | 14 |
| NEW_M2_E5 | 14 |

零调用、超时、Recorder 缺失和评分 UNKNOWN 均按原状态保留。这是选定任务的诊断材料，不能据此计算全量 TB2.1 成功率、训练增益或官方榜单成绩。工具、采样、模型身份及时限以每条原始 `config.json` 为准；包中不包含模型权重。

## 下载

仓库本体保存索引和说明，轨迹文件在 [Release Assets](https://github.com/CoyeCHEN/qwen35-4b-sft-rollouts-20261105/releases/tag/v2026.11.05) 中。

**先阅读轨迹：** [离线阅读 ZIP，约 117 MiB](https://github.com/CoyeCHEN/qwen35-4b-sft-rollouts-20261105/releases/download/v2026.11.05/Qwen35-SFT-54-offline-review.zip)。解压后打开 `review/index.html`，包含54个独立页面与索引。

**完整原始证据：** 约 6.5 GB 的完整 ZIP 分为4块，每块均小于[GitHub 的2 GiB发布文件限制](https://docs.github.com/en/repositories/releasing-projects-on-github/about-releases)：

- [Qwen35-SFT-checkpoint-54-rollouts-20261105.zip.00.part](https://github.com/CoyeCHEN/qwen35-4b-sft-rollouts-20261105/releases/download/v2026.11.05/Qwen35-SFT-checkpoint-54-rollouts-20261105.zip.00.part)
- [Qwen35-SFT-checkpoint-54-rollouts-20261105.zip.01.part](https://github.com/CoyeCHEN/qwen35-4b-sft-rollouts-20261105/releases/download/v2026.11.05/Qwen35-SFT-checkpoint-54-rollouts-20261105.zip.01.part)
- [Qwen35-SFT-checkpoint-54-rollouts-20261105.zip.02.part](https://github.com/CoyeCHEN/qwen35-4b-sft-rollouts-20261105/releases/download/v2026.11.05/Qwen35-SFT-checkpoint-54-rollouts-20261105.zip.02.part)
- [Qwen35-SFT-checkpoint-54-rollouts-20261105.zip.03.part](https://github.com/CoyeCHEN/qwen35-4b-sft-rollouts-20261105/releases/download/v2026.11.05/Qwen35-SFT-checkpoint-54-rollouts-20261105.zip.03.part)

原始包包含 Result、Recorder、模型请求/响应、工具附件、Session、Verifier、错误日志及离线页面，共249,156个原始文件。完整ZIP还含逐文件SHA、逐Trial映射和公开前的导出说明。源记录缺失的部分按原状保留，没有补造内容或修改Reward。

[分块身份与SHA清单](https://github.com/CoyeCHEN/qwen35-4b-sft-rollouts-20261105/releases/download/v2026.11.05/PARTS_MANIFEST.json) · [SHA256SUMS](https://github.com/CoyeCHEN/qwen35-4b-sft-rollouts-20261105/releases/download/v2026.11.05/SHA256SUMS.txt) · [54条公开索引](PUBLIC_TRIAL_INDEX.json)

### Windows 合并

将4个分块下载到同一个新目录，在该目录打开PowerShell：

```powershell
cmd /c "copy /b Qwen35-SFT-checkpoint-54-rollouts-20261105.zip.00.part+Qwen35-SFT-checkpoint-54-rollouts-20261105.zip.01.part+Qwen35-SFT-checkpoint-54-rollouts-20261105.zip.02.part+Qwen35-SFT-checkpoint-54-rollouts-20261105.zip.03.part Qwen35-SFT-checkpoint-54-rollouts-20261105.zip"
Get-FileHash .\Qwen35-SFT-checkpoint-54-rollouts-20261105.zip -Algorithm SHA256
```

### Linux / WSL 合并

```bash
cat Qwen35-SFT-checkpoint-54-rollouts-20261105.zip.[0-9][0-9].part > Qwen35-SFT-checkpoint-54-rollouts-20261105.zip
sha256sum Qwen35-SFT-checkpoint-54-rollouts-20261105.zip
```

完整ZIP应为 **6,498,288,325字节**，SHA256：

```text
a5f6cd5196935016897161f480606f206c84c24e83bf083a38abe54082290191
```

## 完整性与公开检查

源Result、已有Recorder与冻结审查SHA逐条核对；服务器压缩包与桌面副本的完整SHA一致。公开前对原始包和独立阅读包执行了凭据模式扫描；扫描范围与结果见 [PUBLIC_SCAN_SUMMARY.json](PUBLIC_SCAN_SUMMARY.json)。上传后按GitHub返回的资产size/digest逐项验收，身份见 [RELEASE_MANIFEST.json](RELEASE_MANIFEST.json)。

记录保留运行路径、localhost和服务地址等上下文元数据。扫描未发现所列规则覆盖的API凭据或私钥候选。包中不含训练权重或DeepSeek教师数据。原始采样材料按研究数据使用；请勿将评测轨迹直接混入声称无评测污染的训练集。

## 来源与版权

运行链路：Harbor-RSI / OpenHarness；学生模型为Qwen3.5-4B的训练后Checkpoint。Terminal-Bench上游：[harbor-framework/terminal-bench](https://github.com/harbor-framework/terminal-bench)。

任务、软件及第三方附件保留各自原始版权和许可证；本仓库不以统一许可证重新授权第三方内容。本数据是运行记录和故障诊断材料。
