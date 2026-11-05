"""Native CPU computation/lifecycle tests; no claim of GPU or ZeRO-3 capacity."""
import importlib.util
import os
os.environ['CUDA_VISIBLE_DEVICES']=''
from pathlib import Path
import tempfile
import unittest

HAS_ML=all(importlib.util.find_spec(name)for name in ('torch','transformers','accelerate','deepspeed'))


@unittest.skipUnless(HAS_ML,'Pinned CPU framework environment required')
class NativeCPU(unittest.TestCase):
    def test_telemetry_write_failure_does_not_interrupt_native_training(self):
        from unittest.mock import patch
        from sft.runtime.lf_train import EvidenceCallback
        callback=EvidenceCallback('/unused',False)
        with patch.object(Path,'open',side_effect=OSError('fixture: evidence log unavailable')),patch.object(Path,'mkdir'):
            callback.record('optimizer_step',type('State',(),{'global_step':1})(),gradient_finite=True)

    def test_real_warmup_zero_LR_is_not_a_failed_parameter_update(self):
        import time
        import torch
        from transformers import Trainer,TrainingArguments
        from sft.runtime.lf_train import EvidenceCallback
        events=[]
        class Model(torch.nn.Module):
            def __init__(self):
                super().__init__();self.a=torch.nn.Parameter(torch.ones(1));self.b=torch.nn.Parameter(torch.ones(1))
            def forward(self,input_ids=None,labels=None):
                logits=input_ids.float()*self.a+self.b
                return dict(loss=(logits-labels.float()).square().mean(),logits=logits)
        class Observe(EvidenceCallback):
            def on_train_begin(self,args,state,control,model=None,**kwargs):
                # Only the full-model range check is replaced for this tiny
                # CPU fixture; use the real step/LR/parameter guards below.
                self.started=time.monotonic();self.cutoff=8
                model.register_forward_pre_hook(self.observe_batch,with_kwargs=True)
                self.selected=list(model.named_parameters());self.initial={name:self.weight(p)for name,p in self.selected}
                for name,p in self.selected:
                    def capture(g,name=name):
                        self.gradients[name]=dict(norm=float(g.norm()),finite=bool(torch.isfinite(g).all()),dtype=str(g.dtype));return g
                    p.register_hook(capture)
            def record(self,event,state,**data):events.append(dict(event=event,step=state.global_step,**data))
        with tempfile.TemporaryDirectory(prefix='native-zero-LR-warmup-')as directory:
            callback=Observe(directory,False)
            args=TrainingArguments(output_dir=directory,use_cpu=True,max_steps=2,warmup_ratio=.03,
                per_device_train_batch_size=1,save_strategy='no',logging_steps=1,report_to='none',disable_tqdm=True)
            Trainer(model=Model(),args=args,train_dataset=[dict(input_ids=[1],labels=[0]),dict(input_ids=[2],labels=[0])],callbacks=[callback]).train()
            steps=[e for e in events if e['event']=='optimizer_step']
            self.assertTrue(steps[0]['optimizer_step_learning_rates'])
            self.assertTrue(all(rate==0.0 for rate in steps[0]['optimizer_step_learning_rates']))
            self.assertFalse(steps[0]['parameter_update_observed'])
            self.assertTrue(steps[1]['parameter_update_observed'])
            self.assertTrue(any(e['event']=='train_end'for e in events))
            callback.gradients={name:dict(finite=True)for name,p in callback.selected}
            callback.step_learning_rates=[1e-5]
            callback.on_step_end(args,type('State',(),{'global_step':3})(),None)
            self.assertFalse([e for e in events if e['event']=='optimizer_step'][-1]['parameter_update_observed'])
            self.assertFalse(torch.cuda.is_initialized())

    def test_real_FP32_Adam_cosine_tail_can_round_away_a_nonzero_update(self):
        import math
        import torch
        parameter=torch.nn.Parameter(torch.ones(2,dtype=torch.float32))
        # Frozen M1's penultimate cosine learning rate, after 10 warmup steps.
        rate=2e-6*0.5*(1+math.cos(math.pi*(332-10)/(333-10)))
        self.assertGreater(rate,0)
        optimizer=torch.optim.AdamW([parameter],lr=rate,weight_decay=.01,eps=1e-8)
        parameter.grad=torch.ones_like(parameter)
        before=parameter.detach().clone();optimizer.step()
        self.assertTrue(torch.equal(before,parameter))
        self.assertEqual(float(optimizer.state[parameter]['step']),1)
        self.assertEqual(optimizer.state[parameter]['exp_avg'].dtype,torch.float32)

    def test_native_save_then_step2_keeps_same_PID(self):
        import torch
        from transformers import Trainer,TrainingArguments,TrainerCallback
        torch.set_num_threads(1)
        class Model(torch.nn.Module):
            def __init__(self):super().__init__();self.weight=torch.nn.Parameter(torch.ones(1))
            def forward(self,input_ids=None,labels=None):
                logits=input_ids.float()*self.weight
                return dict(loss=(logits-labels.float()).square().mean(),logits=logits)
        class Data(torch.utils.data.Dataset):
            def __len__(self):return 2
            def __getitem__(self,index):return dict(input_ids=[index+1],labels=[0])
        events=[]
        class Observe(TrainerCallback):
            def on_step_end(self,args,state,control,**kwargs):events.append(('step',state.global_step,os.getpid()))
            def on_save(self,args,state,control,**kwargs):events.append(('save',state.global_step,os.getpid()))
        with tempfile.TemporaryDirectory(prefix='native-cpu-save-')as temp:
            model=Model();before=model.weight.detach().clone()
            args=TrainingArguments(output_dir=temp,use_cpu=True,max_steps=2,per_device_train_batch_size=1,save_steps=1,
                save_total_limit=2,logging_steps=1,report_to='none',disable_tqdm=True,dataloader_num_workers=0)
            trainer=Trainer(model=model,args=args,train_dataset=Data(),callbacks=[Observe()]);trainer.train()
            self.assertEqual([e[:2]for e in events],[('step',1),('save',1),('step',2),('save',2)])
            self.assertEqual({e[2]for e in events},{os.getpid()})
            self.assertFalse(torch.equal(before,model.weight))
            self.assertTrue((Path(temp)/'checkpoint-1/optimizer.pt').is_file())
            self.assertFalse(torch.cuda.is_initialized())

    def test_dataloader_IO_exception_is_propagated(self):
        import torch
        class Broken(torch.utils.data.Dataset):
            def __len__(self):return 1
            def __getitem__(self,index):raise OSError('fixture: cache read failed')
        with self.assertRaisesRegex(OSError,'cache read failed'):next(iter(torch.utils.data.DataLoader(Broken(),num_workers=0)))

    def test_all_masked_or_overlong_real_tensor_batch_is_refused(self):
        import torch
        from sft.runtime.lf_train import EvidenceCallback
        callback=EvidenceCallback('/unused',False);callback.cutoff=8
        with self.assertRaisesRegex(RuntimeError,'All assistant labels'):
            callback.observe_batch(torch.nn.Linear(1,1),(),{'labels':torch.full((1,8),-100)})
        with self.assertRaisesRegex(RuntimeError,'cutoff'):
            callback.observe_batch(torch.nn.Linear(1,1),(),{'labels':torch.zeros((1,9),dtype=torch.long)})


