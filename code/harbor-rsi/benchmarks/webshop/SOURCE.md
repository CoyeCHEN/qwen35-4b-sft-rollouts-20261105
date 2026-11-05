# WebShop 来源与评分边界

- 官方仓库：`https://github.com/princeton-nlp/WebShop`
- 固定提交：`64fa2a5c15c7daa698b9ac93f5bb5437b634c9bd`
- 数据首选来源：官方 `setup.sh` 中列出的 Google Drive 文件 ID
- 数据后备镜像：`YWZBrandon/webshop-data@ce990fff5aee388db2706f07820c578ab68e0453`

完整数据固定文件：

- `items_shuffle.json`：5,479,720,229 bytes；SHA256
  `2ef591d65df3af89e972ab72468eb82cbf124d876552d9f3678667edd620a6c8`
- `items_ins_v2.json`：186,295,270 bytes；SHA256
  `1d36af476bdb8f82a5da62bd8acdabe54cd8de2fa84010d37da5c4890feb447e`

Hugging Face API 还返回不同的 `xetHash`；本项目校验的是 LFS `oid`，即实际文件
内容的 SHA256，而不是 Xet 存储哈希。

正式 test split 依据官方 `baseline_models/env.py` 与 `baseline_models/test.py`：完整商品模式
下 `goal_idxs = range(500)`，每个 episode 最多执行 100 个动作。完整资产构建后，
`sources/webshop-full/manifest.json` 记录原始文件、SQLite、goals 和每个 Lucene 索引文件
的哈希与大小。
- 环境：官方 `WebAgentTextEnv` 的 `text` 模式
- 状态转换：官方 `search[...]` / `click[...]`
- 评分：官方 `web_agent_site.engine.goal.get_reward`，归一化范围 0 到 1
- 最大交互步数：100，与官方 baseline 测试 episode 一致

当前 smoke 镜像使用官方 `setup.sh -d small` 对应的 1000 商品文件和
`items_human_ins.json`，并针对这 1000 商品构建官方 Lucene/pyserini 索引。因此它用于
验证 OpenHarness 是否能完整进入环境、连续交互、购买并获得 reward；它不是论文中
118 万商品、测试集前 500 个目标的正式全量分数。

由于官方 Google Drive 链接可能拒绝匿名自动下载，准备脚本在 Drive 失败时使用上述
固定提交的 Hugging Face 镜像，并在下载结束后输出三个文件的 SHA-256，供运行记录
锁定实际数据内容。

兼容性改动只有一项：镜像删除文本环境中未使用的顶层 `torch` 导入，避免安装图像
特征栈。商品加载、目标生成、搜索、页面状态机和 reward 代码保持固定提交原样。
