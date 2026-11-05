"""Explicit bounded review layered on the immutable 45-recorder audit.

The CSV records the first unambiguous observed failure pattern, not an invented
causal first mistake. Command errors alone and background polling are not loops.
"""
import csv
import hashlib
import json
from pathlib import Path
import sys

ROOT=Path('/home/chenkeyi/.local/share/harbor-rsi/qwen35-new-cf500-tmax500-20261029')
WHEEL=ROOT.parent/'qwen35-m1-m2-tb21-20261026/wheels/null-delta/open_harness_ai-0.3.0-py3-none-any.whl'
sys.path.insert(0,str(WHEEL))
from foundation.rollouts.export import loadValue

reviews={
 'build-pmars':('length',None,'MODEL_OUTPUT_LIMIT','先有真实下载尝试和错误返回；随后纯 Thinking 达到81920，未产生下一动作。不是900秒Agent期限或HTTP空闲120秒。'),
 'cancel-async-tasks':('length',None,'NO_ACTION_MODEL_OUTPUT_LIMIT','第一请求直接纯Thinking达到81920，工具数为0；未开始环境修改。'),
 'code-from-image':('call','060dd64d-78e2-48f9-9a81-9ea15b97bdaf','ACTION_INSIDE_THINKING_NOT_EXECUTED','读取图片并写入脚本后，最后回答把bash XML放进Thinking；正文和已解析Tool Call为空，未执行脚本。脚本本身正确性未获验证。'),
 'configure-git-webserver':('tool',5,'READ_ONLY_REPEAT_WITHOUT_PROGRESS','序号5至28重复只读查询，30至357重复另一只读查询；参数及可见Observation相同，没有配置或启动服务进展。'),
 'constraints-scheduling':('tool',33,'UNCHANGED_COMPUTATION_REPEAT','前期读取真实日历并搜索可行时间；33至352反复打印相同固定datetime，没有完成日历输出。'),
 'fix-code-vulnerability':('last_agent',None,'REPOSITORY_DETOUR_WITHOUT_PATCH','读取源码后持续追溯历史提交；77次工具交互没有write/edit/edit_patch，没有完成要求的修补和report.jsonl。具体首个不可逆错误不能由只读轨迹确定。'),
 'fix-git':('length',None,'RECOVERED_PATH_ERROR_THEN_OUTPUT_LIMIT','起初错误目录cd失败后已恢复到/app/personal-site；后续纯Thinking达到81920才是明确中断，不把早期可恢复错误冒充根因。'),
 'git-leak-recovery':('tool',43,'REPEATED_EMPTY_GIT_QUERY','43至246相同git查询、相同空输出；shell尾部返回0不能证明命令实现了恢复目标。'),
 'hf-model-inference':('last_agent',None,'MODEL_CLASS_AND_CODE_RECOVERY_FAILURE','实际记录包含错误模型架构/分类头新初始化、label2label属性错误和多次Python引用/转义错误；不能仅凭任务依赖下载就归为网络基础设施。精确最早语义偏离仍未确定。'),
 'kv-store-grpc':('tool',63,'REPEATED_COMPLETED_JOB_WITH_FAILED_SERVICE','区分前期运行中Job的合法轮询与后期反复读取已completed但端口未监听的结果；任务内timeout15秒杀服务不同于Harbor时限和handoff600。'),
 'nginx-request-logging':('length',None,'MODEL_OUTPUT_LIMIT_AND_INVALID_RAM_DIAGNOSIS','工具后纯Thinking达到81920；awk读取MemAvailable不存在的第4列会得到0，不是容器真实0MB或GPU OOM证据。'),
 'portfolio-optimization':('tool',97,'UNCHANGED_COMPILE_FAILURE_THEN_OUTPUT_LIMIT','97至108重复编译失败，gcc|head可能返回0掩盖错误；随后Agent81920输出耗尽。之后17Token compaction helper的stop不能当作任务正常完成。'),
}
resources=json.loads((ROOT/'checks/frozen-267-resource-audit.json').read_text())['rows']
lookup={(x['model'],x['task_id']):x for x in resources}
rows=[]
for task,(kind,which,category,note) in reviews.items():
    case=json.loads((ROOT/f'stage1/case-m2-{task}.private.json').read_text())
    other=json.loads((ROOT/f'stage1/case-m1-{task}.private.json').read_text())
    if kind=='length':point=case['first_length']
    elif kind=='tool':point=next(t for t in case['tools'] if t['ordinal']==which)
    elif kind=='call':point=next(c for c in case['calls'] if c['call_id']==which)
    else:point=next(c for c in reversed(case['calls']) if c.get('source')=='agent')
    resource=lookup[('m2',case['task_id'])]
    row=dict(task_id=case['task_id'],m1_success=other['success'],m2_success=case['success'],
        observable_failure_category=category,confidence='CONFIRMED_OBSERVATION_NOT_UNIQUE_CAUSAL_EXPLANATION',
        first_unambiguous_observation_call_id=point['call_id'],event_line=point.get('line'),
        response_line=point.get('response_line'),tool_ordinal=point.get('ordinal'),
        action=point.get('arguments_excerpt',''),observation=point.get('raw_excerpt',''),
        review=note,first_causal_deviation='UNPROVEN; observed localization is explicitly distinguished',
        final_exception=case['exception'],normal_close=case['normal_close'],
        original_agent_timeout_sec=resource['task_agent_timeout'],agent_override=resource['agent_override'],
        original_verifier_timeout_sec=resource['task_verifier_timeout'],verifier_override=resource['verifier_override'],
        observed_agent_seconds=resource['agent_execution_seconds'],historical_actual_cgroup=resource['historical_actual_cgroup'],
        m1_model_calls=other['counts']['model_calls'],m2_model_calls=case['counts']['model_calls'],
        m1_tool_executions=other['counts']['tool_executions'],m2_tool_executions=case['counts']['tool_executions'],
        source_events=case['source_events'],source_events_sha256=case['events_sha256'],result_path=case['result_path'],
        result_sha256=case['result_sha256'],review_file=f'stage1/case-m2-{task}.private.json')
    rows.append(row)
