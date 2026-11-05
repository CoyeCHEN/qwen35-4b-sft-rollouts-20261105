"""Frozen recipe safety: changing initialization must not change the experiment."""
from pathlib import Path
import json
import tempfile
import unittest
from unittest.mock import patch
import yaml

from sft.runtime.config import initialize, native_arguments, validate_native
from sft.runtime.identity import training_source_sha256
from sft.runtime.new_entry_acceptance import new_entry_acceptance


class CalibForgeRecipeTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        root=Path(self.temp.name)
        initialize(root,'/base',root/'hot',root/'archive',['GPU-'+str(i)for i in range(4)])
        self.previous=yaml.safe_load((root/'configs/m2-128k.yaml').read_text())
        self.recipe=self.previous|dict(runtime_recipe='calibforge_appendix_e',learning_rate=1e-5,
            num_train_epochs=10,gradient_accumulation_steps=32,weight_decay=0.0,warmup_ratio=0.05,
            mask_history=False,save_strategy='epoch',eval_strategy='epoch',save_total_limit=None,
            load_best_model_at_end=False,eval_on_start=True)

    def tearDown(self):
        self.temp.cleanup()

    def test_previous_recipe_stays_frozen_and_new_recipe_requires_identity(self):
        validate_native(self.previous)
        validate_native(self.recipe)
        with self.assertRaises(ValueError):
            validate_native(native_arguments(self.recipe))
        with self.assertRaisesRegex(ValueError,'Unknown'):
            validate_native(self.recipe|dict(runtime_recipe='typo'))

    def test_shared_recipe_keeps_both_initializations_identical(self):
        routes=[self.recipe|dict(model_name_or_path=path,output_dir='/runs/'+name)
                for name,path in [('m3-a','/verified-m2'),('c1-b','/verified-m0')]]
        for cfg in routes:
            validate_native(cfg)
            self.assertNotIn('runtime_recipe',native_arguments(cfg))
            self.assertEqual(native_arguments(cfg)['num_train_epochs'],10)
        ignored={'model_name_or_path','output_dir'}
        self.assertEqual({k:v for k,v in routes[0].items()if k not in ignored},
                         {k:v for k,v in routes[1].items()if k not in ignored})

    def test_shortening_precision_or_checkpoint_rotation_cannot_slip_through(self):
        changes=dict(cutoff_len=98304,num_train_epochs=1,gradient_accumulation_steps=4,
            learning_rate=5e-7,pure_bf16=True,weight_decay=0.01,warmup_ratio=0.03,
            mask_history=True,save_total_limit=2,save_only_model=True,
            load_best_model_at_end=True,eval_on_start=False,lr_scheduler_kwargs={'min_lr':1e-6})
        for key,value in changes.items():
            with self.subTest(key=key),self.assertRaises(ValueError):
                validate_native(self.recipe|{key:value})

    def test_bounded_probe_is_separate_from_the_ten_epoch_formal_recipe(self):
        probe=self.recipe|dict(max_steps=3,save_steps=1,save_strategy='steps',
                               do_eval=False,eval_strategy='no',eval_on_start=False)
        validate_native(probe,bounded=True)
        with self.assertRaises(ValueError):
            validate_native(probe)
        with self.assertRaises(ValueError):
            validate_native(probe|dict(max_steps=2),bounded=True)

    def _acceptance_fixture(self,ga=32,parallelism=True):
        # Synthetic records only: these never become a runtime acceptance artifact.
        root=Path(self.temp.name)/'unit-records';root.mkdir(exist_ok=True)
        for rank in range(4):
            identity=dict(pid=100+rank,process_start_ticks='1',cuda_context='unit-only',
                          engine_id=1,optimizer_id=2)
            before=dict(weight_hashes={'norm':'unit-weight'},optimizer_state_sample_sha256='unit-adam',
                        scheduler_state={'last_epoch':2})
            begin=dict(event='train_begin',training_source_sha256=training_source_sha256(),
                gradient_accumulation_steps=32,learning_rate=1e-5,warmup_ratio=0.05,
                cutoff_len=131072,bf16=True,pure_bf16=False,runtime_recipe='calibforge_appendix_e',
                ignore_data_skip=False)
            if parallelism:
                begin['parallelism']=dict(world_size=4,data_parallel_group_size=4,
                    data_parallel_group_ranks=[0,1,2,3],microbatch_per_gpu=1,
                    gradient_accumulation_steps=32,effective_global_batch=128)
            events=[begin|dict(global_step=0,pid=identity['pid'])]
            for step in (1,2,3):
                if step==3:
                    events.append(begin|dict(global_step=2,pid=200+rank,
                        initial_weight_hashes=before['weight_hashes'],
                        optimizer_state_sample_sha256=before['optimizer_state_sample_sha256'],
                        scheduler_state=before['scheduler_state']))
                    events.append(dict(event='rng_restored',global_step=2,matches=dict(python=True,numpy=True,torch_cpu=True,torch_cuda=True)))
                events.append(dict(event='optimizer_step',global_step=step,identity=identity,
                    model_input_batches=[dict(nonpadding_tokens=131000,supervised_tokens=4000)]*ga,
                    gradients={'norm':dict(finite=True)},optimizer_moment_dtypes=['torch.float32'],
                    parameter_update_observed=step>1,**before))
                events.append(dict(event='metrics',global_step=step,metrics=dict(loss=1.0)))
                if step<3:
                    events.append(dict(event='checkpoint_save_complete',global_step=step,identity=identity,
                        process_context_engine_unchanged=True,training_state_unchanged=True))
            (root/f'preflight-evidence-rank{rank}.jsonl').write_text(''.join(json.dumps(e)+'\n'for e in events))
        (root/'trainer_state.json').write_text(json.dumps(dict(global_step=3)))
        return root

    def test_ga32_acceptance_requires_measured_batch_and_all_microbatches(self):
        root=self._acceptance_fixture()
        with patch('sft.runtime.new_entry_acceptance.validate_checkpoint'):
            self.assertTrue(new_entry_acceptance(root,131072,3000,configuration=self.recipe)['passed'])
        self._acceptance_fixture(ga=4)
        self.assertFalse(new_entry_acceptance(root,131072,configuration=self.recipe)['passed'])
        self._acceptance_fixture(parallelism=False)
        self.assertFalse(new_entry_acceptance(root,131072,configuration=self.recipe)['passed'])
        self._acceptance_fixture()
        # Old recipe/default acceptance must not admit the new recipe's evidence either.
        self.assertFalse(new_entry_acceptance(root,131072)['passed'])

    def test_frozen_corpus_input_signatures_replace_padding_or_unrelated_capacity_data(self):
        root=self._acceptance_fixture()
        a=dict(text_tokens=12000,loss_tokens=5000);b=dict(text_tokens=9000,loss_tokens=7000)
        contract=dict(allowed={('input-a','labels-a'):a,('input-b','labels-b'):b},
                      required={('input-a','labels-a'),('input-b','labels-b')},diagnostic_exposures=384)
        for rank in range(4):
            path=root/f'preflight-evidence-rank{rank}.jsonl';events=[json.loads(line)for line in path.read_text().splitlines()]
            for event in events:
                if event['event']=='optimizer_step':
                    event['model_input_batches']=[dict(sequence_tokens=(a if i%2==0 else b)['text_tokens']+66,
                        nonpadding_tokens=(a if i%2==0 else b)['text_tokens'],
                        supervised_tokens=(a if i%2==0 else b)['loss_tokens'],
                        input_sha256='input-a'if i%2==0 else'input-b',labels_sha256='labels-a'if i%2==0 else'labels-b',
                        canary_sample_index=rank*96+(event['global_step']-1)*32+i)for i in range(32)]
            path.write_text(''.join(json.dumps(event)+'\n'for event in events))
        with patch('sft.runtime.new_entry_acceptance.validate_checkpoint'):
            self.assertTrue(new_entry_acceptance(root,131072,configuration=self.recipe,input_contract=contract)['passed'])
            path=root/'preflight-evidence-rank0.jsonl'
            original=path.read_text()
            events=[json.loads(line)for line in path.read_text().splitlines()]
            resumed=next(event for event in events if event['event']=='optimizer_step'and event['global_step']==3)
            resumed['model_input_batches'][0]['canary_sample_index']=0
            path.write_text(''.join(json.dumps(event)+'\n'for event in events))
            failure=new_entry_acceptance(root,131072,configuration=self.recipe,input_contract=contract)
            self.assertFalse(failure['passed']);self.assertIn('data position',failure['reason'])
            events=[json.loads(line)for line in original.splitlines()]
            for event in events:
                if event['event']=='optimizer_step':
                    for batch in event['model_input_batches']:batch['labels_sha256']='other-labels'
            path.write_text(''.join(json.dumps(event)+'\n'for event in events))
            self.assertFalse(new_entry_acceptance(root,131072,configuration=self.recipe,input_contract=contract)['passed'])


if __name__=='__main__':
    unittest.main()
