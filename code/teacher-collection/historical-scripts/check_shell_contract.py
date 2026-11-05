"""Exercise the exact IO executor used by the frozen Bash tool on a temp fixture."""
import asyncio
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import zipfile

ROOT=Path('/home/chenkeyi/.local/share/harbor-rsi/qwen35-new-cf500-tmax500-20261029')
WHEEL=Path('/home/chenkeyi/.local/share/harbor-rsi/qwen35-m1-m2-tb21-20261026/wheels/null-delta/open_harness_ai-0.3.0-py3-none-any.whl')
assert hashlib.sha256(WHEEL.read_bytes()).hexdigest()=='f84f810e8a61545d685fb6722593886a0c88cc829b2ab9ca7c3476fe11e1209e'
sys.path.insert(0,str(WHEEL))
from foundation.io import createLocalBashOperations


async def main():
    operations=createLocalBashOperations({'shellPath':'/bin/bash'})
    with tempfile.TemporaryDirectory(prefix='qwen35-shell-contract-')as temporary:
        root=Path(temporary);(root/'child').mkdir()
        (root/'seed.sh').write_text('export QWEN_STUDY_SOURCE_VAR=source_value\nstudy_fixture_function() { printf function_value; }\n')
        async def call(command):
            chunks=[]
            async def receive(data):chunks.append(data)
            result=await operations.exec(command,str(root),{'timeout':5,'onData':receive})
            return dict(command=command,exit_code=result['exitCode'],output=b''.join(chunks).decode())
        results=[]
        for command in ['cd child; pwd','pwd','export QWEN_STUDY_VAR=export_value',
                        'printf "%s" "${QWEN_STUDY_VAR-unset}"','source ./seed.sh',
                        'printf "%s" "${QWEN_STUDY_SOURCE_VAR-unset}"; type study_fixture_function 2>/dev/null || true']:
            results.append(await call(command))
        assert results[0]['output'].strip()==str(root/'child')
        assert results[1]['output'].strip()==str(root)
        assert results[3]['output']=='unset' and results[5]['output']=='unset'
        for row in results:row['output']=row['output'].replace(str(root),'<owned-temporary-directory>')
    with zipfile.ZipFile(WHEEL)as archive:
        source=archive.read('rsi_modules/capabilities/tools/bash.py')
    proof=dict(passed=True,executor='frozen foundation.io.createLocalBashOperations',
        same_operations_object=True,working_directory_persisted=False,export_persisted=False,
        sourced_environment_and_function_persisted=False,results=results,
        wheel_sha256=hashlib.sha256(WHEEL.read_bytes()).hexdigest(),bash_source_sha256=hashlib.sha256(source).hexdigest(),
        scope='IO executor behind the exact Bash tool, not a re-execution of a benchmark or original persistent-shell agent',
        model_calls=0,temporary_resources_cleaned=True)
    (ROOT/'checks/shell-contract.json').write_text(json.dumps(proof,indent=2));print(json.dumps(proof))


asyncio.run(main())