with (ROOT/'stage1/FAILED_TASKS_REVIEWED.csv').open('x') as stream:
    writer=csv.DictWriter(stream,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)

# Read the actual final model response, not the truncated case excerpt.
case=json.loads((ROOT/'stage1/case-m2-code-from-image.private.json').read_text())
call=next(c for c in case['calls'] if c['call_id']=='060dd64d-78e2-48f9-9a81-9ea15b97bdaf')
with Path(case['source_events']).open() as stream:
    event=next(json.loads(raw) for line,raw in enumerate(stream,1) if line==call['response_line'])
response=loadValue(event['data']['response'],Path(case['source_events']).parent/'artifacts')
content=response['content'];thinking=''.join(b.get('thinking','') for b in content if b['type']=='thinking')
text=''.join(b.get('text','') for b in content if b['type']=='text')
proof=dict(call_id=call['call_id'],response_event_line=call['response_line'],
    response_sha256=hashlib.sha256(json.dumps(response,sort_keys=True,ensure_ascii=False).encode()).hexdigest(),
    thinking_contains_tool_xml='<tool_call>' in thinking and '<function=bash>' in thinking,
    text_characters=len(text),parsed_tool_calls=sum(b['type']=='toolCall' for b in content),
    intended_bash_execution_seen_in_tools=any('python3 solve.py' in t['arguments_excerpt'] for t in case['tools']),
    claim='Observed intended tool syntax inside reasoning was never executed; source of this output behavior still needs serving/model comparison')
assert proof['thinking_contains_tool_xml'] and proof['text_characters']==0 and proof['parsed_tool_calls']==0
(ROOT/'checks/code-from-image-protocol-finding.json').write_text(json.dumps(proof,indent=2))
controls=[]
for task in ['modernize-scientific-stack','multi-source-data-merger','openssl-selfsigned-cert']:
    value=json.loads((ROOT/f'stage1/case-m2-{task}.private.json').read_text())
    controls.append({k:value[k] for k in ['task_id','success','normal_close','exception','counts','source_events','events_sha256']})
(ROOT/'checks/failure-review.json').write_text(json.dumps(dict(reviewed_lost_tasks=len(rows),
    controls=controls,source_modified=False,new_trials=0,new_model_requests=0),indent=2))
print(json.dumps(dict(reviewed=len(rows),code_image_finding=proof,controls=controls)))
