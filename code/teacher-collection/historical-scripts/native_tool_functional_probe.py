"""Synthetic, model-free SDK checks inside each pool's actual task image.

These records are diagnostics, never teacher requests, rewards, or SFT data.
"""
import asyncio
import copy
import hashlib
import json
from pathlib import Path
import sys
from uuid import uuid4

from rsi_modules.controller.sdk import createAgentSession
from rsi_modules.memory.context.budget import SessionToolResultBudget


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False).encode()).hexdigest()


async def main():
    config=json.loads(Path(sys.argv[1]).read_text());contract=json.loads(Path(sys.argv[2]).read_text())
    root=Path(sys.argv[3] if len(sys.argv)>3 else '/logs/agent/native-capability');root.mkdir(parents=True,exist_ok=False)
    work=root/'work';work.mkdir()
    config.update(cwd=str(work),sessionDir=str(root/'sessions'),recording=dict(enabled=True,directory=str(root/'recorder')))
    async with await createAgentSession(**config) as session:
        schemas=[{k:t[k] for k in ['name','description','parameters']} for t in session.state.tools]
        assert [t['name'] for t in schemas]==contract['final_tool_names']
        tools={t['name']:t for t in session.state.tools}
        result=await tools['edit_patch']['execute']('add',dict(changes=[dict(path='probe.txt',operation='add',content='before\n')]))
        assert not result.get('isError')
        result=await tools['edit_patch']['execute']('replace',dict(changes=[dict(path='probe.txt',operation='replace',oldText='before',newText='after')]))
        assert not result.get('isError') and (work/'probe.txt').read_text()=='after\n'
        started=await tools['bash']['execute']('bg-start',dict(command='sleep .1; printf native-job-ok',background=True,timeout=5))
        job=started['details']['job_id']
        waited=await tools['bash_job']['execute']('bg-wait',dict(action='wait',job_id=job,wait_seconds=2))
        read=await tools['bash_job']['execute']('bg-read',dict(action='read',job_id=job,offset=0,max_bytes=65536))
        assert 'native-job-ok' in json.dumps(waited) and 'native-job-ok' in json.dumps(read)
        live=await tools['bash']['execute']('bg-live',dict(command='sleep 30',background=True,timeout=40))
        cancelled=await tools['bash_job']['execute']('bg-cancel',dict(action='cancel',job_id=live['details']['job_id']))
        assert 'cancel' in json.dumps(cancelled).lower()
        # Exercise persisted compaction recall without a summarizer/model call.
        # The synthetic checkpoint is explicitly isolated from every teacher session.
        fixture_run='synthetic-capability-'+uuid4().hex
        session.manager.append('run_start',dict(runId=fixture_run))
        hidden=session.manager.append('message',dict(runId=fixture_run,message=dict(role='user',content='SYNTHETIC hidden capability fixture',timestamp=0)))
        kept=session.manager.append('message',dict(runId=fixture_run,message=dict(role='user',content='SYNTHETIC kept capability fixture',timestamp=0)))
        checkpoint=session.manager.append('compaction',dict(summary='SYNTHETIC capability checkpoint, no model',
            firstKeptEntryId=kept['id'],tokensBefore=2,details={},reason='manual',runId=fixture_run))
        session.manager.append('run_end',dict(runId=fixture_run,status='completed'))
        listing=json.loads((await tools['trajectory_read']['execute']('history-list',{}))['content'][0]['text'])
        assert listing['total']==1 and listing['entries'][0]['entry_id']==hidden['id']
        a=json.loads((await tools['trajectory_read']['execute']('history-read',dict(entry_id=hidden['id'],max_chars=30)))['content'][0]['text'])
        b=json.loads((await tools['trajectory_read']['execute']('history-next',dict(entry_id=hidden['id'],offset=a['next_offset'])))['content'][0]['text'])
        assert json.loads(a['content']+b['content'])==hidden
        try:await tools['trajectory_read']['execute']('visible-forbidden',dict(entry_id=kept['id']))
        except ValueError:pass
        else:raise AssertionError('Visible entry incorrectly exposed as hidden history')
        raw='full original output\n'*20000
        original=[dict(role='toolResult',toolCallId='large-error',toolName='bash',content=[dict(type='text',text=raw)],isError=True,timestamp=0)]
        before=copy.deepcopy(original)
        budget=SessionToolResultBudget(session._config['toolResultBudget'],baseDir=str(root/'tool-results'))
        visible=budget.project(original);saved=list((root/'tool-results').glob('*.txt'))
        assert before==original and len(saved)==1 and saved[0].read_text()==raw
        assert visible[0]['toolCallId']=='large-error' and visible[0]['isError']
        assert 'shortened by budget' in visible[0]['content'][0]['text']
        readable=await tools['read']['execute']('offloaded-read',dict(path=str(saved[0]),offset=1,limit=2))
        assert 'full original output' in json.dumps(readable) and not readable.get('isError')
        first=await tools['finish']['execute']('finish-check',dict(summary='Synthetic functional checks only'))
        second=await tools['finish']['execute']('finish-request',dict(summary='Synthetic functional checks only'))
        assert not first.get('finishRequested') and second.get('finishRequested') is True
        evidence=dict(passed=True,scope='SYNTHETIC native SDK functional tests; no teacher model run',
            execution_environment='isolated local installed wheel' if len(sys.argv)>3 else 'actual task image via native Harbor setup',
            real_model_calls=0,teacher_attempts=0,sft_eligible=False,
            tool_schema_sha256=digest(schemas),system_prompt_sha256=hashlib.sha256(session.state.systemPrompt.encode()).hexdigest(),
            tool_names=[t['name'] for t in schemas],edit_patch_add_replace=True,
            background_start_wait_read_cancel=True,finish_check_then_request=True,
            trajectory_hidden_read_pagination_and_visible_rejection=True,
            synthetic_compaction_entry_id=checkpoint['id'],budget_settings=session._config['toolResultBudget'],
            raw_chars=len(raw),model_visible_chars=len(visible[0]['content'][0]['text']),
            full_raw_path=str(saved[0]),full_raw_sha256=hashlib.sha256(raw.encode()).hexdigest(),
            budget_error_and_call_id_preserved=True,offloaded_content_read_via_native_read=True)
        (root/'proof.json').write_text(json.dumps(evidence,indent=2));print(json.dumps(evidence))


if __name__=='__main__':asyncio.run(main())
