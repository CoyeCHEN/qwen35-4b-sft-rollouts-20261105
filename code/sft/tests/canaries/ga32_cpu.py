"""Tiny native Trainer DP4/GA32 save/resume proof; never a Qwen/GPU acceptance."""
from pathlib import Path
import json,os,sys
import torch
import torch.distributed as dist
from transformers import Trainer,TrainingArguments,TrainerCallback

phase=sys.argv[1];root=Path(sys.argv[2]);root.mkdir(parents=True,exist_ok=True)
torch.set_num_threads(1);torch.manual_seed(42);seen=[];events=[]
class Model(torch.nn.Module):
    def __init__(self):super().__init__();self.weight=torch.nn.Parameter(torch.tensor([.25]))
    def forward(self,input_ids=None,labels=None,sample_index=None):
        seen.extend(sample_index.detach().cpu().flatten().tolist())
        value=input_ids.float()*self.weight
        return {'loss':(value-labels.float()).square().mean(),'logits':value}
class Data(torch.utils.data.Dataset):
    def __len__(self):return 384
    def __getitem__(self,index):return dict(input_ids=[index%7+1],labels=[0],sample_index=index)
class Observe(TrainerCallback):
    def on_train_begin(self,args,state,control,model=None,**kwargs):
        events.append(dict(event='begin',step=state.global_step,pid=os.getpid(),world_size=dist.get_world_size(),ga=args.gradient_accumulation_steps,
                           batch=args.per_device_train_batch_size,ignore_data_skip=args.ignore_data_skip))
    def on_step_end(self,args,state,control,**kwargs):
        events.append(dict(event='step',step=state.global_step,pid=os.getpid()))
        if phase=='initial'and state.global_step==2:control.should_save=True;control.should_training_stop=True
    def on_save(self,args,state,control,**kwargs):events.append(dict(event='save',step=state.global_step,pid=os.getpid()))

class CPUArguments(TrainingArguments):
    @property
    def device(self):
        # Accelerate's MULTI_CPU reports cpu:0; Torch 2.8 deserialization only
        # accepts canonical cpu. This tiny CPU fixture never changes GPU args.
        assert super().device.type=='cpu'
        return torch.device('cpu')

output=root/('reference'if phase=='reference'else'resumed')
args=CPUArguments(output_dir=str(output),use_cpu=True,ddp_backend='gloo',max_steps=3,
    per_device_train_batch_size=1,gradient_accumulation_steps=32,learning_rate=1e-5,weight_decay=0.,
    adam_beta1=.9,adam_beta2=.999,adam_epsilon=1e-8,lr_scheduler_type='cosine',warmup_ratio=.05,max_grad_norm=1.,
    optim='adamw_torch',seed=42,data_seed=42,save_strategy='steps',save_steps=1,save_only_model=False,
    logging_strategy='steps',logging_steps=1,report_to='none',disable_tqdm=True,dataloader_num_workers=0,
    remove_unused_columns=False,ddp_find_unused_parameters=False,ignore_data_skip=False)
trainer=Trainer(model=Model(),args=args,train_dataset=Data(),callbacks=[Observe()])
trainer.train(resume_from_checkpoint=str(output/'checkpoint-2')if phase=='resume'else None)
state=trainer.optimizer.state_dict();moments=[]
for values in state['state'].values():
    for key,value in values.items():
        if key in ('exp_avg','exp_avg_sq'):moments.append(str(value.dtype))
proof=dict(phase=phase,rank=dist.get_rank(),world_size=dist.get_world_size(),effective_global_batch=dist.get_world_size()*32,
    dtype=str(trainer.model.weight.dtype),adam_moment_dtypes=sorted(set(moments)),observed_sample_ids=seen,events=events,
    final_weight=trainer.model.weight.detach().cpu().tolist(),global_step=trainer.state.global_step,scheduler=trainer.lr_scheduler.state_dict(),
    cpu_only=True,cuda_initialized=torch.cuda.is_initialized(),scope='TINY_FIXTURE_NATIVE_DDP_FP32_NOT_QWEN_OR_ZERO3_GPU')
(root/(phase+'-rank'+str(dist.get_rank())+'.json')).write_text(json.dumps(proof,indent=2));dist.barrier();dist.destroy_process_group()
