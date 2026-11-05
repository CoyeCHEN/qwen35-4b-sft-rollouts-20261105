# 正式 Campaign 的环境门槛

正式 Campaign 使用 `harbor rsi campaign`。它复用 Harbor 的 TaskClient、Job、Trial、Agent.setup 和 Docker/Remote Docker 生命周期；不调用 Agent.run、Oracle 或官方评分来判断环境是否合格。`run` 最终仍交给原生 Harbor 队列。

历史实验原件与旧 Wheel 保留；生产代码不兼容旧 request/launcher。`harbor rsi campaign` 是唯一 RSI 正式入口，上游 `harbor run` 保持官方低层命令语义，不取得 Campaign 门禁身份。

## 实际流程

先在独立控制器 venv 安装明确的 Harbor、Provider Wheel，以及它们的正常依赖。保留 Wheel 文件、SHA256 和源码提交/差异清单。通过本地 Wheel 安装的 `direct_url.json` 用于记录实际安装工件的 SHA；缺少这一身份时不能冻结正式运行。

```bash
harbor rsi campaign prepare \
  --config /absolute/new-campaign/job.json \
  --profiles /absolute/new-campaign/environment-profiles.json \
  --contracts /absolute/new-campaign/contracts.json \
  --output /absolute/new-campaign/prepared

harbor rsi campaign validate \
  --prepared /absolute/new-campaign/prepared/prepared.json \
  --output /absolute/new-campaign/validation

harbor rsi campaign freeze \
  --validation /absolute/new-campaign/validation/validation.json \
  --output /absolute/new-campaign/ready.lock.json \
  --valid-for-sec 3600

harbor rsi campaign run --lock /absolute/new-campaign/ready.lock.json
harbor rsi campaign status --lock /absolute/new-campaign/ready.lock.json
```

无逐题覆盖时省略 `--profiles`。JobConfig 可以使用 Harbor 的 dataset 或显式 tasks；准备后固定实际解析出的本地任务集合。多模型使用原生 `agents`，多次独立尝试使用 `n_attempts`。仅相同 Task/Agent/有效环境的重复 attempt 共用一次安装验收；不同模型配置分别验收。冻结全部原生 Trial 身份和配置，不把重复 attempt 再乘到 tasks 轴。

输出目录必须新建，不能覆盖原准备、验收或正式结果。检查失败返回2，不产生 reward。不存在静默豁免或自动修复开关。

复验可在 `validate` 添加 `--previous /path/to/previous/validation.json`。只有 prepared SHA、完整部署身份和原生分组全部一致的 READY 证据可复用；失败项重新建立独立环境验收。旧报告不改写，复用检查保留最早时间，不刷新 TTL。代码、缓存或配置变化时必须重新 prepare，不能借用旧 Ready。

- **Prepare**：应用逐题 profile 的完整替换语义，使用真实环境启动以拉取/构建镜像、检查 staging 和挂载，再关闭该环境。记录每个 service 的实际 Image ID，并生成 `pull_policy: never` 的覆盖配置；动态构建的 service 使用标准 Compose `!reset` 清除正式启动时的 build。
- **Validate**：重新启动固定镜像和相同有效配置，检查资源、工作目录、可用磁盘容量、Agent.setup、声明命令、Verifier 脚本及 bootstrap。检查使用实际 Agent/Verifier 阶段环境和原生网络策略。Verifier 文件只在 Agent 检查结束后上传，检查环境随后销毁。
- **Freeze**：所有任务必须 `READY`，每项必要检查也必须通过。固定任务内容、有效 Trial 配置、Compose/工件文件、声明的缓存 manifest、安装包代码身份、Wheel SHA、镜像与 daemon 身份以及有界检查证据。
- **Run**：检查过期、文件/代码/环境变量漂移、daemon 身份、全部固定镜像是否仍存在；取得独占派发标记后才创建正式 Job。不能静默重派或复用已存在的正式 Job 目录。

`validate --skip-agent-setup` 只供准备审计使用：Agent 与依赖其安装的工具检查均为 `UNVERIFIED`，不能 Freeze。它不是快速通过选项。

## 外部合同

配置是经人工审阅的任务要求，不从题面猜测包、不调用模型分析任务、不按任务名称写核心分支。参考 [tb21-contracts.json](tb21-contracts.json)，其中 Task 名称仅用于选择配置数据。

每个合同必须说明 `basis`，并明确审阅 `runtime`、`network`、`assets`、`verifier`、`agent` 五个范围。每个范围引用检查 ID，或者给出真实的“不需要额外检查”的理由。没有合同的任务始终为 `UNVERIFIED`，即使镜像和启动检查成功。

```json
{
  "organization/task": {
    "basis": "题面明确承诺预装某解释器与包；安装服务本身仍属于 Agent 工作。",
    "coverage": {
      "runtime": {"reason": "验证承诺的真实运行时导入及版本", "checks": ["runtime-import"]},
      "network": {"reason": "这个任务不需要额外的外网来源", "not_required": true},
      "assets": {"reason": "输入已经包含在固定镜像，无额外公开缓存", "not_required": true},
      "verifier": {"reason": "Verifier 仅依赖已有 shell，另有脚本语法检查", "not_required": true},
      "agent": {"reason": "部署的 Agent 需要专门的无模型工具合同检查", "checks": ["agent-tools"]}
    },
    "checks": [
      {"id": "runtime-import", "category": "runtime", "phase": "agent", "command": "python -c 'import required_package'", "timeout_sec": 30},
      {"id": "agent-tools", "category": "agent", "phase": "agent", "command": "/path/to/deployed/runtime/python /opt/readiness/cli_contract_probe.py /path/to/deployed/open-harness", "timeout_sec": 60}
    ],
    "inputs": ["/absolute/cache/manifest.json"]
  }
}
```

