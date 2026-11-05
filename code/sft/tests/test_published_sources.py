"""Public task provenance is not an authored-task alias or automatic approval."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import os
import shutil

from sft import qwen35 as codec
from sft.published import approved_scope, collection_scope, task_origin,source_files_sha256
from sft.collection import freeze
from sft.runtime.checkpoint_archive import sha256
from sft.sources import read_source


class PublishedSourceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name); task = self.root/'task'; task.mkdir()
        for name in ('instruction.md', 'task.toml', 'tests/test.sh', 'environment/Dockerfile'):
            p = task/name; p.parent.mkdir(exist_ok=True); p.write_text('unit fixture only: '+name)
        files = [dict(path=str(p), relative_path=str(p.relative_to(task)), sha256=sha256(p))
                 for p in sorted(task.rglob('*')) if p.is_file()]
        origin = dict(kind='published_harbor_task', dataset='unit/public', revision='a'*40,
                      source_split='train', instance_id='public-unit', task_group='group-a',
                      source_task_path='release/public-unit', source_files=files)
        self.task = dict(task_id='public-unit', task_group_id='group-a', split='train',
                         source_split='train', source_task_path='release/public-unit',
                         source_files_sha256=source_files_sha256(files), origin=origin, path=str(task))
        self.review = self.root/'review.json'
        self.review_data = dict(kind='evaluation_isolation_review', status='APPROVED',
            dataset='unit/public', revision='a'*40, retained_evaluation_sets=['terminal-bench-2.1'],
            tasks={'public-unit':dict(decision='APPROVED', source_files_sha256=source_files_sha256(files))})
        self.review.write_text(json.dumps(self.review_data))
        self.scope = dict(kind='approved_published_harbor_tasks', status='APPROVED',
            dataset='unit/public', revision='a'*40, license='unit-test-only', tasks=[self.task],
            isolation_review=str(self.review), isolation_review_sha256=sha256(self.review),
            execution_contract=dict(harness_commit='b'*40, harbor_commit='c'*40, harness_wheel_sha256='d'*64))

    def test_public_identity_preserves_source_split_separately_from_sft_split(self):
        self.assertEqual(approved_scope(self.scope), self.scope['execution_contract'])
        task = copy.deepcopy(self.task); task['split'] = 'validation'
        task_origin(task['origin'], task, self.scope)

    def test_pending_scope_and_lexical_screen_cannot_approve_public_data(self):
        self.scope['status'] = 'PENDING'
        with self.assertRaisesRegex(ValueError, 'not approved'): approved_scope(self.scope)
        self.scope['status'] = 'APPROVED'; self.review_data['kind'] = 'lexical_screen_only'
        self.review.write_text(json.dumps(self.review_data)); self.scope['isolation_review_sha256'] = sha256(self.review)
        with self.assertRaisesRegex(ValueError, 'lexical screening'): approved_scope(self.scope)

    def test_source_cannot_be_relabelled_authored_or_changed_revision(self):
        for key, value in [('kind','authored_non_evaluation_task'), ('revision','e'*40), ('source_split','test'), ('instance_id','renamed')]:
            with self.subTest(key=key):
                origin = copy.deepcopy(self.task['origin']); origin[key] = value
                with self.assertRaisesRegex(ValueError, 'identity/original split'): task_origin(origin,self.task,self.scope)

    def test_byte_identical_source_snapshot_is_portable_but_hashes_stay_binding(self):
        origin=copy.deepcopy(self.task['origin'])
        for index,item in enumerate(origin['source_files']):
            copy_path=self.root/('snapshot-'+str(index));shutil.copyfile(item['path'],copy_path)
            item['path']=str(copy_path)
        task_origin(origin,self.task,self.scope)
        self.assertEqual(source_files_sha256(origin['source_files']),self.task['source_files_sha256'])
        Path(origin['source_files'][0]['path']).write_text('corrupt copied source')
        with self.assertRaisesRegex(ValueError,'file identity'):task_origin(origin,self.task,self.scope)

    def test_missing_verifier_or_modified_source_is_rejected(self):
        origin = copy.deepcopy(self.task['origin']); origin['source_files'] = origin['source_files'][:-1]
        with self.assertRaises(ValueError): task_origin(origin,self.task,self.scope)
        Path(self.task['origin']['source_files'][0]['path']).write_text('changed')
        with self.assertRaisesRegex(ValueError, 'file identity'): task_origin(self.task['origin'],self.task,self.scope)

    def test_review_hash_task_identity_and_group_leakage_are_checked(self):
        with self.subTest('sha'):
            self.scope['isolation_review_sha256'] = '0'*64
            with self.assertRaisesRegex(ValueError, 'SHA mismatch'): approved_scope(self.scope)
        self.scope['isolation_review_sha256'] = sha256(self.review)
        other = dict(self.task, task_id='other-unit', split='validation')
        self.scope['tasks'].append(other)
        with self.assertRaisesRegex(ValueError, 'split leakage'): approved_scope(self.scope)

    def test_collection_execution_contract_is_pinned_to_approved_public_scope(self):
        scope_path = self.root/'scope.json'; scope_path.write_text(json.dumps(self.scope))
        identity = dict(self.scope['execution_contract'], approved_scope=str(scope_path), approved_scope_sha256=sha256(scope_path))
        entry = dict(task_id=self.task['task_id'], task_group_id='group-a', split='train', origin=self.task['origin'])
        self.assertEqual(collection_scope(entry,identity), self.scope['execution_contract'])
        identity['harbor_commit'] = 'f'*40
        with self.assertRaisesRegex(ValueError, 'execution contract'): collection_scope(entry,identity)

    def test_native_freeze_uses_public_contract_without_relabel_or_execution(self):
        workspace = self.root/'workspace'
        for name in ('manifests','configs'): (workspace/name).mkdir(parents=True)
        wheel = self.root/'unit.whl'; wheel.write_bytes(b'unit fixture, never installed')
        self.scope['execution_contract']['harness_wheel_sha256'] = sha256(wheel)
        scope_path = self.root/'scope.json'; scope_path.write_text(json.dumps(self.scope))
        base = self.root/'base.json'; base.write_text(json.dumps(dict(agents=[dict(kwargs={})])))
        with patch.dict(os.environ, {'OPENHARNESS_SFT_WORKSPACE':str(workspace)}):
            result = freeze(scope_path,base,wheel,'deepseek/unit-test','UNIT_TEST_NOT_A_REAL_COLLECTION')
        identity = json.loads(Path(result['collection']).read_text())
        self.assertFalse(result['executed'])
        self.assertEqual(identity['kind'],'published_harbor_teacher_collection')
        self.assertEqual(identity['harness_commit'],'b'*40)
        self.assertEqual(identity['approved_scope_sha256'],sha256(scope_path))
        entry = dict(task_id=self.task['task_id'],task_group_id='group-a',split='train',origin=self.task['origin'])
        self.assertEqual(collection_scope(entry,identity),self.scope['execution_contract'])
        self.assertFalse((workspace/'manifests/m2-approved-sources.json').exists())

    def native_trial_entry(self):
        """Artificial unit files only; no real collection or approval is written."""
        trial = self.root/'trial'; raw = trial/'agent/openharness-rollout'
        shutil.copytree(Path(__file__).parents[1]/'fixtures/openharness_v2',raw)
        events = [json.loads(line) for line in (raw/'events.jsonl').read_text().splitlines()]
        for event in events:
            if event['type']=='call_end': event['data']['response']['role']='assistant'
            if event['type']=='call_payload':
                event['data'] = dict(call_id='call-1', fidelity='provider_payload', payload=dict(
                    model='unit-test', messages=[dict(role='user',content='Unit fixture instruction')]))
        (raw/'events.jsonl').write_text(''.join(json.dumps(event)+'\n' for event in events))
        (trial/'agent/open-harness.complete.json').write_text(json.dumps(dict(exit_code=0)))
        installed = trial/'agent/artifact.json'
        installed.write_text(json.dumps(dict(wheel_sha256='d'*64,profile='native-cli-v1',cli_contract='openharness-cli-v1')))
        options = dict(wheel_sha256='d'*64,profile='native-cli-v1',record_trajectory=True)
        result = trial/'result.json'
        result.write_text(json.dumps(dict(id='trial-unit',task_name='public-unit',
            verifier_result=dict(rewards={'reward':1},return_code=0),config=dict(agent=dict(
                import_path='harbor.agents.installed.open_harness:OpenHarnessAgent',
                model_name='deepseek/unit-test',kwargs=options)))))
        scope_path = self.root/'scope.json'; scope_path.write_text(json.dumps(self.scope))
        identity = dict(kind='published_harbor_teacher_collection',**self.scope['execution_contract'],
            approved_scope=str(scope_path),approved_scope_sha256=sha256(scope_path),
            teacher_model='deepseek/unit-test',teacher_model_version_basis='UNIT_TEST_ONLY',
            approved_tasks=[self.task],agent_options_sha256=codec.digest(options))
        collection = self.root/'collection.json'; collection.write_text(json.dumps(identity))
        return dict(task_id='public-unit',task_group_id='group-a',split='train',trial_id='trial-unit',
            origin=self.task['origin'],harbor_result=str(result),harbor_result_sha256=sha256(result),
            collection_manifest=str(collection),collection_manifest_sha256=sha256(collection),
            installed_artifact=str(installed),installed_artifact_sha256=sha256(installed),
            rollout_export_dir=str(raw),recorder_manifest_sha256=sha256(raw/'manifest.json'),
            raw_recorders=[dict(path=str(raw),manifest_sha256=sha256(raw/'manifest.json'),events_sha256=sha256(raw/'events.jsonl'))])

    def test_raw_native_recorder_is_checked_without_inventing_export_integrity_fields(self):
        entry = self.native_trial_entry()
        calls, identity = read_source(entry)
        self.assertEqual(len(calls),1)
        self.assertEqual(calls[0]['context_fidelity'],'provider_payload')
        self.assertTrue(identity['formal_training_eligible'])
        # A complete marker alone cannot turn an interrupted native run into data.
        raw = Path(entry['rollout_export_dir']); path = raw/'events.jsonl'
        path.write_text('\n'.join(path.read_text().splitlines()[:-1])+'\n')
        entry['raw_recorders'][0]['events_sha256'] = sha256(path)
        with self.assertRaisesRegex(ValueError,'Recorder closure'): read_source(entry)

    def test_reward_one_does_not_override_agent_exit_or_secondary_errors(self):
        entry = self.native_trial_entry(); result = Path(entry['harbor_result'])
        completion = result.parent/'agent/open-harness.complete.json'
        completion.write_text(json.dumps(dict(exit_code=137)))
        with self.assertRaisesRegex(ValueError,'Normal Agent completion'): read_source(entry)
        completion.write_text(json.dumps(dict(exit_code=0)))
        data = json.loads(result.read_text()); data['secondary_errors'] = [{'phase':'cleanup'}]
        result.write_text(json.dumps(data)); entry['harbor_result_sha256'] = sha256(result)
        with self.assertRaisesRegex(ValueError,'Harbor identity/error'): read_source(entry)


if __name__ == '__main__': unittest.main()
