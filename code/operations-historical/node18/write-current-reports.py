"""Render evidence-backed partial reports; no dispatch and no completion inference."""
import hashlib
import importlib
import json
from pathlib import Path
from datetime import datetime,timezone

L=Path(__file__).resolve().parent
OUT=L/'reports';OUT.mkdir(exist_ok=True)
F=L/'frozen-metadata'
R='/ssd/chenkeyi/qwen35-sft-772-20261101'
S='/data/chenkeyi/qwen35-sft-772-20261101'
def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(name,text):(OUT/name).write_text(text.strip()+'\n')
data=read(F/'DATA_AUDIT.json');release=read(F/'DATA_RELEASE.json')
mf=read(F/'FROZEN_772_CORPUS_MANIFEST.json')
status=read(L/'checks/CURRENT_EXECUTION_STATUS.json')
run=status['formal_runs']['new-m1-cf416-128k-e5']
native=read(L/'checks/NATIVE_TRAINING_READOUT_R1.json')
native_m1=native['stages']['new-cf416-m1'];native_m2=native['stages']['new-cf416-tmax356-m2']
step=native_m1['actual_optimizer_step_rank0'];step2=native_m2['actual_optimizer_step_rank0'];metrics=native_m1.get('latest_metrics')
checkpoints=run['native_checkpoint_names']
e1_path=L/'checks/NEW_M1_EPOCH1_NATIVE_ACCEPTANCE.json'
e1=read(e1_path) if e1_path.exists() else None
nll_path=L/'checks/NLL_AUDIT_COMPLETE.json'
e1nll=read(nll_path) if nll_path.exists() else None
when=datetime.fromtimestamp(native['checked_at'],timezone.utc).isoformat()
pool={n:read(F/n/'DATA_MANIFEST.json') for n in ['calibforge','tmax']}
rows=[];coverage=[];classes={};stages={}
for n,d in pool.items():
    for split in ['train','validation']:
        v=d['length_views']['131072'][split]
        rows.append(f"| {n} {split} | {v['retained_independent_tasks']} | {v['segments']} | {v['multi_assistant_samples']} | {v['retained_targets']} | {v['supervised_tokens']:,} |")
        for key,num in v['supervision_token_classes'].items():classes[key]=classes.get(key,0)+num
        for key,num in v['stage_target_counts'].items():stages[key]=stages.get(key,0)+num
for context in ['262144','131072']:
    vs=[d['length_views'][context][s]for d in pool.values()for s in ['train','validation']]
    coverage.append('| '+context+' | '+' | '.join(str(sum(v[k]for v in vs))for k in ['retained_independent_tasks','complete_tasks','closing_tasks','segments','retained_targets','supervised_tokens','input_plus_target_qwen_tokens'])+' |')
