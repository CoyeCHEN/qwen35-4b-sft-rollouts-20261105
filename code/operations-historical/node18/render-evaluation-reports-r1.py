"""Use native formal comparison/progress if present; no scores from pending work."""
import hashlib
import json
from pathlib import Path


def render(root):
    root=Path(root);out=root/'reports';current=json.loads((root/'checks/CURRENT_EXECUTION_STATUS.json').read_text())
    full=root/'checks/TB21_N3_FULL_COMPARISON.json';result=json.loads(full.read_text())if full.exists()else None
    remote=(current.get('remote_native_evaluation')or{}).get('modes',{}).get('formal-n3',{})
    progress=remote.get('progress')or{};terminal=(result or progress).get('terminal',0)
    lines=['# TB2.1 M0 / NEW-M1 / NEW-M2 n=3','',f'原生证据已观察{terminal}/801个正式Trial终态。'+('正式比较已齐。'if result and result.get('complete')else'尚未取得完整三模型比较。'),
        '', '固定89题，三个模型各3次，801正式Trial；NEW-M1/M2预先指定Epoch5。修复版E3另有9题×两模型×1=18诊断，分母独立；旧R4的9条NEW-M1诊断保留为历史，尚未启动的旧R4 NEW-M2不再派发。E3/E5比较使用同9题在E5的全部三次，不择优Attempt，不据成绩改配方或Checkpoint。',
        '', '三个模型分别独立冷启动，统一11工具、Finish、toolResultBudget、Thinking/Compaction及采样；EVAL_LONG3H研究时限，保留原始12000秒任务时限，不是旧原生时限或官方榜单分数。旧十工具M0的14/89不充当本轮对照。']
    if result:
        lines+=['','| 模型 | 确认Reward成功/267 | 平均单次确认率 | 正常完整成功/267 | 评分及协议覆盖 | UNKNOWN |','|---|---:|---:|---:|---:|---:|']
        for name,v in result['models'].items():
            lines.append(f"| {name} | {v['confirmed_reward_successes']}/267 | {v['confirmed_mean_single_trial_success_fixed_denominator']:.4%} | {v['normal_complete_successes']}/267 | {v['coverage']:.4%} | {v['unknown']} |")
        lines+=['',f"正式比较JSON SHA `{hashlib.sha256(full.read_bytes()).hexdigest()}`。逐轮89题、逐题三次、至少成功一次比例、超时但Reward1、工具/Thinking指标及M0→M1→M2得失均见该JSON。"]
    elif progress:
        lines+=['',f"原生进度（含待评分/审计项，不能作为最终成绩）：`{json.dumps(progress,ensure_ascii=False)}`。"]
    else:lines+=['','当前尚无正式Result可报告；配置冻结和工程联验不当作正式Task成绩。']
    lines+=['','UNKNOWN保留，固定分母成功率在存在UNKNOWN/待完成项时为已确认下界；三次至少一次成功比例不混称平均pass1。Verifier原始Reward、协议资格和正常完整轨迹分列；Recorder审计失败不计合格成功。',
        '', '已通过的独立Harbor工程fixture使用实际Verifier得到Reward1，9次调用中保留两次工具失败与修复、两次Finish请求；该fixture排除在801之外。另有未改动官方regex-log的NOP合法零分联验。89镜像及946源文件身份已有完整预检。',
        '', 'E3/E5只读比较另见EPOCH3_VS_EPOCH5_DIAGNOSTIC_R4.md，只使用相同修复版R5 Harness的结果，并逐个核对实际Trial配置中的Wheel SHA。R1/R2/R3历史比较不作为本轮可比结果。缺少结果时明确待执行；新的18条E3身份已预登记，不重复派发旧Trial。']
    lines+=['','正式三个模型和重新评测的E3统一R5 wheel：1d27eef1ca6696275f306d8c653f7a266a4c7aea7321f0d47fd01b739c27fa18。修复不改变模型、工具、Prompt、Token预算和采样；完整CLI的6项HTTP故障注入联验及独立安装80项回归通过。原始R4结果不改分、不混入可比成绩。派生审计用已冻结Task路径及公开文件SHA对齐短题名，保留原生terminal-bench/题名；原Result/Reward不改写。']
    preflight=root/'checks/NEW11_INSTALL_PREFLIGHT_STATUS_R1.json'
    if preflight.exists():
        p=json.loads(preflight.read_text())
        lines+=['',f"89题原生安装预检：{p['ready']}/89 Ready，{p['terminal']}/89终态，失败{len(p['failed'])}。该预检install_only，不调用模型、不执行官方Verifier，不计正式Trial成绩。正式801还需全部89题安装通过和NEW-M1/M2 Epoch5最终HF/CLI验收，当前不能仅因Wheel验收通过宣称整组READY。"]
    (out/'TB21_N3_COMPARISON.md').write_text('\n'.join(lines)+'\n')
