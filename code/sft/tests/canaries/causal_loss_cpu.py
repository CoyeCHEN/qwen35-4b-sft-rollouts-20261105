"""Numerical native-LF causal loss/DDP/GA check; tiny CPU models, no SFT output.

This checks loss and gradient reduction, not Qwen/ZeRO/Liger GPU kernels.
Run with torchrun --nproc_per_node=4 and the pinned training environment.
"""
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import tempfile

import torch
import torch.nn.functional as F
from transformers import AutoProcessor, LlamaConfig, LlamaForCausalLM, TrainerCallback
from llamafactory.hparams import FinetuningArguments, TrainingArguments
from llamafactory.train.sft.trainer import CustomSeq2SeqTrainer


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', required=True)
    parser.add_argument('--model', default='/data/models/Qwen/Qwen3.5-4B')
    args = parser.parse_args()
    torch.set_num_threads(1)
    processor = AutoProcessor.from_pretrained(args.model, local_files_only=True)
    results = []
    for ga in (4, 32):
        count = 4*ga
        torch.manual_seed(314)
        config = LlamaConfig(vocab_size=128, hidden_size=16, intermediate_size=32,
            num_hidden_layers=1, num_attention_heads=2, num_key_value_heads=2,
            attention_dropout=0.0, max_position_embeddings=128)
        config._attn_implementation = 'eager'
        model = LlamaForCausalLM(config)
        reference = copy.deepcopy(model)
        samples = []
        for i in range(count):
            ids = [i % 127 + 1] + [(i*7+j*11) % 127+1 for j in range(1, 8)]
            labels = [-100]*(8-(i % 6+1)) + ids[-(i % 6+1):]
            samples.append(dict(input_ids=ids, attention_mask=[1]*8, labels=labels))
        loss_values = []
        target_counts = []
        for sample in samples:
            ids = torch.tensor([sample['input_ids']])
            labels = torch.tensor(sample['labels'][1:])
            logits = reference(input_ids=ids, use_cache=False).logits[0, :-1].float()
            loss = F.cross_entropy(logits, labels, ignore_index=-100, reduction='mean')
            (loss/count).backward()
            loss_values.append(float(loss.detach()))
            target_counts.append(int((labels != -100).sum()))
        reference_unclipped_norm = float(torch.nn.utils.clip_grad_norm_(reference.parameters(), 1.0))
        expected = {name: p.grad.detach().clone() for name,p in reference.named_parameters() if p.grad is not None}
        captured = {}

        class Observe(TrainerCallback):
            def on_pre_optimizer_step(self, training_args, state, control, model=None, **kwargs):
                got = {name.removeprefix('module.'): p.grad.detach().clone()
                    for name,p in model.named_parameters() if p.grad is not None}
                assert set(got) == set(expected)
                errors = {name:float((got[name]-expected[name]).abs().max()) for name in got}
                captured.update(max_gradient_absolute_error=max(errors.values()),
                    gradients_match=all(torch.allclose(got[name], expected[name], rtol=3e-5, atol=2e-6) for name in got),
                    gradients_finite=all(bool(torch.isfinite(value).all()) for value in got.values()))

        with tempfile.TemporaryDirectory(prefix='lf-causal-cpu-') as temporary:
            train_args = TrainingArguments(output_dir=temporary, use_cpu=True, max_steps=1,
                gradient_accumulation_steps=ga, per_device_train_batch_size=1,
                learning_rate=1e-5, warmup_ratio=0.0, weight_decay=0.0,
                max_grad_norm=1.0, optim='adamw_torch', save_strategy='no',
                logging_steps=1, report_to='none', disable_tqdm=True, dataloader_num_workers=0,
                ddp_find_unused_parameters=False, seed=42, data_seed=42)
            trainer = CustomSeq2SeqTrainer(model=model, args=train_args,
                finetuning_args=FinetuningArguments(finetuning_type='full'),
                processor=processor, tokenizer=processor.tokenizer,
                train_dataset=samples, callbacks=[Observe()])
            assert trainer.model_accepts_loss_kwargs is False
            trained = trainer.train()
            assert torch.distributed.get_world_size() == 4
            per_rank = [None]*4
            torch.distributed.all_gather_object(per_rank, captured)
            mean = sum(loss_values)/count
            token_mean = sum(x*n for x,n in zip(loss_values,target_counts))/sum(target_counts)
            state_dtypes = sorted({str(value.dtype) for state in trainer.optimizer.state.values()
                for key,value in state.items() if key in ('exp_avg','exp_avg_sq')})
            row = dict(gradient_accumulation=ga, world_size=4, global_batch=count,
                trainer_class=type(trainer).__name__, model_accepts_loss_kwargs=False,
                native_loss=trained.training_loss, manual_sample_mean_loss=mean,
                manual_token_weighted_loss=token_mean,
                loss_matches=abs(trained.training_loss-mean)<2e-5,
                reference_unclipped_gradient_norm=reference_unclipped_norm,
                target_counts=target_counts, rank_gradient_checks=per_rank,
                optimizer_moment_dtypes=state_dtypes, global_step=trainer.state.global_step,
                reference_shift_count=1, observation_padding_mask_value=-100)
            row['passed'] = bool(row['loss_matches'] and all(x['gradients_match'] and x['gradients_finite'] for x in per_rank)
                and state_dtypes == ['torch.float32'] and trainer.state.global_step == 1)
            results.append(row)
            if torch.distributed.get_rank()==0:
                print(json.dumps({'ga':ga,'passed':row['passed'],'native_loss':row['native_loss'],
                    'reference_loss':mean,'rank_max_gradient_error':max(x['max_gradient_absolute_error'] for x in per_rank)}),flush=True)
        del trainer,model,reference,expected
        torch.distributed.barrier()
    result = dict(passed=all(x['passed'] for x in results), cases=results,
        scope='Actual LF Trainer plus native causal-LM loss and CPU DDP/GA; tiny Llama model only',
        qwen_gpu_forward_verified=False, liger_gpu_kernel_verified=False,
        deepspeed_zero_gpu_verified=False, cuda_initialized=torch.cuda.is_initialized(),
        source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    if torch.distributed.get_rank()==0:
        output=Path(args.output);output.parent.mkdir(parents=True,exist_ok=True)
        with output.open('x') as stream:json.dump(result,stream,indent=2)
    assert result['passed'] and not result['cuda_initialized']
    torch.distributed.destroy_process_group()


if __name__=='__main__':
    main()
