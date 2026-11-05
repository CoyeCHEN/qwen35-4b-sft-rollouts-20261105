"""Native collection configuration only; no teacher calls or formal-data fixtures."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from sft.collection import freeze
from sft.runtime.config import initialize


class CollectionTests(unittest.TestCase):
    def test_native_scope_is_frozen_without_execution_and_rejects_group_leakage(self):
        with tempfile.TemporaryDirectory()as directory:
            root=Path(directory)
            with patch.dict(os.environ,{'OPENHARNESS_SFT_WORKSPACE':str(root/'workspace')}):
                initialize(root/'workspace','/model',root/'hot',root/'archive',['GPU-'+str(i)for i in range(4)])
                wheel=root/'fixture.whl';wheel.write_bytes(b'not-a-real-wheel; never installed')
                base=root/'job.json';base.write_text(json.dumps(dict(agents=[dict(kwargs={})],environment=dict(type='docker'))))
                tasks=[]
                for index,split in enumerate(('train','validation')):
                    task=root/f'authored-{index}';task.mkdir();(task/'instruction.md').write_text(f'Unit fixture {index}; never execute or approve as data.')
                    tasks.append(dict(task_id=task.name,task_group_id='same-group',split=split,path=str(task),origin='authored_non_evaluation_task'))
                scope=root/'scope.json'
                scope.write_text(json.dumps(dict(kind='approved_independent_tasks',tasks=tasks)))
                with self.assertRaisesRegex(ValueError,'leakage'):freeze(scope,base,wheel,'deepseek/accepted-fixture','unit-test-only')
                tasks[1]['task_group_id']='separate-group';scope.write_text(json.dumps(dict(kind='approved_independent_tasks',tasks=tasks)))
                result=freeze(scope,base,wheel,'deepseek/accepted-fixture','unit-test-only')
                self.assertFalse(result['executed'])
                job=json.loads(Path(result['native_job_config']).read_text())
                agent=job['agents'][0]
                self.assertEqual(agent['import_path'],'harbor.agents.installed.open_harness:OpenHarnessAgent')
                self.assertTrue(agent['kwargs']['record_trajectory'])
                self.assertEqual(agent['kwargs']['profile'],'native-cli-v1')
                self.assertEqual(agent['env']['DEEPSEEK_API_KEY'],'${DEEPSEEK_API_KEY}')
                self.assertEqual(len(job['tasks']),2)
                self.assertEqual(json.loads((root/'workspace/manifests/m2-approved-sources.json').read_text())['entries'],[])
                with self.assertRaises(FileExistsError):freeze(scope,base,wheel,'deepseek/accepted-fixture','unit-test-only')


if __name__=='__main__':unittest.main()
