# 排障源码快照的验证边界

本次目的是交付代码给他人 debug，不是重新验收生产训练。用户要求尽快上传后，未追加训练、Serving 或评测测试。

已完成：

- SFT CPU 测试：173 passed，15 skipped，13.30 秒。
- 公开 Tokenizer 资产的 Codec/分段测试：25 passed，6.82 秒。
- Harbor Remote Docker Provider/取消/本地 I/O/探测超时测试：47 passed，0.83 秒。
- Viewer JavaScript 语法检查通过；10 个原查看器源文件 SHA 与原交付 provenance 一致。
- 实际训练 runtime SHA 与生产记录一致：`293ba2a7dca8569bb39e11bc0137a0e1180a0391402f10d49ff5b4ad00ce6c93`。
- M1/M2 YAML、ZeRO3 和十一工具合同的四份 SHA 与生产身份记录一致。
- 本次未重新执行 GPU 训练或真实 Benchmark；没有改动原训练目录、模型、总控或服务。

发现并修正了公开副本的测试问题：阅读包误脱敏的假 Token 已从真实源码恢复；四个测试文件补齐 world_size、callback 元数据，以及已修复生成边界的正确断言。生产 runtime 未变，具体差异见 `metadata/PUBLICATION_TEST_CHANGES.json` 和 `code/patches-and-diffs/publication-tests-only.patch`。

原始测试输出见 `metadata/publication-validation/`。跳过项不声称通过；本次没有声称 GitHub Actions 或完整端到端重部署已经通过。

排障者仍需要有权限的私有 Harness Wheel、模型/语料和执行环境。历史运维脚本保留原路径和修订号，不应批量盲跑。OpenHarness 源码、私有 Wheel、API/SSH 凭据和模型权重均不在本公开源码包。