if __name__=='__main__':unittest.main()

@unittest.skipUnless(HAS_ML,'Pinned CPU framework environment required')
class NativeResumeContract(unittest.TestCase):
    def test_GA4_warmup_stop2_resume3_matches_uninterrupted_data_and_weights(self):
        import torch
        from transformers import Trainer,TrainingArguments
        from sft.runtime.lf_train import StopAfterCheckpoint
        torch.set_num_threads(1)
        class Model(torch.nn.Module):
            def __init__(self):super().__init__();self.weight=torch.nn.Parameter(torch.ones(1))
            def forward(self,input_ids=None,labels=None):
                logits=input_ids.float()*self.weight
                return dict(loss=(logits-labels.float()).square().mean(),logits=logits)
        data=[dict(input_ids=[i+1],labels=[i%3])for i in range(24)]
        with tempfile.TemporaryDirectory()as directory:
            def args(name):return TrainingArguments(output_dir=str(Path(directory)/name),use_cpu=True,max_steps=3,
                gradient_accumulation_steps=4,per_device_train_batch_size=1,learning_rate=2e-6,warmup_ratio=.03,
                seed=42,data_seed=42,save_steps=1,save_total_limit=3,report_to='none',disable_tqdm=True)
            reference=Trainer(model=Model(),args=args('reference'),train_dataset=data);reference.train()
            first=Trainer(model=Model(),args=args('resumed'),train_dataset=data,callbacks=[StopAfterCheckpoint()]);first.train()
            self.assertEqual(first.state.global_step,2)
            second=Trainer(model=Model(),args=args('resumed'),train_dataset=data)
            second.train(resume_from_checkpoint=str(Path(directory)/'resumed/checkpoint-2'))
            self.assertEqual(second.state.global_step,3)
            self.assertTrue(torch.equal(reference.model.weight,second.model.weight))
            self.assertEqual(reference.lr_scheduler.state_dict(),second.lr_scheduler.state_dict())
            a=reference.optimizer.state_dict()['state'];b=second.optimizer.state_dict()['state']
            for key in a:
                for state in a[key]:self.assertTrue(torch.equal(a[key][state],b[key][state]))
