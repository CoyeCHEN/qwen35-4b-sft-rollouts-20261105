"""Read-only report rendering, fed by the existing20-minute observer."""
from collections import Counter
import hashlib,json
from pathlib import Path

def render(root,progress,environment):
 root=Path(root);stamp=progress['checked_at']
 def emit(name,text):(root/name).write_text(text.rstrip()+'\n')
 counts=progress['environment_status_by_pool'];ctrl=progress.get('controller',{})
 active_scope=ctrl.get('campaign_scope','collection-r3')
 bindings=list((root/'manifests/runtime-bindings-r4').glob('*.json'))
 reserve_ids={json.loads(p.read_text())['candidate_row']['task_id'] for p in bindings}
 reserve_acceptances=sum(p.stem in reserve_ids for p in (root/'checks/native-reserve-acceptance-r4').glob('*.json'))
 handoff_note=('r3已在原生生命周期全部结束后安全交接；r4为当前唯一教师控制器，继续使用原模型/工具/预算合同。旧源码、Job及Trial保留。' if active_scope=='collection-r4' else '当前r3保留其冻结源码与在途Trial，复核通过的环境和候补待安全空闲交接后采纳；没有启动第二个付费控制器，也未中断健康教师Trial来切换版本。')
 if ctrl.get('controller_revision') in ['r6','r7','r8','r9','r10','r11','r12','r13','r14','r15','r16','r17','r19','r20']:
  handoff_note='前代控制器均按各自原生交接证据撤销新增派发权限；当前版本为唯一新增派发总控，暂驻149。在途旧版本仅继续已经开始的原生生命周期。当前及所有继承中的旧版本教师均按已验收的原生AGENT_START→AGENT_END计数；合计教师许可最多8，Verifier/回收另列；未用节点本地flock冒充跨节点互斥。旧Trial不取消、不重跑、不追改。'
 attempt_note=(f"实际AgentStart与旧配置保守预留的合并账本为{ctrl.get('submitted_attempts')}次、{ctrl.get('teacher_independent_tasks')}个独立任务，不能等同于这些任务都已实际调用模型；旧配置预留另为{ctrl.get('legacy_configuration_reservations')}次，其中4次经原始Result证明在environment_setup阶段终止，未开始Agent。所有历史记录保留；尚有旧配置计数读取器相关的保守hold：{ctrl.get('legacy_reader_compatibility_holds',[])}。" if ctrl.get('controller_revision') in ['r6','r7','r8','r9','r10','r11','r12','r13','r14','r15','r16','r17','r19','r20'] else f"旧Job配置与新dispatch保守记账{ctrl.get('submitted_attempts','未观察')}次，涉及{ctrl.get('teacher_independent_tasks','未观察')}个独立任务；其中包含未发出模型请求的setup项。")
 backend_note=('新准备、镜像驻留/加载、staging、执行、Verifier及清理全部绑定17私有SSD Engine59c8ba22-0aa4-4aed-bc43-4e1b5989fa22；绑定先于镜像检查和Ready。149保留原生Harbor收集镜像，当前版本逐Trial另存17 SSD完整文件SHA副本。旧149教师按原生生命周期收尾；旧149无模型准备队列仍单列观测，在其终态前不宣称149无新增任务容器。' if ctrl.get('controller_revision') in ['r6','r7','r8','r9','r10','r11','r12','r13','r14','r15','r16','r17','r19','r20'] else '当前新派发以实际TrialConfig为准；17原生联验和不可变部署绑定另行记录，不能只凭TLS或旧joint=false文件判断。')
 retirement=root/'checks/old149-native-final-retirement-r8.json'
 if ctrl.get('controller_revision') in ['r6','r7','r8','r9','r10','r11','r12','r13','r14','r15','r16','r17','r19','r20'] and retirement.exists():
  backend_note='新准备、镜像检查/驻留/加载、staging、执行、Verifier及清理使用17私有SSD Engine59c8ba22-0aa4-4aed-bc43-4e1b5989fa22；部署绑定先于镜像检查和Ready。149控制器只保留原生Harbor收集副本，各Trial另存17 SSD全文件SHA副本。旧149正式Trial及原准备进程均已原生结束；最后一题为AgentTimeout10800秒/Reward0，失败记录保留。checks/old149-native-final-retirement-r8.json保留旧PID/子进程/锁身份、零本轮容器及最后Result以后零新增容器事件证据。'
 builder=progress.get('private17_build_service',{})
 build_note=('新构建服务已在同一私有Engine通过原生RUN、OCI全哈希导出、加载及运行验证；后续构建部署见configs/campaign-build17-r17.json。'+('旧有限准备器已自然终态，后续未构建任务使用私有Engine构建服务。' if progress.get('private17_build_preparation_handoff') else '旧有限准备器交接尚在收尾；现有构建和原生检查正常结束，后续冷构建已通过本轮专属归档目录门禁阻止沿旧构建器继续启动。') if builder else '原始上下文构建的实际Engine及SSD身份按逐题构建回执核对。')
 closure=root/'checks/CF_BASIC_500_CLOSURE_R7.json'
 basic_cf=json.loads(closure.read_text()) if closure.exists() else {}
 qualified=root/'checks/collection-qualification.json'
 q=json.loads(qualified.read_text()) if qualified.exists() else {}
 target_audit=progress.get('partial_primary_target_cache_audit',{})
 target_rows=[]
 for pool,stats in target_audit.get('pools',{}).items():
  for cutoff,view in stats['length_views'].items():
   target_rows.append(f"| {pool} | {cutoff} | {stats['qualified_independent_tasks']} | {view['assistant_targets']} | {view['cached_samples']} | {view['cached_samples_with_multiple_supervised_assistant_targets']} | {view['supervised_tokens']} | {view['normal_closure_last_target_retained']}/{stats['qualified_independent_tasks']} | {view['quarantined_targets']} |")
 emit('DATA_FREEZE_PROGRESS.md',f'''# 数据整理与冻结进度：partial

监控时间：{stamp}。以下为独立、不可变的合格主轨迹快照审计，源索引时间与持续更新的成功索引分别记录，不以此表代替最新全池统计。
阶段性证据：{target_audit.get('evidence','尚未观察')}；SHA：{target_audit.get('evidence_sha256','尚未观察')}。

| 池 | Qwen总长度上限 | 主轨迹独立Task | 保留Assistant目标 | 缓存样本/分段 | 含多个监督目标的样本 | 监督Token | 正常结束末目标保留 | 明确隔离目标 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
'''+ '\n'.join(target_rows)+'''

当前缓存采用每个真实可见上下文分段一条样本，样本数与分段数在这一存储布局中一一对应；独立Task、主轨迹、Assistant目标及含多个监督目标的样本单独统计。
缓存审计对全部输入/标签Token逐个核对：目标区间标签等于原Token，其余标签为-100；每个保留原Assistant目标恰好出现一次。长度使用Qwen缓存Token和正式processor额外Token及padding，包含input+target，不使用DeepSeek usage代替。
每条分段保存Task/Trial/Call、原前缀SHA、输入/标签SHA和原缓存文件SHA。每个Task的监督目标数、Token数及其在池内Token贡献单独保存；该贡献统计不引入新的训练损失加权政策。
14个历史Canary Task的28份长度视图缓存原件保留，在17 SSD另存逐SHA一致副本；当前stream目标缓存本已位于SSD。R139另已完成452个Task组合Arrow缓存的全量正式Loader/Collator与CPU手工loss/梯度参考，见checks/partial-combined-cache-r139/DATA_AUDIT_PARTIAL.json；这是冻结中间快照，不能代替全1000题最终语料验收。正式训练、原始Task、官方测试和Reward均未改动。
各Trial原有语义投影、正式Loader/Collator、stream/nonstream Serving及手工loss/梯度参考证明继续绑定到原始Recorder及缓存。最终组合语料的正式Loader全量验收及最终DATA_MANIFEST/DATA_AUDIT尚待全1000任务、有界尝试和剩余目标审计收尾；此处不是正式语料发布。
''')
 emit('TOOL_CONTRACT_FINAL.md',f'''# 最终11工具合同

检查时间：{stamp}。最终合同为 read, bash, edit, write, grep, find, ls, edit_patch, trajectory_read, bash_job, finish。
Finish、Background Jobs、toolResultBudget开启；Agent/Skill/Search关闭；timeBudget=0。

Teacher配置SHA：bf9069d53ec81d6f53a1a93f35bd61a0a8eadb42deafb4fc1c6540bf10afba2c。
Harness wheel SHA：c686ba3f429d8257a060cf6b6a6e4c5aa7d740f33b2d59180d9a2717b55d0db8。
实际工具Schema SHA：89ad662f58c4fe4df97187bae2c84ada041a8195b3ba9bfc0a6eccc909b66bfe。
System Prompt SHA：400cd2a6498f6f0b33dea4b15cdc6c2e8c75b450017aca7ea7e6045041fb6958。

有效预算阈值：maxCharsPerBatch=200000、previewChars=2000。
离线功能检查保留420000字符原始Observation、模型可见2279字符；包含卸载内容读取、错误工具调用语义、Finish、后台任务启动/等待/输出/取消检查。该功能证据为0模型调用。
两池真实8题Canary验收另见 checks/CANARY_GATE.json 及其中引用的逐Trial实际请求证据。Canary通过不等于16条成功。

DeepSeek官方直连服务deepseek-flash；Thinking enabled/max、context262144、output65536、stream=true、temperature1。服务Thinking模式忽略temperature，保留原请求值及实际语义。
压缩reserve81920/keepRecent20000/maxTurns0，辅助摘要同样Thinking max/output65536。
HTTP空闲120秒、Provider maxRetries3；后台并发2/输出20000000字节/keepProcesses=true/handoff600。
来源：checks/summary-r1-offline-teacher-contract.json、checks/CANARY_GATE.json、configs/teacher-native-11tools-summary-r1.json。
''')
 rows=[]
 for pool in ['calibforge','tmax']:
  v=q.get('pools',{}).get(pool,{})
  rows.append(f"| {pool} | 500 | {v.get('terminal_native_trials',0)} | {v.get('independent_tasks_with_terminal_trials',0)} | {v.get('raw_reward_one',0)} | {v.get('qualified_independent_tasks',0)} | {v.get('primary_trajectories',0)} |")
 emit('SAMPLING_STATUS.md',f'''# 采集快照：partial

时间：{stamp}。全局屏障已移除；逐题按原生环境证据验收后，由Harbor原生TrialQueue持续补位。未解目标及原始测试失败路径清理导致NOP超时的例外另行登记；这类旧NOP仍为超时、无Reward，不能称作Verifier通过或Reward0。参见checks/public-goal-deadlock-readiness-review-r47.json、checks/public-sensor-pipeline-readiness-review-r52.json及checks/original-verifier-failure-cleanup-review-r86.json。

| 池 | 计划唯一任务 | 审计索引终态Trial | 终态独立任务 | 原始Reward1 | 合格独立任务 | 主训练轨迹 |
|---|---:|---:|---:|---:|---:|---:|
'''+ '\n'.join(rows)+f'''

{attempt_note} 这不是API请求数或成功轨迹数；实时派发与终态审计有时间差，不能相减生成成功数。
冻结来源：CalibForge c2fae4c1f536461142b2a89a8b9423a8bc376088，两subset；TMax-15K e3ded940596cc611c9815684ba51a7e8ee0cffc9。seed42、固定家族split、TB2.1公开类别参照及去重证据见SAMPLING_MANIFEST与相邻清单。
未使用tmax-sft、TMax-SFT-16.5K、旧TB21教师或167未知Reward数据。
最多1000个教师任务/2000次尝试/每题2次；已找到的预算授权来源是用户上述任务上限，未在现有冻结配置中核实到独立USD硬上限。
已登记{len(bindings)}个精确分层候补绑定，{reserve_acceptances}个候补通过原生环境验收；仅由新控制器采纳后进入500个在用任务。逐Trial保存实际采样快照。旧失败、超时后Reward1、基础设施失效、模型合法零分及不可转换多模态分别保留。
候补的原始失败、分层/家族split、预登记顺序和原生验收SHA见manifests/SAMPLING_ACTIVE_BINDINGS_R4.json及后续追加R5；分别报告原选集和候补后技能/家族构成，不宣称相同标签代表相同分布。当前成功池分布见checks/collection-qualification.json。
API请求、压缩调用、Trial、独立Task、分段和目标采用各自分母。费用账本保存原始usage，模型描述符金额为估算，不能当成服务账单。
本轮语料尚不能正式冻结：需全部任务/有界尝试终态，精确成功索引，逐目标Qwen投影、正式Loader/Collator及完整收尾统计全部完成。
''')
 failures=[x for x in environment if x['status'] in ['ENV_FAILED','ENV_BLOCKED'] or x['runtime17_current_deployment_status'] in ['ENV_FAILED','ENV_BLOCKED']]
 emit('ENVIRONMENT_FAILURES.md',f'# 环境异常快照\n\n时间：{stamp}。以下按逐Task现有证据报告失败；历史环境结果与当前17部署结果分别记录于ENVIRONMENT_1000_STATUS.csv。历史验收不代表当前17全部Ready；原始失败证据保留，新验收不会覆盖旧记录。\n\n'+
  '\n'.join(f"- {x['pool']} / {x['task_id']}：历史{x['status']} / 当前17{x['runtime17_current_deployment_status']} / {x['basic_preparation']}；{x.get('runtime17_current_reason') or x['reason']}；证据 `{x.get('runtime17_current_evidence') or x['evidence']}`。" for x in failures)+'''

历史处理记录（具体当前状态以逐Task CSV与新回执为准）：

已确认的原始问题包括：000176的Git所有权限制、000552原环境只装客户端但初始测试要求数据库服务、000886原镜像输入图未能生成。三题同分层预登记候补已完成基础准备与原生安装/NOP Verifier验收，等待唯一控制器安全交接后采纳；未替换任何已尝试任务。
四题预检容器名称碰撞已在独立命名空间复查恢复；000173经原始container.def精确哈希确认四个公开/tests/corpus输入，已完成原生上传/NOP Reward0验收，没有向教师开放官方测试。
首次流式诊断中的默认Docker网段耗尽属于共享基础设施资源问题，不能归因于模型或原始任务；本轮专属/28网段已另行8路验收。中止的诊断均为0教师调用，保留原始Result。
后续新发现问题以逐Task原始日志为准；不会修改官方测试或伪造Fixture。
三题NOP的缺模块报错对应公开instruction要求创建的输出模块，独立复核保留于checks/native-environment-reviews-r10，原始失败分类未覆盖。此ENV_READY表示环境已通过，当前r3控制器缓存仍待安全交接后采纳；不是教师成功。
R10曾将scientific-computing_20260419_023954_006也判为就绪，该判断已由R11撤回：镜像为系统Python安装NumPy，而官方Verifier以uvx Python3.13运行，只声明pytest/ctrf依赖，并用python3启动任务子进程。评分解释器隔离依赖尚未证明正确，现为ENV_BLOCKED。该题没有教师派发，原始Trial/Reward及旧复核均保留，未修改官方脚本。
CalibForge software-engineering_20260507_093408_003的原始镜像内有六个/tests/test_*.py文件。只读实测已保存文件清单和SHA；未宣称它们与官方评分测试相同。公开instruction没有指定这些文件为必需公开输入，当前可信测试边界未明，记ENV_BLOCKED；无教师尝试，不修改官方镜像，也不向教师开放这些测试。
TMax task_009921_1b294fdc首轮原生构建遇到APT502，后续缺Python/pip。原上下文、首轮失败日志及SHA均保留；只对该题原样重新构建一次，跳过该题失效的构建缓存，没有删除共享缓存。新镜像经完整manifest/config/layer/DiffID哈希核验后，进入独立原始初始测试及原生CLI/NOP检查。最终状态以CSV与stream/tmax-original-network-recovery-r6/environment-outcomes为准；这不是候补或模型失败重试。
TMax task_002302_735aa57d与task_001883_953510f4此前因镜像源403未完成构建；已在17以原始上下文重建，并在149通过原始初始测试、CLI安装和官方NOP Verifier。原题身份、失败日志及官方文件保留，0教师调用，不是候补替换。
TMax task_001934_29de52e9除原始Git所有权初始测试失败外，原镜像还包含未公开的正确总和侧文件。可信原生探针只验证文件存在和可读权限，没有读取其答案内容；记ENV_BLOCKED并禁止派发。新源检查覆盖当前500个TMax任务，499通过既有检查加新增规则，1题命中该规则。三处secret/expected路径命中经原始instruction和源码复核是公开输入、提取目标或公开样例，不据此冒充环境已就绪；词法检查也不被宣称为全部语义泄漏的证明。候补已按预登记精确分层选定，原Task、镜像和测试不修改。
''')
 recipe=root/'checks/TRAINING_RECIPE_B32_E5_R2.json'
 if recipe.exists():
  training=json.loads(recipe.read_text())
  policy_path=Path(training['data_and_serving_policy']['path'])
  if hashlib.sha256(policy_path.read_bytes()).hexdigest()!=training['data_and_serving_policy']['sha256']:raise ValueError('Prepared student data/serving policy changed')
  emit('TRAINING_CONFIG_LOCK.md','# 新M1/M2配置锁：等待数据与GPU验收\n\nLR1e-5、全局Batch32、5epochs、BF16 mixed、FP32 master/Adam要求、AdamW/Cosine/warmup5%/WD0、Full Thinking+Action。\n\n四份R2候选通过LlamaFactory参数类的CPU校验（显式覆盖use_cpu、do_train/do_eval、bf16和deepspeed；不是GPU配置验收），R1旧文件保持原SHA。256K先实际验收，失败才使用128K。计划DP4时GA8；正式启动前必须测量真实DP组D并核验GA=32/D。CPU解析不能替代GPU精度/长上下文验收。\n\n'+ '\n'.join(f"- {v['stage']} / {v['context']}：`{v['path']}`，SHA `{v['sha256']}`。" for v in training['configs'])+'\n\n未启动训练；合格成功语料冻结与GPU验收均为必要门禁。M1从固定原始Qwen权重初始化，M2从对应M1输出初始化。\n')
  with (root/'TRAINING_CONFIG_LOCK.md').open('a') as stream:
   stream.write('\nR2待用学生运行清单：`'+training['student_runtime']+'`；十一工具/Finish开启合同：`'+training['student_tool_contract']+'`。旧十工具清单是保留的旧候选，R2不引用它。\n\n固定tokenizer资源：`'+training['canonical_tokenizer_resource']+'`，backend语义SHA：`'+training['canonical_backend_semantics_sha256']+'`。M1从同一原权重的规范加载资源初始化，M2从匹配M1输出初始化；M1保存后M2加载和Serving显式tokenizer路径均通过CPU语义复核。Serving必须显式采用该tokenizer_path、qwen3 reasoning parser及qwen3_coder工具parser，使用同一官方历史Thinking政策。真实学生服务联验、GPU精度/长上下文、实际DP组及最终语料冻结仍待完成；未启动训练。\n')

 emit('CONTROLLER_AND_MONITOR_STATUS.md',f'''# 控制器与20分钟监控

时间：{stamp}。唯一写教师控制器PID：{ctrl.get('pid')}；实际PID存活：{ctrl.get('actual_pid_alive')}；状态：{ctrl.get('status')}。
唯一采集控制器以原生生命周期钩子限制实际教师Trial最多8个，原生安装缓冲最多额外8个；安装、镜像准备与NOP不计作教师。独立0模型调用环境预检使用各自有限并发，下面单列。Task agent时限按max(原始值,10800)，原始资源和Verifier时限保留。
旧的WAITING_FOR_CANARY_AND_ALL_1000_ENVIRONMENTS门禁已解除。当前ENV_READY计数：{json.dumps(counts,ensure_ascii=False)}。
1000题是否全部完成检查：{progress['all1000_environment_checks_terminal']}；CSV中的ENV_CHECK_PENDING是诚实的中间状态，不能当成最终ENV_READY/FAILED/BLOCKED。
CalibForge全500题基础检查结果：{json.dumps(basic_cf.get('counts',{}),ensure_ascii=False)}。此处基础检查与上面的完整ENV_READY、教师Reward及训练资格是不同验收层级。
独立原生环境预检：{json.dumps(progress.get('independent_native_environment_preparation',{}),ensure_ascii=False)}。CF原选任务检查不是候补，也不是教师尝试。

{backend_note} {build_note} CalibForge固定官方镜像直接归档到17 SSD。镜像归档通过Hash后仍须原始初始测试、原生安装及NOP Verifier验收，不能计作ENV_READY。
全1000题的当前环境层级、实际逐题证据及本轮17验收进度见ENVIRONMENT_1000_STATUS.csv；历史缺失206题CF基础检查、142题TMax初始检查的旧计划保留原清单，不再充当当前待检查数量。CF基础检查、完整原生ENV_READY、教师Reward及最终训练资格分别统计。
原始TMax初始检查在17使用冻结原生转换器生成的启动命令、原始HOME/工作目录、原始CPU/RAM及可信只读初始测试挂载。环境检查与镜像准备各有界，不占教师名额；17初始通过仍须后续正式CLI安装与官方Verifier验收。
17的构建器限定4CPU/16GiB、无GPU请求；只使用本轮专属SSD目录，不改变共享Docker默认数据目录。167的大容量挂载无当前用户写权限，未在其中写环境。Windows/本地不运行环境构建或大镜像下载。
部分准备的当前原因：149普通镜像准备进程已因磁盘保护线停止；历史PREPARING状态文件不能证明其仍存活。17的公开归档、原始TMax构建及CF基础启动检查独立推进，依实际PID、逐Task回执和时间差确认。旧全局门禁与旧工具配置均不是当前暂停原因；单题源环境、Verifier及清理问题保留各自分类。
{handoff_note}
实际当前控制器scope：{active_scope}。旧交接器未成立的SIGSTOP判断已经独立核实；确认全部旧生命周期结束、无遗留容器后，已退出旧空闲控制器并取得唯一写锁。证据见checks/controlled-idle-handoff-r5.json；旧交接状态文件保留为历史，不能用作当前等待理由。
原生Agent阶段占槽及补位观测：{json.dumps(progress.get('teacher_slot_telemetry',{}),ensure_ascii=False)}。
真实模型活动证据：{json.dumps(progress.get('live_teacher_model_evidence',{}),ensure_ascii=False)}。
AGENT_START名额包含CLI启动准备和首个模型事件之前的时间；原生占槽数不能直接宣称为8个已观测模型。真实8并发须单列Recorder/Provider事件及稳定活动集合证据。当前版本使用Harbor原生AGENT_START钩子在安装完成后占用全局教师名额，在原生AGENT_END释放名额；Verifier、Recorder收集和清理使用独立的原生生命周期容量。额外有界安装缓冲和独立环境预检不计入教师并发；不以pipeline数量替代8个实际教师。当前版本同时计入全部前代尚未END的教师，完成到补位的逐次间隔单独保存于teacher-lifecycle.jsonl。
CF原选500份冷归档已在17完成原始manifest/config/layer/DiffID全哈希和展开大小检查；TMax已实测149保存到17、原镜像删除后精确恢复、错误传输SHA拒绝。CF也已实测同样的原生Docker删除/恢复。仅释放有完整冷备、无容器引用的本轮镜像缓存，不删除原Task/Verifier/Trial/Recorder/归档，不做全局prune。
模型始终使用冻结官方服务直连；公开镜像与依赖下载使用17既有代理，未传入教师进程。
已有qwen35-tb21-monitor.timer保持唯一，observe_collection.py记录原生队列、全1000题CSV、准备worker、CPU磁盘、API/Reward/Recorder审计状态、授权GPU UUID/进程所有者及20分钟差值。
对照20分钟前最近可用快照的差值及实际观测间隔：{json.dumps(progress['twenty_minute_delta'],ensure_ascii=False)}。巡检曾因入口15秒总时限而遗漏刷新；修复证据见checks/collection-monitor-hook-repair-r1.json，未将长间隔变化冒充精确20分钟变化。
监控为只读，不凭Timer运行推断采集推进。远端tmux、SSH agent和现有17连接均不依赖WSL/Codex会话存活。
''')
 artifacts=['ENVIRONMENT_1000_STATUS.csv','ENVIRONMENT_FAILURES.md','TOOL_CONTRACT_FINAL.md','SAMPLING_STATUS.md','TRAINING_CONFIG_LOCK.md','CONTROLLER_AND_MONITOR_STATUS.md','DATA_FREEZE_PROGRESS.md',
  'manifests/SAMPLING_MANIFEST.json','checks/CANARY_GATE.json','checks/isolated-network-capacity-r4.json','checks/stream-controller-r3-offline.json',
  'checks/TRAINING_RECIPE_B32_E5_R2.json','checks/collection-qualification.json','checks/tmax-remaining-ssd17-r3.json',
  'checks/tmax-cleanup-receipt-preservation-r7.json','checks/tmax-missing-receipt-recovery-r7.json',
  'checks/tmax-ssd17-import-preflight-campaign-r3.json','checks/public-asset-worker-149-to17-handoff-r5.json','progress.json']
 artifacts.extend(['checks/native-nop-module-error-review-r10.json','checks/qualified-public-image-cache-release-r9.json','manifests/CF_REMAINING_ORIGINAL_BASIC_SSD17_R6.json'])
 artifacts.extend(['manifests/TMAX_REMAINING_INITIAL_SSD17_R7.json','checks/cf-basic-ssd17-r6-acceptance.json'])
 artifacts.extend(['checks/tmax-initial-ssd17-r7-acceptance.json','checks/cf-native17-basic-boundary-runtime-r8.json'])
 artifacts.extend(['checks/CF_BASIC_500_CLOSURE_R7.json','manifests/CF_CANONICAL_TIMEOUT_RECHECK_SSD17_R7.json'])
 artifacts.extend(['checks/CF_BASIC_500_CLOSURE_R7_CURRENT_LOCATORS.json','checks/admission-capacity-hold-r1.json',
  'checks/capacity-held-cf-image-eviction-r1.json','checks/capacity-held-cf-image-eviction-r1-reconciliation.json',
  'checks/native-cold-tmax-restore149-acceptance-r1.json','checks/native-cf-cold-release-restore149-r4-acceptance.json',
  'checks/native-tmax-resident-archive-r1.json','manifests/SAMPLING_ACTIVE_BINDINGS_R4.json',
  'checks/collection-r4-promotion-ready.json','checks/collection-r4-idle-handoff.json','checks/stream-r4-data-audit-worker.json'])
 artifacts.extend(['checks/native-tmax17-cold-release-restore149-r4-acceptance.json',
  'checks/collection-r4-additional-native-image-acceptance.json','checks/cf500-cold-image-size-audit17-receipt.json',
  'checks/collection-r4-admission-and-native-config-acceptance-r2.json','checks/stream-r4-data-worker-handoff.json'])
 artifacts.extend(['checks/capacity-window-tmax-admission-r2.json','checks/collection-monitor-hook-repair-r1.json'])
 artifacts.extend(['checks/collection-monitor-service-execution-acceptance-r2.json',
  'checks/prelaunch-controller-revision-r4b/revision.json','checks/collection-r4b-native-config-acceptance.json',
  'checks/collection-r4b-admission-tests.log','stream/environment-preflight-r5/PLAN.json',
  'stream/environment-preflight-r5/state.json','stream/environment-preflight-r5/TERMINAL.json',
  'manifests/TMAX_INITIAL_STATE_RESERVE_PLAN_R5.json','checks/tmax-initial-state-reserve-source-r5.json',
  'stream/tmax-initial-reserve-acceptance-r5/PLAN.json','stream/tmax-initial-reserve-acceptance-r5/original-build-receipt.json',
  'stream/tmax-initial-reserve-acceptance-r5/original-initial-state.json','manifests/SAMPLING_ACTIVE_BINDINGS_R5.json'])
 artifacts.extend(['checks/tmax-original-network-recovery-resolver-acceptance-r5.json',
  'checks/tmax-original-build-network-recovery-r5/task_009921_1b294fdc.json',
  'stream/tmax-original-network-recovery-r6/PLAN.json',
  'stream/tmax-original-network-recovery-r6/original-network-recovery-build.json',
  'stream/tmax-original-network-recovery-r6/original-initial-state.json',
  'stream/tmax-original-network-recovery-r6/cold-image-identity.json',
  'stream/tmax-original-network-recovery-r6/native-image-release.json',
  'stream/tmax-original-network-recovery-r6/environment-outcomes/task_009921_1b294fdc.json',
  'checks/active-native-long-task-health-r5.json'])
 artifacts.extend(['manifests/TMAX_ORIGINAL_MIRROR403_RECOVERY_R7.json',
  'stream/tmax-original-infra-recovery-r7/PLAN.json','stream/tmax-original-infra-recovery-r7/state.json',
  'stream/tmax-original-infra-recovery-r7/environment-outcomes/task_002302_735aa57d.json',
  'stream/tmax-original-infra-recovery-r7/environment-outcomes/task_001883_953510f4.json',
  'checks/tmax-computed-sidecar-native-boundary-r7.json','checks/tmax500-computed-sidecar-boundary-acceptance-r7.json',
  'checks/task-source-boundary-reviews-r7/task_001934_29de52e9.json',
  'checks/prelaunch-source-boundary-revision-r4c/revision-start.json',
  'checks/collection-r4c-source-boundary-and-native-config-acceptance.json',
  'checks/collection-r4c-boundary-and-admission-tests.log','checks/collection-r4c-boundary-and-admission-tests-r2.log',
  'manifests/TMAX_PRIVATE_SIDECAR_RESERVE_PLAN_R8.json','manifests/TMAX_PRIVATE_SIDECAR_RESERVE_CANDIDATE_R8.jsonl',
  'checks/tmax-private-sidecar-reserve-source-r8.json'])
 artifacts.extend(['checks/collection-idle-handoff-actual-predicates-r5.json','checks/controlled-idle-handoff-r5.json',
  'checks/actual-teacher-slots-r5-native-contract.json','checks/actual-eight-teacher-overlap-r5-initial.json',
  'checks/USER_AUTHORIZED_IMAGE_BANDWIDTH_POLICY_R1.json','checks/image-bandwidth-live-acceptance-r1.json',
  'stream/collection-r4/CAMPAIGN.json','stream/collection-r4/teacher-lifecycle.jsonl'])
 artifacts.extend(str(p.relative_to(root)) for p in sorted((root/'checks').glob('actual-teacher-eight-and-backfill-r5-*.json')))
 artifacts.extend(['stream/tmax-resident-buffer-preflight-r1/PLAN.json','stream/tmax-resident-buffer-preflight-r1/state.json',
  'checks/full-native-ready-small-tmax-warm-r1-plan.json','checks/private17-native-ssh-client-policy-r1.json'])
 artifacts.extend(['checks/private-ssd-engine17-original-resource-acceptance-r2.json','checks/private17-native-ssh-dial-r3.json',
  'checks/private17-native-task-acceptance-r1.json','checks/private17-native-task-acceptance-r2.json',
  'checks/private17-native-task-acceptance-r3.json','checks/private17-dependency-index-policy-r3.json',
  'manifests/TMAX_ORIGINAL_REGISTRY_EOF_RECOVERY_R9.json',
  'checks/private17-native-preflight-network-recheck-r2.json','checks/image-bandwidth-native-arguments-live-r5.json',
  'checks/collection-monitor-lightweight-counter-r5.json','checks/collection-monitor-profiled-cpu-fix-r5.json',
  'checks/collection-monitor-hook90-budget-r5.json','checks/collection-monitor-hook90-service-acceptance-r5.json',
  'ACTUAL_TEACHER_EIGHT_ACCEPTANCE_R5.md'])
 artifacts.extend(['checks/data-audit-r5-handoff-start.json','checks/data-audit-idle-handoff-r5.json',
  'checks/data-audit-queue-r5-offline-acceptance.json','checks/student-target-audit-storage-migration-r5.json',
  'manifests/SAMPLING_ACTIVE_BINDINGS_R8.json','manifests/CAMPAIGN_PRIVATE17_BACKEND_R1.json',
  'stream/tmax-original-registry-acceptance-r9/PLAN.json','stream/tmax-original-registry-acceptance-r9/state.json',
  'checks/private17-native-task-acceptance-r4.json','checks/private17-canary-registration-r4.json',
  'checks/private17-native-task-acceptance-r7.json','checks/private17-canary-registration-r7.json',
  'manifests/PRIVATE17_UNATTEMPTED_RECOVERED_ORIGINAL_CANARY_R7.json',
  'checks/task-legacy-configuration-holds-r1/task_007206_2ea22c7f.json'])
 artifacts.extend(['checks/private17-terminal-joint-acceptance-r3.json','checks/private17-actual-teacher-metadata-r1-20261030T151516Z.json',
  'manifests/CAMPAIGN_PRIVATE17_BACKEND_R2.json','checks/deployment17-r6c-offline-acceptance.json','checks/deployment17-r6c-source-promotion.json',
  'configs/campaign-deployment17-r6c.json','configs/private17-public-dependency-index-r6c.json','checks/controller-r5-admission-fence-r6.json',
  'checks/CURRENT_DISPATCH_AUTHORITY_R6.json','checks/fenced-handoff17-preimport-exec-recovery-r6.json',
  'checks/attempt-environment-only-reconciliation-r6.json','stream/collection-r4/deployment-r6c/CAMPAIGN.json','stream/collection-r4/deployment-r6c/state.json',
  'stream/collection-r4/deployment-r6c/PREFLIGHT_PLAN.json','stream/collection-r4/deployment-r6c/PREFLIGHT_TERMINAL.json'])
 artifacts.extend(str(p.relative_to(root)) for p in sorted((root/'checks').glob('actual-teacher-eight-and-backfill-r6-*.json')))
 artifacts.extend(str(p.relative_to(root)) for p in sorted((root/'checks').glob('attempt-ledger-evidence-r6-*.json')))
 artifacts.extend(['checks/deployment17-r7b-offline-and-resource-acceptance.json','checks/deployment17-r7b-source-promotion.json',
  'checks/controller-r6-admission-fence-r7.json','checks/CURRENT_DISPATCH_AUTHORITY_R7.json',
  'configs/campaign-deployment17-r7b.json','stream/collection-r4/deployment-r7b/CAMPAIGN.json','stream/collection-r4/deployment-r7b/state.json',
  'checks/campaign17-independent-ssh-auth-r6.json','checks/native17-bounded-ssh-masters-r6b.json',
  'checks/initial-probe-log-history-integrity-r7.json','checks/monitor-active-selection-cache-r6.json',
  'checks/owned-docker-events149-r7.json','checks/owned-docker-events149-r7.jsonl','ACTUAL_TEACHER_EIGHT_ACCEPTANCE_R7.md'])
 artifacts.extend(str(p.relative_to(root)) for p in sorted((root/'checks').glob('actual-teacher-eight-and-backfill-r7-*.json')))
 artifacts.extend(str(p.relative_to(root)) for p in sorted((root/'checks').glob('private17-actual-teacher-metadata-r7-*.json')))
 artifacts.extend(str(p.relative_to(root)) for p in sorted((root/'checks').glob('deployment17-rollout-acceptance-r7-*.json')))
 artifacts.extend(['checks/legacy-resident-preparation-admission-fence-r7.json','checks/legacy-resident-preparation-retired-r7.json',
  'checks/collection-monitor-r7-updated-hook-service-acceptance.json','checks/native-structural-cache-r7-acceptance.json',
  'checks/qualification-scope-cache-activation-r6.json','checks/qualification-native-cache-activation-r7.json',
  'checks/direct17-context-staging-r13.json','manifests/TMAX_UNSTARTED_DIRECT_SSD17_R13.json',
  'stream/direct17-native-source-r13/PLAN.json','stream/direct17-native-source-r13/state.json',
  'checks/direct17-r13-native-admission-fence-r14.json','checks/direct17-r14-native-config-path-acceptance.json',
  'stream/direct17-native-source-r14/PLAN.json','stream/direct17-native-source-r14/state.json',
  'stream/private17-original-network-acceptance-r10/state.json','DEPLOYMENT17_ACCEPTANCE_R8.md'])
 artifacts.extend(['checks/private17-buildkit-r16-acceptance.json','configs/campaign-build17-r17.json',
  'checks/private17-cold-build-directory-fence-r20.json','checks/private-builder-tmux-stop-root-cause-r20.json',
  'checks/direct17-build-preparation-handoff-r17.json','checks/direct17-private-builder-r17-launcher.json',
  'stream/direct17-native-source-r13/TERMINAL.json','stream/direct17-native-source-r14/TERMINAL.json',
  'stream/direct17-native-source-r17/PLAN.json','stream/direct17-native-source-r17/state.json',
  'checks/derived-reader-activation-r8.json','checks/attempt-counter-r8-current-parity.json',
  'checks/controller-r8-offline-acceptance-r3.json','checks/controller-r8-reader-lifetime-acceptance-r3.json',
  'checks/controller-r7-staging-admission-fence-r8.json','checks/controller-r7-admission-fence-r8.json',
  'checks/CURRENT_DISPATCH_AUTHORITY_R8.json','stream/collection-r4/deployment-r8/CAMPAIGN.json',
  'stream/collection-r4/deployment-r8/state.json',
  'checks/attempt-counter-r8-boundary-acceptance.json','checks/incremental-export-r8-real-canonical-equivalence.json',
  'checks/qualification-reader-r8-validator-acceptance.json',
  'checks/partial-primary-target-audit-r136/PARTIAL_DATA_TARGET_AUDIT_R136.json',
  'checks/partial-primary-target-audit-r136/CALIBFORGE_PARTIAL_DATA_MANIFEST_R136.json',
  'checks/partial-primary-target-audit-r136/TMAX_PARTIAL_DATA_MANIFEST_R136.json'])
 artifacts.extend(str(p.relative_to(root)) for p in sorted((root/'checks').glob('actual-teacher-eight-and-backfill-r8-*.json')))
 emit('EVIDENCE_INDEX.md','# 证据索引：partial\n\n时间：'+stamp+'。最终语料尚未冻结。远端原始数据不复制进Git；本地仅同步小型报告和身份清单。\n\n'+ '\n'.join(f"- [{name}]({name}) SHA `{hashlib.sha256((root/name).read_bytes()).hexdigest()}`" for name in artifacts if (root/name).exists())+'\n\n原始Trial/Recorder：jobs/ 与 stream/collection-r3/trials/；原始请求/响应、Thinking、Observation、压缩事件与完整工具输出保持原件。新语料独立发布，训练样本只消费按时间首个合格成功索引。\n')
