"""Check native AgentEnd accounting and atomically bind the existing observer."""
import ast
import datetime
import hashlib
import json
from pathlib import Path
import tempfile

R=Path('/home/chenkeyi/.local/share/harbor-rsi/qwen35-new-cf500-tmax500-20261029')
sha=lambda path:hashlib.sha256(path.read_bytes()).hexdigest()
source=R/'scripts/observe_collection_agent_phases_r147.py'
tree=ast.parse(source.read_bytes())
function=next(x for x in tree.body if isinstance(x,ast.FunctionDef) and x.name=='teacher_slot_telemetry')
module=ast.Module(body=[function],type_ignores=[]);ast.fix_missing_locations(module)
with tempfile.TemporaryDirectory(prefix='cftmax-agent-phase-test-') as temp:
    root=Path(temp);directory=root/'stream/collection-r4';directory.mkdir(parents=True)
    events=[];base=datetime.datetime(2026,10,31,tzinfo=datetime.timezone.utc)
    def add(kind,name,second):
        stamp=(base+datetime.timedelta(seconds=second)).isoformat()
        events.append(dict(event=kind,trial_name=name,observed_at=stamp,agent_admitted_at=stamp))
    for i in range(8):add('TEACHER_ADMITTED',str(i),i)
    add('TEACHER_AGENT_ENDED','0',10);add('TEACHER_ADMITTED','8',11)
    add('TEACHER_FINALIZED','0',12)
    (directory/'teacher-lifecycle.jsonl').write_text(''.join(json.dumps(x)+'\n' for x in events))
    namespace=dict(ROOT=root,json=json,datetime=datetime)
    exec(compile(module,str(source),'exec'),namespace)
    value=namespace['teacher_slot_telemetry']({})
    if value['native_admitted_agent_phase_trials']!=8 or value['maximum_observed_native_agent_permits']!=8 or value['completed_backfill_cycles']!=1:
        raise ValueError('A completed Agent or later native END was miscounted')
    if value['completion_to_replacement'][0]['gap_seconds']!=1:raise ValueError('Refill did not use actual native AgentEnd boundary')
canonical=R/'scripts/observe_collection.py'
proof=R/'checks/agent-phase-observer-r147-activation.json'
if proof.exists():raise FileExistsError('Observe already activated source')
if sha(canonical)!='f47f795483d98d0c1055970eaf220ef6fcd523be0065f1b24ca54338087cf9c6':
    raise ValueError('Existing observer source changed')
backup=R/'scripts/observe_collection_before_agent_phase_r147.py'
with backup.open('xb') as stream:stream.write(canonical.read_bytes())
temporary=canonical.with_suffix('.r147-pending');temporary.write_bytes(source.read_bytes());temporary.replace(canonical)
value=dict(checked_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),passed=True,
    observer_sha256=sha(canonical),reporter_sha256=sha(R/'scripts/collection_reports_r147.py'),
    live_phase_sampler_sha256=sha(R/'scripts/capture_active_teacher_phases149_r147.py'),
    synthetic_agent_end_refill_gap_seconds=1,duplicate_native_end_not_counted_twice=True,
    live_teacher_claim='Requires Provider events, live actual native CLI process and absent CLI completion marker',
    historical_r130_proof_limit='Only proved unfinished Trial plus existing Provider evidence; did not exclude Agent already completed during verifier/artifact collection',
    timer_or_service_changes=0,teacher_or_verifier_signals=0,source_sha256=sha(Path(__file__)))
with proof.open('x') as stream:json.dump(value,stream,indent=2)
handoff=R/'CURRENT_HANDOFF.md';backup=R/'CURRENT_HANDOFF_before_agent_phase_correction.md'
if not backup.exists():backup.write_bytes(handoff.read_bytes())
correction='''# 并发口径纠正：R16交接验收中

旧R130的“8个未终态Trial+Recorder/Provider事件”不足以证明8个Agent仍执行。R143增加实际CLI进程/完成marker检查后，发现若干已结束Agent仍在Verifier或回收；旧R15把许可持有到Trial END。旧证据全部保留，但其严格8 Agent结论被撤回。参见checks/actual-active-agent-eight-and-backfill-r143-20261031T074822Z.json。

R16候选改为原生AGENT_START→AGENT_END占用最多8个教师许可；Verifier/回收保持原生生命周期且另行有界，native queue上限24，setup缓冲4。原Task/Verifier/模型/工具/预算均不变。以CURRENT_DISPATCH_AUTHORITY_R16.json实际存在及进程身份为准，不能把候选验收当作已交接。监控R147已使用真实CLI进程+无完成marker，新增AgentEnd事件计入补位；旧R15在途任务仍保守占许可至原END，未经新证据不能声称真实8。

已完成的新数据工作：17SSD/data-corpus-snapshots/r139中452个Task（CF304/TF148）的两视图组合缓存，2840行全部通过正式Loader/Collator和逐Token标签验收，CPU手工loss/梯度参考最大梯度差0。元数据checks/partial-combined-cache-r139/，原始Token/轨迹未下载本地。它是中间快照，未冻结全量最终语料、未训练。

节点时钟差证据checks/runtime-clock-offset-r140.json：17相对149约慢19秒；原时间戳不改，跨节点不能直接相减为延迟。主轨迹按Harbor原生Trial顺序选首个合格成功，Trial内按Recorder因果顺序。

以下保留上一份快照，涉及“严格8”的旧结论以上述纠正为准：

'''
handoff.write_text(correction+backup.read_text())
print(json.dumps(value))
