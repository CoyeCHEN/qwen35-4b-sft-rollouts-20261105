"""Opt-in tiny CPU updates with the pinned TMax Trainer/collator, never historical arms."""
import importlib.util
import os
from pathlib import Path
import sys
import tempfile
import unittest

STUDY=Path(__file__).resolve().parents[1]/'studies/tmax32k'
ENABLED=os.environ.get('TMAX_CPU_TESTS')=='1'


@unittest.skipUnless(ENABLED,'Set TMAX_CPU_TESTS=1 in the separate pinned TMax CPU environment')
class TMaxNativeCPU(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ['CUDA_VISIBLE_DEVICES']=''
        import torch,transformers
        if transformers.__version__!='5.14.0':raise RuntimeError('TMax CPU test requires its own Transformers 5.14.0 environment')
        torch.set_num_threads(1)
        def load(name,path):
            spec=importlib.util.spec_from_file_location(name,path);module=importlib.util.module_from_spec(spec)
            sys.modules[name]=module;spec.loader.exec_module(module);return module
        cls.data=load('sft_data',STUDY/'sources/original-sft_data.py')
        cls.native=load('pinned_tmax_cpu_trainer',STUDY/'sources/original-train.py')

    def test_original_tokenizer_Thinking_and_current_target_mask(self):
        import hashlib,json
        from transformers import AutoTokenizer
        from adapters.openharness_v2 import load_rollout
        from sft.tokenization import tokenize_trajectories,tokenize_call
        path=os.environ.get('TMAX_MODEL_PATH')
        if not path:self.skipTest('Provide the original fixed TMax tokenizer checkout; no automatic model download')
        identity=json.loads((STUDY/'historical-model-identities.json').read_text())[0]
        for name,digest in identity['auxiliary_files'].items():
            self.assertEqual(hashlib.sha256((Path(path)/name).read_bytes()).hexdigest(),digest)
        tokenizer=AutoTokenizer.from_pretrained(path,local_files_only=True)
        trajectory=load_rollout(STUDY.parents[1]/'fixtures/openharness_v2')
        samples=tokenize_trajectories([trajectory],tokenizer,max_length=32768)
        self.assertTrue(samples)
        for sample in samples:
            self.assertTrue(any(sample['loss_mask']))
            self.assertFalse(sample['loss_mask'][0])
            self.assertEqual(len(sample['loss_mask']),len(sample['input_ids']))
        synthetic=dict(call_id='synthetic-thinking-mask',request_messages=[
            dict(role='user',content='Synthetic question.'),dict(role='assistant',content='OLD_TARGET'),
            dict(role='user',content='Continue the synthetic fixture.')],
            assistant_response=dict(role='assistant',reasoning_content='CURRENT_REASON',content='CURRENT_ANSWER'))
        encoded=tokenize_call(synthetic,tokenizer,max_length=32768)
        supervised=tokenizer.decode([token for token,active in zip(encoded['input_ids'],encoded['loss_mask'])if active])
        self.assertIn('CURRENT_REASON',supervised);self.assertIn('CURRENT_ANSWER',supervised)
        self.assertNotIn('OLD_TARGET',supervised)

    def test_real_collator_masks_and_refuses_truncation(self):
        collator=self.data.MaskCollator(pad_token_id=0,max_length=8)
        batch=collator([dict(input_ids=[1,2,3,4],loss_mask=[0,0,1,1]),dict(input_ids=[1,5],loss_mask=[0,1])])
        self.assertEqual(batch['labels'].tolist(),[[-100,-100,3,4],[-100,5,-100,-100]])
        with self.assertRaisesRegex(ValueError,'truncation forbidden'):
            collator([dict(input_ids=[1]*9,loss_mask=[0]+[1]*8)])
        with self.assertRaisesRegex(ValueError,'Empty supervision'):
            collator([dict(input_ids=[1,2],loss_mask=[0,0])])

    def test_native_cpu_checkpoint_restores_then_updates(self):
        import random
        import numpy as np
        import torch
        from transformers import TrainingArguments,TrainerCallback
        from transformers.modeling_outputs import CausalLMOutput
        class Tiny(torch.nn.Module):
            def __init__(self):
                super().__init__();self.embedding=torch.nn.Embedding(16,8)
                self.model=torch.nn.Module();self.model.norm=torch.nn.LayerNorm(8);self.head=torch.nn.Linear(8,16)
            def forward(self,input_ids=None,attention_mask=None,labels=None,**kwargs):
                logits=self.head(self.model.norm(self.embedding(input_ids)))
                loss=torch.nn.functional.cross_entropy(logits[:,:-1].reshape(-1,16),labels[:,1:].reshape(-1),ignore_index=-100)
                return CausalLMOutput(loss=loss,logits=logits)
        events=[]
        class Observe(TrainerCallback):
            def on_save(self,args,state,control,**kwargs):
                events.append((state.global_step,os.getpid()))
                if state.global_step==1:control.should_training_stop=True
        rows=[dict(input_ids=[1,2,3,4],loss_mask=[0,0,1,1])for _ in range(4)]
        with tempfile.TemporaryDirectory(prefix='synthetic-tmax-cpu-')as directory:
            def arguments():return TrainingArguments(output_dir=directory,use_cpu=True,max_steps=2,per_device_train_batch_size=1,
                gradient_accumulation_steps=4,save_steps=1,logging_steps=1,report_to='none',disable_tqdm=True,remove_unused_columns=False,seed=42)
            model=Tiny();trainer=self.native.VerifiedTrainer(model=model,args=arguments(),train_dataset=rows,
                data_collator=self.data.MaskCollator(0,32768),callbacks=[Observe()])
            trainer.train();checkpoint=Path(directory)/'checkpoint-1';before={k:v.clone()for k,v in model.state_dict().items()}
            for name in ('model.safetensors','optimizer.pt','scheduler.pt','rng_state.pth','trainer_state.json'):
                self.assertTrue((checkpoint/name).is_file(),name)
            class Restored(TrainerCallback):
                def on_train_begin(self,args,state,control,model=None,optimizer=None,lr_scheduler=None,**kwargs):
                    self_outer.assertEqual(state.global_step,1)
                    self_outer.assertTrue(all(torch.equal(v,model.state_dict()[k])for k,v in before.items()))
                    saved=torch.load(checkpoint/'scheduler.pt',map_location='cpu',weights_only=False)
                    self_outer.assertEqual(saved,lr_scheduler.state_dict())
                    live=optimizer.state_dict()['state']
                    saved_optimizer=torch.load(checkpoint/'optimizer.pt',map_location='cpu',weights_only=False)['state']
                    self_outer.assertTrue(live)
                    self_outer.assertEqual(live.keys(),saved_optimizer.keys())
                    for parameter,values in saved_optimizer.items():
                        for name,value in values.items():
                            if torch.is_tensor(value):self_outer.assertTrue(torch.equal(value,live[parameter][name]))
                            else:self_outer.assertEqual(value,live[parameter][name])
            self_outer=self
            rng_checks=[]
            class ObserveRNG(self.native.VerifiedTrainer):
                def _load_rng_state(instance,path):
                    super()._load_rng_state(path)
                    if path is None:return
                    rng=torch.load(Path(path)/'rng_state.pth',map_location='cpu',weights_only=False)
                    self_outer.assertEqual(random.getstate(),rng['python'])
                    self_outer.assertTrue(torch.equal(torch.random.get_rng_state(),rng['cpu']))
                    current=np.random.get_state();saved=rng['numpy']
                    self_outer.assertEqual(current[0],saved[0]);self_outer.assertTrue(np.array_equal(current[1],saved[1]))
                    self_outer.assertEqual(current[2:],saved[2:]);rng_checks.append(True)
            resumed=ObserveRNG(model=Tiny(),args=arguments(),train_dataset=rows,
                data_collator=self.data.MaskCollator(0,32768),callbacks=[Restored()])
            resumed.train(resume_from_checkpoint=str(checkpoint))
            self.assertTrue(rng_checks)
            self.assertEqual(resumed.state.global_step,2)
            self.assertTrue(any(not torch.equal(v,resumed.model.state_dict()[k])for k,v in before.items()))
            self.assertFalse(torch.cuda.is_initialized())


if __name__=='__main__':unittest.main()