write('CF416_TMAX356_DATA_AUDIT.md',f'''
# CF416/TMax356 数据验收

状态：数据已冻结；训练和评测结果另列。数据Release SHA：`{sha(F/'DATA_RELEASE.json')}`。

773条合格原始成功轨迹对应772个独立任务；每题取按时间顺序第一条合格成功，额外同题成功单独保留。CF416，TMax356。固定家族拆分：CF374 Train/42 Validation，TMax325/31，共699/73。772包含验证集，不能全部宣称训练曝光。

| 语料与拆分（128K） | 独立任务 | 分段/样本 | 多Assistant样本 | 监督目标 | 监督Token |
|---|---:|---:|---:|---:|---:|
{chr(10).join(rows)}

| Context | 保留任务 | 完整任务 | 保留收尾任务 | 分段 | 目标 | 监督Token | 全部input+target+processor+padding |
|---|---:|---:|---:|---:|---:|---:|---:|
{chr(10).join(coverage)}

256K有185条样本超过128K。128K隔离3886个超长目标；772任务仍各有合法样本，但只有670个任务保留完整决策、694个保留收尾。没有截断原文，没有把完整任务数、独立任务数、分段数混报。

128K监督分类：`{json.dumps(classes,ensure_ascii=False)}`；阶段目标：`{json.dumps(stages,ensure_ascii=False)}`。按原生样本均值训练，无自定义任务权重；逐任务分段份额在两份DATA_MANIFEST中保留，不假称均匀任务权重。

全部Task/Trial/Call、原始Reward=1、Verifier完成、资格/闭合/Recorder身份和源SHA已核验。最终11工具及System Prompt覆盖30193个真实Payload。Compaction和预算化Observation按真实可见上下文投影；每个保留Assistant目标监督一次，重叠历史只输入。原始Recorder继续保留149/17。

固定CF revision `c2fae4c1f536461142b2a89a8b9423a8bc376088`，TMax-15K revision `e3ded940596cc611c9815684ba51a7e8ee0cffc9`。原家族split保留，772 vs TB89、跨池精确/近重复和模板检查无候选命中；此结论限冻结审计算法，未使用模型成败挑数据。

实际LF Loader/Collator读全量最终缓存并逐Token检查labels通过，30193个原生SGLang前缀逐目标通过。独立数值参考的具体精度范围见QWEN35_PREFIX_AND_SFT_CORRECTNESS.md，不能把全部严格梯度容差宣称已通过。另有只读分类位置索引，对两种Context的全部保留目标逐Token核对并与Manifest分类总量一致；冻结缓存未修改。

最终SSD根：`{R}/frozen-data-772-r3`；SHA一致的Ceph封存：`{S}/frozen-data-772-r3`，825文件、4,624,099,719字节。冻结文件中的“尚未训练”等字段记录冻结当时，当前训练状态以执行日志为准。
''')
write('QWEN35_PREFIX_AND_SFT_CORRECTNESS.md',f'''
# Qwen前缀与SFT正确性

固定M0 revision：`851bf6e806efd8d0a36b00ddf55e13ccb7b8cd0a`。Tokenizer SHA `5f9e4d4901a92b997e463c1f46055088b6cca5ca61a6522d1b9f64c4bb81cb42`；官方模板SHA `a4aee8afcf2e0711942cf848899be66016f8d14a889ff9ede07bca099c28f715`。

30193/30193真实目标的训练前缀与原生SGLang前缀严格一致，0不一致。空Thinking BPE修复已集成；最终数据使用真实Provider分段历史，不补造Compaction之前历史。LF增加的masked占位在两池真实4B样本上不改变可见Token隐藏状态（差值0）。所有缓存、两种Context、原固定Train/Validation经正式Loader/Collator逐标签检查；System/User/Observation/pad不监督，保留目标恰好一次。

36852次工具调用全部通过原生流式及非流式Qwen解析，工具名/参数语义0差异，原始失效工具调用也保留。11工具、toolResultBudget和原System Prompt已对全部Payload核验。5条历史配置在未使用的summary字段有差异，全部实际调用仍同一主协议，未隐瞒配置身份。

实际完整CLI试跑有16次模型调用、16次工具调用、0工具错误、正常finish闭合；120次历史Thinking回放检查及16个实际GPU请求前缀通过。scratch文件期望末尾换行但模型未写入，fixture失败原样保留；协议可转换与模型完成具体任务分开，未宣称任何官方Reward。

独立数值参考：CPU小模型的手工causal-shift Loss和全部梯度通过；真实4B两池FP32 Head参考与BF16 native全梯度相对差约2.35%，在原R1的3%范围内。更严R2的0.5%范围未通过，不能改写为通过。Head隔离R4：真实隐藏状态、BF16/FP32两种计算，手工CE和Liger Loss误差≤1.2e-7；Head输入/权重梯度满足固定上游逐元素容差。同一原生Forward/Backward重复基线也出现CF2.0676%、TMax1.9300%的梯度差，Loss和隐藏状态差为0；这与原生BF16后向数值波动相符，具体Kernel尚未单独定位。没有改变训练精度设置，严格容差失败保留。详见checks/QWEN_HEAD_PRECISION_ISOLATION_R4.json和保留的R1/R2/R3日志。

实际DP4/GA8长样本原生训练、FP32 Master/Adam、保存、全新进程恢复2→3已通过，四卡峰值allocated 61.66GiB。256K八卡真实FLA backward OOM，未产生可恢复256K更新。训练源码 `6f3cae79028b5c2d313a3cd35ee7e7473c9b2f42`，冻结source SHA `293ba2a7dca8569bb39e11bc0137a0e1180a0391402f10d49ff5b4ad00ce6c93`。

Serving工具Schema规范化只保留实际提供字段并排序JSON键。Epoch3固定R4 Transport wheel SHA `3eaeafa4397d5a3284576b8b739a7f79f52311b724fdffc90e8b6f6ccc6e21b4`，79离线测试通过；仅3个Transport/types/config文件相对教师wheel改变，工具、Prompt、Agent Loop、Recorder未改。教师服务/旧历史不改写。训练Transformers5.8；Serving5.3/SGLang0.5.10，模板语义及实际Token前缀已对照，不假称版本号相同。

Epoch3首批两个真实Trial的Provider Payload已核对：11工具，toolResultBudget开启，context262144、max_tokens81920、stream=true，temperature1、top_p0.95、top_k20、min_p0、presence_penalty1.5、repetition_penalty1。冻结Qwen ModelSpec把请求级max映射为wire reasoning_effort=high，同时显式传入chat_template_kwargs.enable_thinking=true；这是学生Serving的实际语义，不作为DeepSeek教师max合同的证据。实际wire工具Schema SHA为9b14204af97deda8b282e969ebbba410490505423912b2bd509896025b50b59f。

正式三模型统一采用R5 wheel `1d27eef1ca6696275f306d8c653f7a266a4c7aea7321f0d47fd01b739c27fa18`，源码commit `ae1403262b8d2ae8a9732c2d00ab622bb6891c40`。相对R4只改Controller的连续超限恢复边界，178个运行时Python文件中仅baseline.py不同；模型Transport、工具、Prompt、Agent Loop与Recorder逐字节不变。源码和独立安装wheel各通过80项相关测试；另有完整安装CLI的6项HTTP故障注入联验，包含11工具真实执行、预算化Observation、Compaction及Finish，均通过。不改变context、output、reserve或采样参数。旧R4的NEW-M1九题诊断原样保留，未启动的旧R4 NEW-M2不派发；新的18条E3诊断使用同一R5，只有这些结果可与正式E5比较。可比读器R4逐条核对实际Wheel SHA；此前跨Harness版本的R3比较仅作历史。

首个真实E3 Result保留官方Reward0、Verifier return_code0和NonZeroAgentExitCodeError。Recorder物理完整，但Agent未正常闭合，后续独立上下文超限未恢复。新版只读审计单列工程退出；原始Reward和旧R1统计不改写。完整Recorder账本input11,870,136、output180,629、reasoning125,766、total12,050,765；Harbor原计数7,728,668/86,092另存，不能混用。两个HTTP400错误响应的零usage不宣称为Provider实报费用。证据为checks/NEW_M1_EPOCH3_NATIVE_TRIALS_LIVE_ACCEPTANCE_R1.json；该记录只证明真实启动和协议，不宣称Verifier成功。
''')
importlib.import_module('render-native-training-reports-r1').render(L)
importlib.import_module('render-evaluation-reports-r1').render(L)
write('OLD_M2_FOUR_ARM_COMPARISON.md',(L/'checks/OLD_FOUR_REPORT_SNAPSHOT_R1.md').read_text())
write('EXECUTION_AND_RESOURCE_STATUS.md',f'''
# 执行与资源状态

最近采样：{when}。原生阶段：{(status.get('native_advance')or{}).get('status')}。NEW-M1 {step}/200步、5Epoch及HF验收={native_m1['five_epochs_completed_and_final_hf_admitted']}；NEW-M2 {step2}/125步、5Epoch及HF验收={native_m2['five_epochs_completed_and_final_hf_admitted']}。评测和旧研究另据真实Trial及Checkpoint终态报告。

17/18的`/data/chenkeyi`和`/data/models/Qwen/Qwen3.5-4B`为同一Ceph挂载，SHA/跨节点锁已核实；`/ssd`和`/home/chenkeyi`各为节点本地，路径相同不等于共享。18本地SSD承载环境、数据缓存、训练进程、热Checkpoint及日志，Ceph异步归档；17既有任务与原始证据保留。

必要资产迁移50,200个文件/链接记录、29,573,416,020字节；独立Serving依赖60,293记录、11,290,783,493字节；最终数据825文件、4,624,099,719字节，另有旧M2基线9,098,658,700字节，均全SHA校验。原始M09.32GB权重复用共享Ceph，未重新下载。没有复制全部Recorder或写入中的Checkpoint，没有--delete源数据。

18八张A800-SXM4-80GB（81920MiB），GPU间NV8，BF16 NCCL八卡通信通过。128K四卡真实最大allocated61.66GiB、reserved64.43GiB，保存/恢复通过；256K八卡真实前向/后向OOM，无256K有效Optimizer Step。最终M1/M2均四卡DP4、GA8，空余卡不保活占用。

训练固定GPU UUID：

- GPU-7b40e1e7-c43c-ba4f-10ed-397f948eeed1
- GPU-e6b0a5b4-c14b-e336-1fba-2cda6693aa91
- GPU-995cb9ba-212b-9df4-f85b-f6f75757007b
- GPU-6e9a5318-94e0-36dc-cb4a-95a22a0950d5

唯一持久advance复用原生`sft.runtime.public_stages.advance`，跨节点Ceph flock；当前R9控制器PID1244593/start_ticks91308613。R8→R9在原控制器观察休眠边界受控交接，M1原生训练PID3179152/start_ticks86376371不变。17跨节点非阻塞加锁确认仍有唯一持有者。旧R4 E3九题已自然终态，其服务由原有生命周期关闭；新R5 E3复用GPU4和18303，不取消或重跑旧Trial，不增加服务端口。89题原生install_only预检以并发4完成，89个唯一实际Trial全部通过，零模型调用；逐题Result、原CPU/RAM/镜像、Task公开文件SHA和Verifier时限终验已通过。原9题已自动启动修复版E3。正式801的环境安装门禁已满足，仍等待两模型最终HF验收。四组仅在801全部终态后恢复，A不会重跑前两步。Epoch1/3/5的六次独立NLL及M2固定CF留出核算已接续，旧443核算继续受801门禁约束。没有第二写入训练总控。18已开启用户linger，训练不依赖本地SSH存活。复用17的20分钟只读GPU Watch与observer R15；实际执行约0.35秒，远低于90秒自身超时，实际监控Step/GPU/Checkpoint和阻塞，不以Timer active代替训练。

E3首批两个真实Trial的启动及多轮调用已由Recorder证据确认；E3全部终态、正式801及旧研究的完成情况仍分别以对应原生Result和阶段报告为准。完整目标包括M1/M2五轮及最终HF验收、E3诊断、801正式评分和后置旧四组，本报告不把已启动当作已完成。严格0.5%全模型梯度误差未通过；两池重复native后向自身亦有约2%波动，保留限制。独立NLL以2048 Prefill块通过130,981 Token/95,839监督Token联验，原8192块输入Logits OOM保留，主Agent Serving及训练配置未改。所有正式结果以原生日志与终态为准。
''')
write('EVIDENCE_INDEX.md',f'''
# 证据索引

本目录为可阅读的进行中交接，不宣称整个研究完成。原始训练/Recorder/Verifier工件仍在其原节点。完整文件SHA见EVIDENCE_SHA256.json；索引对应本次本地报告快照，18的实时曲线随后仍可由监控更新，最终交付另行封存。

| 证据 | 身份/位置 |
|---|---|
| 最终772身份 | ../frozen-metadata/FROZEN_772_CORPUS_MANIFEST.json；SHA `{sha(F/'FROZEN_772_CORPUS_MANIFEST.json')}` |
| 数据Release | ../frozen-metadata/DATA_RELEASE.json；SHA `{sha(F/'DATA_RELEASE.json')}` |
| 数据审计 | ../frozen-metadata/DATA_AUDIT.json；SHA `{sha(F/'DATA_AUDIT.json')}` |
| CF/TMax各池Manifest | ../frozen-metadata/calibforge/DATA_MANIFEST.json；../frozen-metadata/tmax/DATA_MANIFEST.json |
| 逐样本Task/Trial/Call、IDs/labels SHA | `{R}/frozen-data-772-r3/{{calibforge,tmax}}/SAMPLE_MAPPING-131072.jsonl` |
| 全量前缀审计 | `{S}/provenance/native-sglang-prefixes-r1/ALL_TARGET_NATIVE_SGLANG_PREFIX_AUDIT.json` |
| 全量输出Codec | ../checks/ALL_TARGET_NATIVE_OUTPUT_CODEC_AUDIT.json |
| 工具/Prompt全量 | ../checks/ACTUAL_772_TOOL_PROMPT_PROTOCOL_AUDIT.json |
| 容量更新/保存/恢复 | ../checks/CAPACITY_ACCEPTANCE.json；../checks/CONTEXT_128K_FALLBACK_EVIDENCE_R6.json |
| 正式首步及曝光 | ../checks/NEW_M1_LIVE_ACCEPTANCE.json |
| Epoch1完整保存 | ../checks/NEW_M1_EPOCH1_NATIVE_ACCEPTANCE.json |
| Epoch2完整保存及归档 | ../checks/NEW_M1_EPOCH2_NATIVE_SAVE_WITNESS_R1.json；../checks/NEW_M1_EPOCH2_ASYNC_ARCHIVE_ACCEPTANCE_R1.json |
| Epoch3完整保存及归档 | ../checks/NEW_M1_EPOCH3_NATIVE_SAVE_WITNESS_R1.json；../checks/NEW_M1_EPOCH3_ASYNC_ARCHIVE_ACCEPTANCE_R1.json |
| Epoch4完整保存及归档 | ../checks/NEW_M1_EPOCH4_NATIVE_SAVE_WITNESS_R1.json；../checks/NEW_M1_EPOCH4_ASYNC_ARCHIVE_ACCEPTANCE_R1.json |
| Epoch3独立NLL与HF快照 | ../checks/NEW_M1_EPOCH3_UNIQUE_NLL_CROSSCHECK_R1.json；../checks/NEW_M1_EPOCH3_NLL_AUDIT_COMPLETE.json；../checks/NEW_M1_EPOCH3_EPOCH_MODEL_EXPORT_COMPLETE.json |
| E3首批真实Trial及实际协议 | ../checks/NEW_M1_EPOCH3_NATIVE_TRIALS_LIVE_ACCEPTANCE_R1.json；两个实际Agent调用时间重叠，尚不构成Verifier成功 |
| Epoch1逐微批曝光 | ../checks/NEW_M1_EPOCH1_EXPOSURE_AUDIT.json；18 checks/NEW_M1_EPOCH1_EXPOSURE_ROWS.jsonl |
| 控制器交接 | ../checks/NATIVE_ADVANCE_R9_CONTROLLED_HANDOFF.json；训练PID及冻结训练源码未变，跨节点Ceph唯一互斥 |
| E1独立全量NLL | ../checks/NLL_AUDIT_COMPLETE.json；../checks/NEW_M1_EPOCH1_UNIQUE_NLL_CROSSCHECK.json |
| E1视觉冻结与异步归档 | ../checks/NEW_M1_EPOCH1_FROZEN_VISION_AUDIT.json；../checks/NEW_M1_EPOCH1_ASYNC_ARCHIVE_ACCEPTANCE.json |
| 主语言/MTP组件范围 | ../checks/HF_COMPONENT_CENSUS_AND_NO_MTP_POLICY_R1.json |
| 旧M2必要基线迁移 | ../checks/OLD_M2_BASELINE18_DEPLOYMENT.json |
| 旧443在18逐行核验 | ../checks/OLD443_CPU_NODE18_ACCEPTANCE_R1.json |
| 唯一行NLL接线 | ../checks/NLL_PHASE_WIRING_CPU_ACCEPTANCE_R1.json |
| 旧112行为配置与入口 | ../checks/OLD112_NATIVE_DEPLOYMENT_PLAN_R1.json；../checks/OLD112_NATIVE_ALL_CONFIGS_ACCEPTANCE_R2.json；尚未派发 |
| 嵌套Artifact与后台查询 | ../checks/NATIVE_ARTIFACT_BEHAVIOR_READER_ACCEPTANCE_R3.json；../checks/OLD112_NATIVE_BEHAVIOR_READER_ACCEPTANCE_R2.json；../checks/OLD112_NATIVE_KV_TOOL_ERROR_AND_POLL_READOUT_R1.json |
| 旧HF本地封存互斥 | ../checks/OLD_MODEL_RELEASE_LOCAL_MUTEX_CPU_ACCEPTANCE_R1.json；独立于跨节点Ceph总控锁 |
| Recorder UNKNOWN分类 | ../checks/STRICT_RECORDER_UNKNOWN_CLASSIFICATION_R3.json；../checks/NATIVE_EVAL149_DEPLOYMENT_RELEASE_R4.json |
| 原生NLL长样本 | ../checks/NATIVE_SGLANG_NLL_REFERENCE_R2.json |
| 分类Token位置 | ../checks/LABEL_CLASS_INDEX_AUDIT.json |
| 全部实际训练微批次 | ../checks/NATIVE_TRAINING_READOUT_R1.json；18 checks/ACTUAL_TRAINING_EXPOSURE_ROWS_*_R1.jsonl |
| 20分钟曝光观测 | ../checks/MONITOR_R15_CONTROL_AND_NATIVE_PROGRESS_ACCEPTANCE.json；复用17原Timer和受限SSH入口 |
| 跨节点时钟采样 | ../checks/NATIVE_18_149_CLOCK_OFFSET_READOUT_R1.json；149相对18约快22秒，保留原始时间戳与来源节点，不追溯重排冻结语料 |
| E3/E5固定9题比较 | ../checks/EPOCH3_VS_EPOCH5_COMPARISON_R4.json；EPOCH3_VS_EPOCH5_DIAGNOSTIC_R4.md；两者必须同一修复版R5 Wheel，旧R3仅历史 |
| 旧四组统一只读比较 | ../checks/OLD_FOUR_UNIFIED_COMPARISON_R1.json |
| 443行来源身份更正 | ../checks/OLD443_VERIFIED_TASK_IDENTITY_GROUPS_R1.json；../checks/EVALUATION443_TASK_IDENTITY_NOTE_R1.json；100原始ID/92来源组 |
| 443编码视图的模态范围 | ../checks/OLD443_ENCODED_MODALITY_COMPOSITION_R1.json；未冒充原始Teacher图像上下文 |
| 训练曲线与CSV | training-curves/NEW-M1-curves.png；training-curves/NEW-M1-metrics.csv |
| 当前原生日志 | `{R}/runs/new-m1-cf416-128k-e5/preflight-evidence-rank{{0,1,2,3}}.jsonl` |
| GPU数值参考 | ../checks/QWEN4B_GPU_LOSS_GRADIENT_GOLDEN_R1.json；../checks/QWEN_HEAD_PRECISION_ISOLATION_R4.json；18保留R2/R3失败日志 |
| 实际16回合CLI协议 | ../checks/NATIVE_FULL_CLI_PROTOCOL_ACCEPTANCE_R2.json；对应R2 run中原始Recorder和失败fixture都保留 |
| 学生wheel与独立安装 | ../checks/NEW11_STUDENT_HARNESS_RELEASE_R5.json；../checks/CONTEXT_RECOVERY_INSTALLED_WHEEL_ACCEPTANCE_R1.json；源码/独立安装各80项回归 |
| 完整Wheel端到端 | ../checks/CONTEXT_RECOVERY_FULL_WHEEL_E2E_ACCEPTANCE_R1.json；6项真实CLI/HTTP故障注入，不冒充官方Task成功 |
| 最小控制器修复与交付 | OPENHARNESS_CONTEXT_RECOVERY_FIX.md；../patches/consecutive-context-overflow-recovery-r1.patch |
| 修复后当前接续门禁 | ../checks/CONTEXT_RECOVERY_PRIORITY_STATUS_R2.json；R1为部署前历史快照 |
| 旧评测只读影响清单 | ../checks/HISTORICAL_CONTEXT_RECOVERY_AUDIT_R2.json；9条旧诊断中2条同类缺陷，原Reward/Result不变 |
| Token估算独立调查 | ../checks/TOKEN_ESTIMATION_INVESTIGATION_R2.json；4个真实输入中3个原生回放精确、1个差1Token，未补造Token |
| 修复版真实模型调用 | ../checks/REPAIRED_EPOCH3_NATIVE_LIVE_ACCEPTANCE_R1.json；两个原生Trial时间重叠、11工具及Provider Payload实证 |
| 89题CLI部署 | ../checks/NEW11_INSTALL_PREFLIGHT_STATUS_R1.json；零模型调用/零官方评分；原生readonly公共rg绑定见AGENT_PUBLIC_DEPENDENCY_DEPLOYMENT_R1.json |
| 全部89题安装终验 | ../checks/NEW11_ALL89_INSTALL_ACCEPTANCE_R1.json；逐题Result/UUID/安装工件及实际Compose与原Task资源比对，零模型尝试，不宣称Verifier已执行 |
| 首个E3上下文与账本 | ../checks/FIRST_E3_CONTEXT_OVERFLOW_AND_USAGE_RECONCILIATION_R1.json；../checks/CONTEXT_ACCOUNTING_REAL_TRIAL_ACCEPTANCE_R3.json |
| 正式801部署 | ../checks/NATIVE_EVAL149_DEPLOYMENT_RELEASE_R7.json；../checks/FORMAL801_WHEEL_ONLY_DEPLOYMENT_R2.json；原Trial计划未改，仍需两阶段最终HF验收 |
| 原始149主数据身份 | `/home/chenkeyi/.local/share/harbor-rsi/qwen35-new-cf500-tmax500-20261029/frozen-772-20261101` |

读取顺序：EXECUTION_AND_RESOURCE_STATUS → DATA_AUDIT → PREFIX_AND_SFT_CORRECTNESS → 两份训练报告 → TB21 → OLD_M2。
''')
e2e=read(L/'checks/CONTEXT_RECOVERY_FULL_WHEEL_E2E_ACCEPTANCE_R1.json')
historical=read(L/'checks/HISTORICAL_CONTEXT_RECOVERY_AUDIT_R2.json')
token=read(L/'checks/TOKEN_ESTIMATION_INVESTIGATION_R2.json')
live=read(L/'checks/REPAIRED_EPOCH3_NATIVE_LIVE_ACCEPTANCE_R1.json')
preflight=read(L/'checks/NEW11_INSTALL_PREFLIGHT_STATUS_R1.json')
remaining_gates=[]
for label,value in [('NEW-M1',native_m1),('NEW-M2',native_m2)]:
    if not value['five_epochs_completed_and_final_hf_admitted']:
        remaining_gates.append(label+' Epoch5最终HF及CLI验收')
