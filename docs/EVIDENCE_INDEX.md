# 源码及证据索引

- `metadata/ACTUAL_PRODUCTION_TRAINING_IDENTITIES.json`：实际训练源码、配置、模型及状态 SHA。
- `metadata/ACTUAL_SFT_SOURCE_FILE_IDENTITIES.json`：远端 source-r4 的逐文件原始 SHA。
- `metadata/CORE_ASSEMBLY.json`：SFT 与 Harbor 的来源版本。
- `metadata/PUBLIC_SOURCE_FILES.json`：本次公开文件逐项 SHA。
- `metadata/PUBLICATION_TEST_CHANGES.json`：公开副本相对生产源码的测试修改；runtime 不改。
- `metadata/training-identity/`：训练配置、Manifest、resolved config、Trainer 状态和既有证据副本。
- `metadata/FROZEN_772_CORPUS_MANIFEST.json`：772 个成功任务的冻结身份，不含原训练数据正文。
- `metadata/evaluation-configs/`：实际 Wheel6 原生 Job/Profile/合同快照。
- `metadata/HARNESS_WHEEL_IDENTITIES.json`：私有工件版本和 SHA；无 Wheel 或实现源码。
- `metadata/VERSION_SETS.json`：训练与 Serving 两套真实依赖版本。
- `metadata/VIEWER_SOURCE_PROVENANCE.json`：原离线查看器的10份代码身份。
- `metadata/publication-validation/`：已完成的 CPU 测试输出。
- 根目录 Release/Parts Manifest：原54份轨迹和6.50GB完整ZIP身份；Release未替换。

部分旧身份/日志文件是已经脱敏的证据副本，原 SHA 指向原件；不要将脱敏副本字节与原 SHA 混用。公开副本的实际字节以 PUBLIC_SOURCE_FILES.json 为准。
