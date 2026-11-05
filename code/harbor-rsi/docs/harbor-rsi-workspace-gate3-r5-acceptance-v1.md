# WorkspaceBench Gate 3 r5 结果

日期：2026-10-12
范围：WorkspaceBench Lite task 3；只派发一次正式 Agent Trial。r5 失败后没有启动 r6 或其余九题。

## 结论

Gate 3 未通过。本次 Agent 正常退出并生成了目标 Markdown 文件，但 Trial 在
Verifier 交接前后使用了旧版 RemoteDocker runtime。Agent 结束后 task workdir
按 native runner 的既定成功清理策略被删除；旧 provider 只在首次命令上记录
`task_workdir_unavailable`，后续命令仍携带已删除的 cwd。结果是 artifact 目录被
误判为普通文件，artifact 回收失败，Verifier 没有可回收的 `reward.txt`，Harbor
最终报告 `RewardFileNotFoundError`。

这不是 Agent exit、OpenHarness wheel 安装或模型调用失败。任务 image 已包含同步的
诊断 bridge，但保留的 provider evidence 中没有 DeepSeek Judge HTTP 请求或诊断文件；
旧 provider 在交接阶段先失败，容器随后按 identity 清理，因此不能从本次证据断言
请求已发出或未发出。可以
确认的首次异常是 `task_workdir_unavailable` 后的 artifact 目录类型错误。

## r5 证据

| 阶段 | 结果 |
| --- | --- |
| Environment start | 通过；identity `83c26f8901674aa9a3d80c6b1219e0b6`，15:43:19-15:43:28 UTC |
| Agent installation | 通过；OpenHarness wheel SHA `09c874a34f985266548292ee17acc234f30cda4b850d0b492df2c55cd4656f1f` |
| Agent execution | 通过；CLI exit 0，stderr 为空，28 次模型请求，输入 801450、cache 766208、输出 16869 tokens，约 161 秒 |
| Workspace/output | Agent trace 表明已写入 `model_output/project_dependency_deduplication_list.md`；native runner 随成功策略清理 workdir |
| Provider handoff | 失败；evidence 记录 `task_workdir_unavailable`，随后 `/logs/artifacts` 和 `/logs/workspace-native` artifact manifest 均为 `type=file,status=failed`，错误为 `Expected one regular file in transfer` |
| Native Verifier/Judge | 未形成可审计结果；没有保存到本地的 verifier stdout/stderr 或诊断 JSON |
| reward | 缺失；Harbor `RewardFileNotFoundError`，未计分 |
| cleanup | 通过；identity-scoped cleanup 记录 `cleaned`，并清理本轮故障注入遗留资源 |

原始 Trial 结果：
`/home/cky/.local/state/harbor-rsi/workspace-gate3-r5-task3/workspace-gate3-r5-task3/workspace-gate3-task3-bridge-202__s6TpJsC/result.json`

Provider evidence：
`/home/cky/.local/state/harbor-rsi/workspace-gate3-r5-task3/workspace-gate3-r5-task3/workspace-gate3-task3-bridge-202__s6TpJsC/remote-docker-83c26f8901674aa9a3d80c6b1219e0b6.jsonl`

## 修复与离线验证

canonical benchmark adapter 已同步脱敏诊断 bridge（SHA
`0abd123831898faefa833eb1c8cb1899e6e6dc08ab06aa359a74ff695a2edf1f`），记录配置、
输入校验、HTTP 状态/错误码、耗时、响应解析、21 条 rubric、异常堆栈和原子 reward，
不会保存 API key 或完整响应正文。固定 seed image 上构建的 adapter image 为
`harbor-rsi-workspace-gate3-bridge:20261012`，digest
`sha256:5d2321921b87faf854e666f73059bc106f50ada4d939a9ddb8593f9631411b2a`。

实际 r5 使用的 Harbor venv 在派发时仍加载旧 provider wheel（direct URL 为
`/tmp/phase4-runtime4-dist.tOOID3`，SHA `e308570108e5d4f8d83bafe355881b9abaa8acb9c7e0b5608e10cfd0b5230b9c`），不是本轮要求的
RemoteDocker wheel `9cb6f95d93616584409fdeca4c9fb11457cc16f42b638fd306eec63b7531bbac`。
之后已将受控 venv 更换为目标 wheel；源码和目标 wheel均包含后续命令省略失效
cwd 的修复。目标 wheel 的 provider 回归和 Workspace bridge/Verifier 离线契约测试：

```text
PYTHONPATH=packages/remote-docker/src uv run pytest -q \
  tests/unit/test_remote_docker_provider.py \
  tests/unit/rsi/test_lifecycle.py tests/unit/rsi/test_native_job.py \
  tests/unit/rsi/test_workspace_native_bridge.py \
  benchmarks/workspacebench/tests/test_workspacebench.py
63 passed, 1 skipped
```

无模型 handoff preflight（派生 image、固定 agent.json、原始 `tests/test.sh`、
deterministic HTTP 200 stub、21 条 rubric、reward `0.0`、cleanup）通过，证据为
`/tmp/workspace-gate3-handoff-preflight-20261012/result.json`。它没有调用付费模型。

## 计分与后续

task 3 的 r5 没有合法 reward，WorkspaceBench Lite 有效评分仍为 0/10；另外九题
保持未启动。Gate 3 未通过，因此不能进入 Gate 4。下一次真实运行前必须从已安装并
校验 SHA 的目标 provider venv 重新执行一次独立 no-model handoff；本报告对应的
r5 不重试，r1-r4 证据保持原路径不变。