if preflight['ready']!=89:remaining_gates.append('全部89题原生安装预检')
readiness_note=('正式801项目前NOT_READY：尚需'+'、'.join(remaining_gates)+'。')if remaining_gates else '训练HF与89题安装门禁已满足，正式801项执行及完成状态仍以原生Job/Result为准。'
affected=[v for v in historical['trials']if v.get('affected_by_once_per_drive_guard')]
affected_rows=[]
for v in affected:
    episode=v['repeated_after_success_episodes'][0]
    affected_rows.append(f"| {v['trial_name']} | {episode['normal_tool_use_between']} | Reward0 / CLI异常 | `{v['result_sha256']}` |")
token_rows=[f"| {v['trial_name'].split('__')[0]} / {i+1} | {v['serving_actual_input_tokens']} | {v['harness_trigger_estimate']} | {v['undercount']} | {v['serving_budget_overflow']} | {v['exact_replay_difference']} |"for i,v in enumerate(token['rows'])]
case_rows=[f"| {v['case']} | {v['exit_code']} | {v['compactions']} | {v['executed_tools']} | 通过 |"for v in e2e['cases']]
live_rows=[f"| {v['trial']} | {v['actual_agent_model_calls_started']} | {v['actual_tool_calls']} | `{v['first_call_id']}` |"for v in live['trials']]
write('OPENHARNESS_CONTEXT_RECOVERY_FIX.md',f'''
# Open-Harness 上下文恢复修复交付

修复版Wheel工程验收READY，已用于真实E3任务。{readiness_note}NEW-M1实际{step}/200步，NEW-M2实际{step2}/125步；修复时训练原PID3179152/start_ticks86376371、冻结源码、数据、配置与GPU0–3不变。唯一R9控制器PID1244593持续接续；旧四组继续后置，不新增付费教师采样。

源码Commit：`ae1403262b8d2ae8a9732c2d00ab622bb6891c40`。最小补丁：[consecutive-context-overflow-recovery-r1.patch](../patches/consecutive-context-overflow-recovery-r1.patch)，SHA `7c74d9759533d98ddd3eef072427a1b1a4be0cfaddda1ed41421fbbe1c1e1038`。

只改Controller的恢复资格：一次连续失败区间最多恢复一次；真实Assistant完整响应stop/toolUse后恢复资格。overflow、error、aborted、length及辅助摘要成功均不恢复资格。无任务特化、无无限压缩重试，无估算器修改。连同两项回归和版本号共3文件51增4删；178个运行时Python文件中仅controller/baseline.py字节变化，工具、Transport、Prompt、Agent Loop、Recorder不变。未Push。

Wheel：`open_harness_ai-0.3.0+rsi.qwen35.20261101.3-py3-none-any.whl`，371772字节。

**Wheel SHA256：`1d27eef1ca6696275f306d8c653f7a266a4c7aea7321f0d47fd01b739c27fa18`**。

18构建于`/ssd/chenkeyi/qwen35-sft-772-20261101/harness-context-recovery-r1/dist/`，149已校验部署；源码回归80/80、源码目录外独立安装Wheel回归80/80、178个已安装运行时文件逐字节校验、CLI及依赖检查全部通过。证据：[安装验收](../checks/CONTEXT_RECOVERY_INSTALLED_WHEEL_ACCEPTANCE_R1.json)，SHA `{sha(L/'checks/CONTEXT_RECOVERY_INSTALLED_WHEEL_ACCEPTANCE_R1.json')}`。

完整安装CLI以真实HTTP/SSE故障注入、真实工具执行、Session及Recorder完成6项联验。该工程fixture不调用真实模型或官方Verifier，不冒充TB成功。两次独立超限之间有12个正常toolUse回合，执行全部11工具28次；toolResultBudget预算后真正进入请求的Observation、后台任务与Finish均核验。压缩后立即再超限只压缩1次并退出；length/error/中断也不会让资格无限恢复。6份Recorder物理结构均完整，error/aborted终态原样保留。

| 用例 | CLI退出 | 压缩次数 | 实际工具调用 | 结果 |
|---|---:|---:|---:|---|
{chr(10).join(case_rows)}

[完整Wheel联验证据](../checks/CONTEXT_RECOVERY_FULL_WHEEL_E2E_ACCEPTANCE_R1.json)，SHA `{sha(L/'checks/CONTEXT_RECOVERY_FULL_WHEEL_E2E_ACCEPTANCE_R1.json')}`；原始事件、请求索引和配置SHA逐用例保留于18的`harness-context-recovery-r1/e2e/run-20261101T161651Z-718a8c/`。生产context262144、output81920、reserve81920、keepRecent20000不变。

旧NEW-M1 Epoch3诊断9题全部终态，发现同类缺陷2题。其余2题为模型连接故障、5题为安装网络失败且没有Recorder，均不归为此缺陷。以下两题的Verifier均实际完成、原Reward0、Agent异常退出；不重算或改写成绩。

| 受影响历史Trial | 两次超限间正常toolUse | 原始结果 | Result SHA256 |
|---|---:|---|---|
{chr(10).join(affected_rows)}

[旧评测只读审计](../checks/HISTORICAL_CONTEXT_RECOVERY_AUDIT_R2.json)，SHA `{sha(L/'checks/HISTORICAL_CONTEXT_RECOVERY_AUDIT_R2.json')}`，包含真实Call ID、Recorder完整性和原Session/Result身份。原始Result、Reward、退出状态及Recorder均保留。

Token调查独立于修复。用真实Payload和原生SGLang预处理对照Serving HTTP400报告输入数，并从原Session分支重放当时的预算化Observation及Compaction可见历史。阈值是262144−81920=180224。

| 任务/请求顺序 | Serving输入 | Harness估算 | 低估 | 超预算 | 原生回放−Serving |
|---|---:|---:|---:|---:|---:|---:|
{chr(10).join(token_rows)}

主要发现：任意历史工具结果发生预算投影时，当前估算策略清除全部Assistant usage锚点，回退为整个可见历史字符数/4，未显式计入System、工具Schema及模板开销。其余3次用上一调用实际input+output作锚点，之后增量仍用字符数/4；System/Schema已经隐含于锚点，不能再重复相加。Thinking、代码/数字及工具Observation的实际分词与字符估计存在显著差异，模板重渲染也可能影响增量。四次真实请求均无图像，不能将这些超限归因于图片；代码中的1200/image只是估计，未宣称多模态精确计数。

原生回放3/4精确，另1次181949 vs Serving181950，差1 Token仍未解释；没有Padding、手工补Token或修改原始Payload制造一致。组件计数消融仅用于调查，不是实际或训练上下文，差值不宣称可直接相加。精确计数优化尚未实施，保留为独立后续改动，不改变本轮预算。[独立计数报告](../checks/TOKEN_ESTIMATION_INVESTIGATION_R2.json)，SHA `{sha(L/'checks/TOKEN_ESTIMATION_INVESTIGATION_R2.json')}`。

修复版真实任务已启动，以下两条原生E3 Trial的Agent/模型调用时间重叠，尚未评分。Recorder实际Payload的11工具Schema SHA `9b14204af97deda8b282e969ebbba410490505423912b2bd509896025b50b59f`、Thinking、采样和预算均与冻结合同一致，实际安装Wheel SHA相同。下表是该证据的固定采样快照，不能当作终态或成功。

| 新Trial | 实际模型调用开始 | 实际工具调用 | 首Call ID |
|---|---:|---:|---|
{chr(10).join(live_rows)}

[真实运行证据](../checks/REPAIRED_EPOCH3_NATIVE_LIVE_ACCEPTANCE_R1.json)，SHA `{sha(L/'checks/REPAIRED_EPOCH3_NATIVE_LIVE_ACCEPTANCE_R1.json')}`。模型运行18 GPU4，任务容器149 Engine `c6e16cdf-e878-4cc5-84c8-78a56c54b5c5`，复用原18303链路。

已预登记新的18条修复版E3身份，沿用原9题，不按旧成败挑题。旧R4诊断原样保留；未开始的旧R4 M2不再派发。正式M0/NEW-M1/NEW-M2及可比E3统一此R5 Wheel；R4版只读比较器逐个核验实际Wheel SHA，旧跨版本R3比较仅为历史，不能作本轮E3/E5结论。E5仍为预指定主模型，不据诊断调整训练。

89题安装预检快照：{preflight['ready']}/89 READY、{preflight['terminal']}/89终态、失败{len(preflight['failed'])}，模型尝试0、官方评分0。只读公共rg部署避免原apt HTTP80失败；使用RemoteDocker原有extraCompose，不改官方Task、镜像、Verifier或资源。Campaign部署变更与Controller修复分开记录。正式801项原Task/Trial清单未改，当前自动门禁明确NOT_READY；达到两模型最终HF与89题安装验收后由同一原生控制器接续。

部署证据：[R9受控交接](../checks/NATIVE_ADVANCE_R9_CONTROLLED_HANDOFF.json)、[149部署R7](../checks/NATIVE_EVAL149_DEPLOYMENT_RELEASE_R7.json)、[89题安装进度](../checks/NEW11_INSTALL_PREFLIGHT_STATUS_R1.json)、[20分钟监控](../checks/MONITOR_R15_CONTROL_AND_NATIVE_PROGRESS_ACCEPTANCE.json)。完整快照SHA见EVIDENCE_SHA256.json；此报告不是主训练或801项已完成的声明。
''')
(OUT/'FROZEN_772_CORPUS_MANIFEST.json').write_bytes((F/'FROZEN_772_CORPUS_MANIFEST.json').read_bytes())
hashes={str(p.relative_to(L)):sha(p)for p in sorted(L.rglob('*'))if p.is_file()and '__pycache__'not in str(p)and p.name!='EVIDENCE_SHA256.json'}
(OUT/'EVIDENCE_SHA256.json').write_text(json.dumps(hashes,indent=2,ensure_ascii=False)+'\n')
print(json.dumps(dict(reports=str(OUT),files=len(list(OUT.iterdir())),m1_step=step)))
