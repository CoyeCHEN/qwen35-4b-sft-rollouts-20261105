# WorkspaceBench Gate 2 验收报告

日期：2026-10-12
范围：WorkspaceBench Lite task 3；不启动 OpenHarness Agent、不启动 r5、不派发剩余九题。

## 结论

Remote Docker 的 stale-workdir 修复通过了真实远端环境的无模型故障注入和确定性 Verifier 契约测试。删除 task workdir 后，Harbor 内部控制命令仍能执行，文件目录传输、权限失败、缺失文件和命令非零退出被分别识别；原始 `tests/test.sh` 在确定性 Judge stub 下返回 0，并由 Harbor 回收 `reward.txt=0.0`。

真实 DeepSeek Judge-only Gate 2 未通过，因此 Workspace 后续九题和 r5 仍然禁止启动。固定工件、任务容器和 `tests/test.sh` 均进入了执行链，但 verifier 命令返回 1，`/logs/verifier/reward.txt` 不存在。Remote Docker 随后准确报告缺失 reward 并完成资源清理。由于 verifier stdout/stderr 被任务脚本重定向，且容器在失败后已清理，本次保留证据不能把失败进一步归因到 Judge HTTP 响应、模型名、网络或工件内容；不能将它记为有效评分。

## stale-workdir 语义

当前实现位于 `packages/remote-docker/src/harbor_remote_docker/environment.py` 的 `_compose_exec`：

1. 仅对 `main` 服务且请求 cwd 等于 Task 的 `workdir` 做目录探测。
2. 探测到目录不存在后，当前 Environment 实例设置 `_task_workdir_unavailable=True`，后续同一实例的相同 cwd 不再传 `docker exec -w`。
3. Workspace Compose 将容器 `working_dir` 声明为 `/tmp`，所以本次删除后的 `pwd -P` 实际返回 `/tmp`。
4. Agent 在目录存在时仍使用原始 cwd；本次没有改变 Agent 的初始工作目录，也没有在 Harbor core 添加 Workspace 分支。
5. 标志位是单个 Provider/Trial 实例状态，容器重建会创建新实例并重新探测。

该实现足以覆盖已复现的 Workspace r4 时序，但不是任意镜像的完整保证：如果 Compose/镜像默认工作目录本身也不存在，省略 `-w` 仍可能失败；并且 Agent 在 workdir 删除后继续显式请求原 cwd 时会得到 Provider 的稳定 fallback，而不是原 cwd。后续应把 Harbor 内部控制操作统一改用经验证的 Provider-owned cwd，并保留 Agent cwd 的失败语义，作为通用接口改进单独验收。本轮没有为此新增特例。

## 真实 Remote Docker 故障注入

运行目录：`/tmp/workspace-contract-fault-injection-20261012g`
Provider evidence：`/tmp/workspace-contract-fault-injection-20261012g/trial/remote-docker-99d4280e3cba40ada253d96621c7aa43.jsonl`

验证步骤和结果：

- 启动原始 Workspace image 的远端 Compose 环境：通过。
- 创建固定 native agent artifact，不调用模型：通过。
- 删除真实 task workdir：通过。
- 删除后 `exec("pwd -P", cwd=deleted_workdir)`：exit 0，输出 `/tmp`。
- `download_dir` 和 `download_file`：通过，内容可读。
- 将目录当作文件下载：抛出 `RemoteDockerError: Expected one regular file in transfer`。
- 下载不存在文件：抛出带 tar `Cannot stat` 的 `RemoteDockerError`。
- 非 root 读取 `chmod 000` 文件：exit 1，保留 `Permission denied`。
- `false` 命令：exit 1，不被转成成功。
- cleanup：通过，Provider identity 为 `99d4280e3cba40ada253d96621c7aa43`。

这组证据证明删除目录不会再把内部控制操作误判成普通文件，也没有执行全局清理。

## Verifier 链路

