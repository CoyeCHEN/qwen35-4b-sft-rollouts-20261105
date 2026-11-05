# OpenHarness 私有依赖边界

用户明确选择：先公开自有代码，Harness 保留为私有依赖。

未发布 RUCAIBox/open-harness2 的源代码、提取出的 foundation/ 模块、私有 Wheel 或私有源码补丁。公开的是自有调用端、Harbor adapter、数据转换器及接口/版本/SHA。调用端出现 `from foundation...` 是外部依赖引用，不代表实现随仓库公开。

冻结依赖身份见 `metadata/HARNESS_WHEEL_IDENTITIES.json`：

- 教师：`open_harness_ai-0.3.0+rsi.summary.20261030-py3-none-any.whl`；SHA256 `c686ba3f429d8257a060cf6b6a6e4c5aa7d740f33b2d59180d9a2717b55d0db8`。
- 评测 Wheel6：`open_harness_ai-0.3.0+rsi.reliability.20261104.6-py3-none-any.whl`；SHA256 `8c84a8659c136b027c36c48a7100d956fdb58c873b347ef6b240b561cc75e85d`。
- 基础导出器依赖：`open_harness_ai-0.3.0-py3-none-any.whl`；SHA256 `47dc9cc9e37370be00589f690d2da7c5a08e964407dac6e94c57a2a2018da95d`。

有权限的执行者应从原负责人处取得对应工件，先校验 SHA，再在指定环境安装；不能用同名最新版替换。Harbor 接受显式 Wheel 路径和 SHA；不从相邻私有源码目录导入 Harness 内部实现。

公开包不会下载私有 Wheel、读取密钥配置或修改原仓库可见性。旧 SFT 中的 synthetic fixtures 是接口测试，不是私有 Harness 实现或正式训练数据。
