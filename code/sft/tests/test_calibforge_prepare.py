"""No model/data downloads: approval, whole-task rejection and text budgets."""
import copy
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from sft.prepare import prepare_calibforge,read_approval


class CalibForgePreparationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        for name in ('checks','manifests'): (self.root/name).mkdir()
        self.env=patch.dict(os.environ,{'OPENHARNESS_SFT_WORKSPACE':str(self.root)})
        self.env.start();self.addCleanup(self.env.stop)
        self.approval=self.root/'approval.json';self.contract=self.root/'contract.json'
        self.contract.write_text(json.dumps(dict(status='APPROVED',finish=False,schema_sha256=['unit-schema'])))
        self.entries=[dict(task_id='unit-'+split,task_group_id='group-'+split,trial_id='trial-'+split,split=split,
            origin=dict(kind='published_harbor_task',dataset='AweAI-Team/CalibForge',
                revision='c2fae4c1f536461142b2a89a8b9423a8bc376088'))for split in ('train','validation')]
        self.write()

    def write(self):
        self.approval.write_text(json.dumps(dict(purpose='formal_calibforge',entries=self.entries)))

    def test_no_data_wrong_purpose_and_task_leakage_fail_before_tokenizer_load(self):
        with patch('sft.qwen35.load_tokenizer')as load:
            self.approval.write_text(json.dumps(dict(purpose='formal_m2',entries=self.entries)))
            with self.assertRaises(ValueError):prepare_calibforge(self.approval,self.contract)
            self.entries=[];self.write()
            with self.assertRaises(ValueError):prepare_calibforge(self.approval,self.contract)
            load.assert_not_called()

    def test_public_source_identity_and_group_split_are_not_optional(self):
        self.entries[1]['task_group_id']=self.entries[0]['task_group_id'];self.write()
        with self.assertRaisesRegex(ValueError,'Task group leakage'):read_approval(self.approval,purpose='formal_calibforge')
        self.entries[1]['task_group_id']='group-validation'
        self.entries[0]['origin']['kind']='authored_non_evaluation_task';self.write()
        with patch('sft.qwen35.load_tokenizer')as load:
            with self.assertRaisesRegex(ValueError,'public CalibForge provenance'):prepare_calibforge(self.approval,self.contract)
            load.assert_not_called()

    def run_mock_preparation(self,encode):
        def consume(name,generators,manifest,finalize):
            # A mock sink, never Arrow files, approved sources, or formal training.
            self.rows={key:list(generator())for key,generator in generators.items()}
            finalize();return copy.deepcopy(manifest)
        def source(entry):return [{'call_id':'call-'+entry['split']}],{'unit_test_only':True}
        with patch('sft.qwen35.load_tokenizer',return_value=object()),patch('sft.sources.read_source',side_effect=source),\
             patch('sft.qwen35.encode_multiturn_task',side_effect=encode),patch('sft.prepare.publish',side_effect=consume):
            return prepare_calibforge(self.approval,self.contract)

    def test_whole_task_rows_share_frozen_order_and_reserve_actual_native_overhead(self):
        def encode(tokenizer,calls,*,cutoff):
            self.assertEqual(cutoff,131006)
            token=1 if calls[0]['call_id']=='call-train'else 2
            return dict(input_ids=[token],labels=[token]),dict(input_sha256=str(token),tools_sha256='unit-schema',
                text_tokens=1,loss_tokens=1,decision_mapping=[dict(call_id=calls[0]['call_id'])])
        manifest=self.run_mock_preparation(encode)
        self.assertEqual(manifest['cutoff'],131072)
        self.assertEqual(manifest['native_collator_reserved_tokens'],66)
        self.assertEqual(manifest['supervision_scope'],'all_assistant_once')
        self.assertEqual([self.rows[s][0]['input_ids']for s in ('train','validation')],[[1],[2]])
        self.assertEqual(manifest['counts']['train']['decisions'],1)
        self.assertFalse((self.root/'data').exists())

    def test_overlong_context_rejects_whole_task_instead_of_truncating(self):
        def encode(*args,**kwargs):raise ValueError('EXCEEDS_CUTOFF_NO_TRUNCATION:131007>131006')
        with self.assertRaisesRegex(ValueError,'No approved complete multi-turn samples'):
            self.run_mock_preparation(encode)
        proof=json.loads((self.root/'checks/calibforge-128k-quality.json').read_text())
        self.assertIn('NO_TRUNCATION',proof['exclusions'][0]['reason'])
        self.assertFalse((self.root/'manifests/calibforge-128k.json').exists())


if __name__=='__main__':unittest.main()
