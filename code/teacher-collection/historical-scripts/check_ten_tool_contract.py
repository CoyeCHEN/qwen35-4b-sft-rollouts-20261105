"""Validate the explicit ten-tool, Finish-off contract, without model calls."""
import asyncio
import hashlib
import json
import os
from pathlib import Path
import tempfile

os.environ['OPEN_HARNESS_FINISH']='0'
os.environ['OPEN_HARNESS_BACKGROUND_JOBS']='1'
from foundation.ai.deepseek import buildPayload
from rsi_modules.controller.sdk import createAgentSession

ROOT=Path(os.environ.get('CF_TMAX_EVIDENCE_ROOT', '/home/chenkeyi/.local/share/harbor-rsi/qwen35-new-cf500-tmax500-20261029'))


async def main():
    path=ROOT/'configs/teacher-native-10tools-finish-off.json'
    config=json.loads(path.read_text())
    assert config['finish']['enabled'] is False
    with tempfile.TemporaryDirectory(prefix='cf-tmax-ten-tool-contract-') as temp:
        config.update(cwd=temp,sessionDir=temp+'/sessions',recording=dict(enabled=True,directory=temp+'/recorder'))
        config['tokenObservation']['directory']=temp+'/token-usage'
        async with await createAgentSession(**config) as session:
            tools=[{k:t[k] for k in ('name','description','parameters')} for t in session.state.tools]
            payload=buildPayload(session.state.model,dict(systemPrompt=session.state.systemPrompt,
                messages=[dict(role='user',content='Offline contract check. No model request.')],tools=tools),
                dict(config['requestOptions'],reasoning='max'))
            names=[t['function']['name'] for t in payload['tools']]
            assert len(names)==10 and len(set(names))==10
            assert set(names)=={'read','bash','edit','write','grep','find','ls','bash_job','trajectory_read','edit_patch'}
            assert 'finish' not in names
            assert payload['thinking']=={'type':'enabled'} and payload['reasoning_effort']=='max'
            assert payload['max_tokens']==65536 and payload['stream'] is True
            digest=lambda v:hashlib.sha256(json.dumps(v,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
            report=dict(passed=True,scope='Actual installed SDK session and native Provider Payload, offline only',
                teacher_config_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),tool_names=names,
                tool_schema_sha256=digest(tools),system_prompt_sha256=hashlib.sha256(session.state.systemPrompt.encode()).hexdigest(),
                codec_provider_tools_sha256=hashlib.sha256(json.dumps(payload['tools'],sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest(),
                finish=False,native_token_observation_enabled=config['tokenObservation']['enabled'],
                thinking=payload['thinking'],reasoning_effort=payload['reasoning_effort'],
                max_tokens=payload['max_tokens'],paid_model_requests=0,benchmark_attempts=0)
            (ROOT/'checks/ten-tool-finish-off-offline.json').write_text(json.dumps(report,indent=2))
            (ROOT/'checks/ten-tool-finish-off-payload.private.json').write_text(json.dumps(payload,indent=2))
            print(json.dumps(report))


if __name__=='__main__':asyncio.run(main())