命令是可信的运维配置，必须人工审阅。安装、下载只能作用于隔离准备容器/新缓存，不能把 Task 本应要求 Agent 安装的服务提前完成。系统不解析自然语言来决定安装内容。

网络命令设置 `network: true`，必须同时有连接超时与工具总期限；NO_NETWORK 下不会执行这种探针。检查应验证实际 URL 的重定向、TLS、响应码、必要字节和来源；短请求通过不证明 GB 级传输稳定。不要用 `pip ... | head` 隐藏退出码，先保存完整日志和原命令 rc，再预览日志。

缓存合同应声明其 manifest 为 `inputs`，检查文件哈希、精确版本/Revision/Key及原生加载。`inputs` 必须是文件；大型缓存使用清单，不把“目录存在”当验收。只读挂载在实际容器 attestation 中记录。运行时需要写缓存时使用独立工作副本，不能写共享公共缓存。

Compose 引用的 `env_file`、configs/secrets 文件也计入内容哈希；本入口要求这些路径为字面路径，并要求先展开 include/extends。挂载的大型缓存需要声明可校验 manifest；冻结不会阻止其他宿主进程篡改缓存，因此必须由运维维持缓存不可变，内容校验与 TTL 仍然必要。

凭据通过 `${VARIABLE}` 继承，禁止把密钥或带认证信息的代理 URL 直接写入配置。显示脱敏与内部配置回放分开：普通 `GIT_CONFIG_KEY_0=http.version` 必须原样进入真实进程，不能把脱敏显示文本拿去执行。

## Agent 和 Verifier 的准备

[cli_contract_probe.py](cli_contract_probe.py) 是外部 CLI 黑盒 fixture，不导入 Harness 内部模块。通过只监听容器 loopback 的确定性 HTTP fixture，验证实际安装 CLI 的 Bash 输出、非零退出、超时和子进程环境；不会调用真实大模型，也不读取题面或答案。Bash 的 stdout/stderr 本来是合并流，检查的是两种输出都能保留。

在目标解释器中使用标准 `pip download --only-binary=:all:` 准备 Agent wheelhouse，记录每个 Wheel 的 SHA256；以只读卷挂入，并在 Agent kwargs 的 **`install_env`** 设置 `{"PIP_NO_INDEX":"1","PIP_FIND_LINKS":"/container/wheelhouse"}`。适配器只在安装期间使用 Harbor 原生 `scoped_exec_env` 施加这些参数，安装失败也会恢复；不要把它们放进整个 `agent.env`，否则会改变 Task 自行安装依赖的权限。随后真正执行 Agent.setup 和 CLI fixture。这同时验证 ABI、完整性及离线可安装性，不只检查宿主目录。Agent 私有解释器可能与 Task 默认解释器不同；先读取真实安装的 `agent/artifact.json`，不能用 Task 的 `python` 版本猜测 Agent ABI。其他 Python ABI 必须分别验收；旧系统需要 managed Python 时还须准备对应解释器，不能拿3.11的成功代替3.13。

Verifier bootstrap 需要单独声明。不要执行依赖答案的测试来要求预检得1分；可以运行相同 pinned requirements 的安装/导入、Git revision检出、公开权重校验。已有 `prepare_verifier_cache.py` 仅适用于其明确支持的 pinned uvx 配方；它会拒绝未覆盖的 VCS/索引，不能为方便而伪称 SAM 配方已被完整覆盖。

SAM 的 [派生镜像配方](recipes/sam-promised-dependencies.Dockerfile) 只恢复题面承诺的 Python 依赖。它使用固定上游 MobileSAM commit `34bbbfdface3c18e5221aa7de6032d7220c6c6a1` 的源码归档，不能用 Releases HTML 当安装源。将原官方 RepoDigest 通过 `--build-arg BASE_IMAGE=...` 传入，源码归档放在独立 build context 并记录 SHA256，再用标准 `docker build --pull=false` 构建新标签。原 Task、原镜像标签、答案和 Verifier 不变；新结果必须标明这是修复过初始环境的评测条件。

## 支持边界

当前真实验收路径为 Linux Docker/Remote Docker。E2B、Modal、Podman 返回 `UNVERIFIED`；独立 Verifier、多步 Task 也不会被这版预检伪称完整覆盖。Provider 原生不能实现的网络策略必须阻断，不能放宽 NO_NETWORK 来让检查通过。

本地 Docker 的 Campaign 有效配置固定 `environment.delete=false`，使用原生 `stop(delete=false)` 删除测试容器/网络并保留镜像；原生 `delete=true` 会执行 `compose down --rmi local`，可能使刚准备好的动态镜像消失。Remote Docker 原生删除路径本来就不删除镜像。此设置只属于本入口的显式有效配置，不改变 Harbor 默认行为；本地 Task 自建 named volumes 可能保留，运维应按所属项目管理，不执行全局 prune。

CPU/Memory 检查实际 Docker 限额；磁盘检查实际可用容量，并明确记录 Docker 没有承诺逐容器硬配额。有硬磁盘配额合同的 Benchmark 还需原生支持或独立证据，不能把容量检查称为配额验收。

镜像固定、配置哈希及 TTL 无法保证未来网络永不故障。原 Verifier 若坚持每次访问外部 installer/weights URL，准备缓存并不自动消除它的访问。应保持原行为并验证真实访问；需要完全离线时，必须有明确、经过验收的资产接口，不能偷偷改官方评分脚本。

环境 `READY` 与最终 reward 完全独立。正式运行仍保存 Harbor 的原始结果、Verifier 和 Recorder；合法零分不被本门槛转为环境错误。历史无效评分不会被重写或回填。