确定性 Gate 2 preflight 使用原始 Task、原始 `tests/test.sh`、Remote Docker 和任务镜像内的 native bridge；Judge endpoint 是容器内固定 HTTP stub，不调用模型。结果目录为 `/tmp/phase4-workspace-verifier-preflight3-20261012`：

- `test.sh` exit 0；
- `/tmp/phase4-workspace-verifier-preflight3-20261012/trial/verifier/reward.txt` 为 `0.0\n`；
- Harbor 解析为 `{"rewards":{"reward":0.0}}`；
- Provider identity cleanup 通过。

该结果证明原始 Judge bridge、reward 写入和 Harbor 回收契约可连通；它不证明 DeepSeek Judge parity。

随后只执行了一次真实 DeepSeek Judge-only 测试，使用相同 Task、固定 native artifact 和 `deepseek-flash` 配置，预计约 20k 输入 token、一次请求，不运行 Agent。运行目录为 `/tmp/workspace-real-judge-only-20261012`，Provider identity 为 `bc892ce63d924fa49c0c9d0d633c75db`。容器启动、artifact 下载和 verifier 入口均完成，但：

- `tests/test.sh` 返回码为 1；
- `/logs/verifier/reward.txt` 未生成；
- Remote Docker 下载缺失 reward 时返回 exit 2，并保留 `tar: reward.txt: Cannot stat`；
- cleanup 通过；
- 没有合法 reward，也没有可计入的 Judge 结果。

当前证据只能确认 verifier 入口失败在 reward 产生之前。由于 `test.sh` 将 bridge 输出重定向到 `/logs/verifier/test-stdout.txt`，而本次失败前未回收该日志，真实 API 的 HTTP 状态和原始响应没有保存。不能据此断言是 Judge API、模型 ID、网络、响应格式或固定 artifact 中的某一项。下一次诊断必须先保证 verifier stdout/stderr 和 native judge response 在失败路径也被回收；在此之前不应再次付费调用。

## 代码、工件和测试身份

- Harbor 工作树：`/home/cky/harbor-rsi-final`，基线 commit `a6f2b04d`，Phase 4 修改仍未提交。
- Remote Docker Provider wheel SHA-256：`9cb6f95d93616584409fdeca4c9fb11457cc16f42b638fd306eec63b7531bbac`。
- Remote Docker provider 通过 `EnvironmentConfig.import_path` 加载，普通 DockerEnvironment 不包含 Remote Docker 分支。
- 本轮定向回归：

  `PYTHONPATH=packages/remote-docker/src .venv/bin/python -m pytest tests/unit/test_remote_docker_provider.py tests/unit/rsi/test_contract.py tests/unit/rsi/test_lifecycle.py tests/unit/rsi/test_native_job.py -q`

  结果：`69 passed, 7 warnings, 7.67s`。

没有修改 Harbor core、OpenHarness Agent loop、原始 Workspace Task 或 Verifier。临时故障注入脚本和真实 Judge 运行目录均位于 `/tmp`，未写入提交。

## Gate 状态

| Gate | 状态 | 证据 |
|---|---|---|
| Environment、安装/命令/传输 | 通过 | 真实 Remote Docker 故障注入；69 项回归 |
| 原生 Verifier、reward 生成/回收 | 确定性 stub 通过；真实 Judge 阻塞 | preflight reward `0.0`；真实调用无 reward |
| 一题真实 OpenHarness 端到端 | 未执行 | 按要求停止 |
| 剩余九题 | 未执行 | 按要求停止 |

因此当前工程状态是 `partial/blocked-at-gate-2`，不是 WorkspaceBench 完成，也不是 r4 的 Verifier-only recovery。最小剩余问题是补齐真实 Judge 失败路径的 stdout/stderr/API response 证据，然后在确认责任层后再决定是否需要唯一一次受控重试；在此之前不得启动真实 Agent 或后续题目。
