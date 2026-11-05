"""Single Trainer entry point for all Full SFT stages, with explicit correctness gates."""
import argparse
import hashlib
import importlib.metadata
import inspect
import json
import math
import os
import platform
import time
from pathlib import Path

import torch
from datasets import load_dataset
from transformers import AutoModelForCausalLM, AutoTokenizer, Qwen3_5ForCausalLM, Trainer, TrainerCallback, TrainingArguments, set_seed
from transformers.models.qwen3_5 import modeling_qwen3_5 as qwen_modeling

from sft_data import MaskCollator

ROOT = Path(__file__).resolve().parent

def write_json(path, value):
    def serialize(obj):
        if isinstance(obj, set):
            return sorted(obj)
        raise TypeError(f'Unsupported report value: {type(obj).__name__}')
    Path(path).write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False, default=serialize))

def load_text_model(path, liger, attention='sdpa', model_family='qwen3_5'):
    model_cls = AutoModelForCausalLM if model_family == 'tmax2b' else Qwen3_5ForCausalLM
    model, info = model_cls.from_pretrained(
        path, dtype=torch.bfloat16, attn_implementation=attention, local_files_only=True,
        output_loading_info=True)
    if info.get('missing_keys') or info.get('mismatched_keys') or info.get('error_msgs'):
        raise RuntimeError(f'Incomplete pretrained language weights: {info}')
    model.config.use_cache = False
    model.requires_grad_(True)
    if liger:
        from liger_kernel.transformers import apply_liger_kernel_to_qwen3_5
        apply_liger_kernel_to_qwen3_5(model=model, rope=False, rms_norm=False, swiglu=False,
                                    cross_entropy=False, fused_linear_cross_entropy=True)
        assert model.forward.__func__.__module__ == 'liger_kernel.transformers.model.qwen3_5'
    return model, info

class VerifiedTrainer(Trainer):
    """Use Liger's documented skip_logits path for train AND eval (eval mode preserved)."""
    def compute_loss(self, model, inputs, return_outputs=False, num_items_in_batch=None):
        inputs = dict(inputs)
        if getattr(self, 'use_fused_ce', False):
            inputs['skip_logits'] = True
        if num_items_in_batch is not None:
            inputs['num_items_in_batch'] = num_items_in_batch
        outputs = model(**inputs)
        loss = outputs.loss
        if not torch.isfinite(loss):
            raise FloatingPointError(f'Nonfinite loss at step {self.state.global_step}')
        if getattr(self, 'use_fused_ce', False):
            assert outputs.logits is None, 'FLCE did not eliminate full logits'
        return (loss, outputs) if return_outputs else loss

    def training_step(self, model, inputs, num_items_in_batch=None):
        self.context_tokens = getattr(self, 'context_tokens', 0) + int(inputs['attention_mask'].sum())
        self.supervised_tokens = getattr(self, 'supervised_tokens', 0) + int((inputs['labels'] != -100).sum())
        return super().training_step(model, inputs, num_items_in_batch)

class AuditCallback(TrainerCallback):
    def __init__(self, model, out):
        self.out = out
        self.probes = {n: p.detach().flatten()[:4096].float().cpu().clone()
                       for n, p in model.named_parameters()
                       if any(s in n for s in ['layers.0.mlp.down_proj.weight', 'layers.3.self_attn.q_proj.weight', 'model.norm.weight'])}
        self.gradient_reports = []

    def on_pre_optimizer_step(self, args, state, control, model=None, **kwargs):
        if state.global_step < 2:
            total, nonzero, missing = 0, 0, []
            for n, p in model.named_parameters():
                if not p.requires_grad:
                    raise RuntimeError(f'Unexpected frozen language parameter {n}')
                total += 1
                if p.grad is None:
                    missing.append(n); continue
                if not torch.isfinite(p.grad).all():
                    raise FloatingPointError(f'Nonfinite gradient {n}')
                nonzero += int(torch.count_nonzero(p.grad).item() > 0)
            assert not missing and nonzero > 0, (missing, nonzero)
            self.gradient_reports.append({'step': state.global_step, 'parameters': total,
                                          'nonzero_gradients': nonzero, 'all_finite': True, 'missing': missing})
            write_json(self.out / 'gradient_checks.json', self.gradient_reports)

    def updates(self, model):
        records = {}
        params = dict(model.named_parameters())
        for n, before in self.probes.items():
            now = params[n].detach().flatten()[:4096].float().cpu()
            records[n] = {'changed_elements': int((now != before).sum()), 'max_absolute_change': float((now-before).abs().max())}
        assert any(r['changed_elements'] > 0 for r in records.values()), 'No measured parameter updates'
        return records

def selected_dataset(split, limit, count, seed):
    path = ROOT / f'data/NiuNiu0110--TMax-Agent-SFT-terminus/data/pretokenized/{split}.parquet'
    dataset = load_dataset('parquet', data_files=str(path), split='train')
    dataset = dataset.filter(lambda r: len(r['input_ids']) <= limit)
    if count:
        if len(dataset) < count:
            raise ValueError(f'{split}: insufficient complete trajectories')
        dataset = dataset.shuffle(seed=seed).select(range(count))
    return dataset

def dataset_summary(dataset):
    return {'rows':len(dataset), 'context_tokens':sum(dataset['n_tokens']),
            'supervised_tokens':sum(dataset['n_trained_tokens']),
            'trajectory_ids':list(dataset['trajectory_id'])}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--config', required=True)
    ap.add_argument('--resume', default=None)
    args = ap.parse_args()
    cfg = json.loads(Path(args.config).read_text())
    out = ROOT / 'runs' / cfg['run_name']
    if out.exists() and not args.resume:
        raise RuntimeError(f'Run already exists, refusing overwrite: {out}')
    if args.resume:
        old = json.loads((out/'config.json').read_text())
        assert old == cfg, 'Resume configuration differs'
        ckpt = Path(args.resume)
        assert all((ckpt/name).exists() for name in ['optimizer.pt','scheduler.pt','trainer_state.json'])
        print('RESUME', (ckpt/'trainer_state.json').read_text(), flush=True)
    else:
        out.mkdir(parents=True)
        write_json(out/'config.json', cfg)
    report_name = cfg.get('validation_report', 'data_validation.json')
    report = json.loads((ROOT/'reports' / report_name).read_text())
    if cfg.get('model_family') == 'tmax2b':
        assert all(report['splits'][s]['all_rows_exact_tmax2b_tokenizer_match'] for s in ['train','holdout'])
        assert all(report['splits'][s]['all_rows_exact_author_mask_match'] for s in ['train','holdout'])
    else:
        assert all(report['splits'][s]['all_rows_exact_tokenizer_match'] for s in ['train','holdout'])
    set_seed(cfg['seed'])
    torch.set_num_threads(8)
    model_path = ROOT / cfg.get('model_path', 'models/Qwen--Qwen3.5-0.8B')
    tokenizer = AutoTokenizer.from_pretrained(model_path, local_files_only=True)
    train = selected_dataset('train', cfg['max_length'], cfg['train_rows'], cfg['seed'])
    holdout = selected_dataset('holdout', cfg['max_length'], cfg['holdout_rows'], cfg['seed'])
    assert not set(train['task_group_id']) & set(holdout['task_group_id'])
    collator = MaskCollator(tokenizer.pad_token_id, cfg['max_length'])
    assert cfg['precision'] == 'bf16'
    assert qwen_modeling.is_fast_path_available, 'Qwen3.5 fast GDN/conv path required; run verify_fast_kernels.py'
    model, loading = load_text_model(model_path, cfg['liger'], cfg['attention'], cfg.get('model_family', 'qwen3_5'))
    total = sum(p.numel() for p in model.parameters())
    assert total == sum(p.numel() for p in model.parameters() if p.requires_grad)
    model.to('cuda')
    model.gradient_checkpointing_enable(gradient_checkpointing_kwargs={'use_reentrant': False})
    callback = AuditCallback(model, out)
    training_args = TrainingArguments(
        output_dir=str(out), per_device_train_batch_size=cfg['per_device_batch_size'], per_device_eval_batch_size=1,
        gradient_accumulation_steps=cfg['gradient_accumulation'], learning_rate=cfg['learning_rate'],
        lr_scheduler_type=cfg['scheduler'], warmup_ratio=cfg['warmup_ratio'], weight_decay=cfg['weight_decay'],
        max_grad_norm=cfg['max_grad_norm'], num_train_epochs=cfg['epochs'], max_steps=cfg['max_steps'], bf16=True,
        optim=cfg['optimizer'], gradient_checkpointing=cfg['gradient_checkpointing'],
        gradient_checkpointing_kwargs={'use_reentrant':False}, seed=cfg['seed'],
        logging_steps=cfg['logging_steps'], eval_strategy='steps', eval_steps=cfg['eval_steps'],
        save_strategy='steps', save_steps=cfg['save_steps'], save_total_limit=1,
        remove_unused_columns=False, report_to='none', prediction_loss_only=True,
        dataloader_num_workers=0, disable_tqdm=True, average_tokens_across_devices=False)
    trainer = VerifiedTrainer(model=model, args=training_args, train_dataset=train,
                              eval_dataset=holdout, data_collator=collator, callbacks=[callback],
                              processing_class=tokenizer)
    trainer.use_fused_ce = cfg['liger']
    train_info, holdout_info = dataset_summary(train), dataset_summary(holdout)
    env = {'python':platform.python_version(), 'gpu':torch.cuda.get_device_name(),
           'visible_devices':os.environ.get('CUDA_VISIBLE_DEVICES'), 'gpu_count':torch.cuda.device_count(),
           'cuda':torch.version.cuda, 'parameters':total, 'trainable_parameters':total,
           'model_class':type(model).__name__, 'excluded_components':['vision tower','MTP head'],
           'loading_info':loading, 'liger_forward':model.forward.__func__.__module__,
           'versions':{n:importlib.metadata.version(n) for n in ['torch','transformers','datasets','accelerate','liger-kernel','tokenizers','flash-linear-attention','causal-conv1d']},
           'complete_qwen_fast_path':qwen_modeling.is_fast_path_available,
           'train_rows':train_info['rows'], 'holdout_rows':holdout_info['rows'],
           'train_supervised_tokens':train_info['supervised_tokens'], 'train_context_tokens':train_info['context_tokens'],
           'holdout_supervised_tokens':holdout_info['supervised_tokens'],
           'train_trajectory_ids':train_info['trajectory_ids'], 'holdout_trajectory_ids':holdout_info['trajectory_ids']}
    write_json(out/'environment.json', env)
    train_eval = train.select(range(min(100,len(train))))
    before_holdout = trainer.evaluate(metric_key_prefix='holdout_before')
    before_train = trainer.evaluate(train_eval, metric_key_prefix='train_before')
    write_json(out/'baseline.json', {**before_holdout, **before_train})
    torch.cuda.reset_peak_memory_stats()
    started = time.time()
    result = trainer.train(resume_from_checkpoint=args.resume)
    elapsed = time.time()-started
    peak = torch.cuda.max_memory_allocated()/2**30
    updates = callback.updates(model)
    after_holdout = trainer.evaluate(metric_key_prefix='holdout_after')
    after_train = trainer.evaluate(train_eval, metric_key_prefix='train_after')
    trainer.save_model(str(out/'final'))
    trainer.save_state()
    tokenizer.save_pretrained(out/'final')
    # Prove the export contains exactly the trained tensors. The pure-Torch GDN
    # path can give slightly different BF16 losses on repeated evals of one model,
    # so a single strict loss equality is not a sound checkpoint integrity gate.
    batch = {k:v.to('cuda') for k,v in collator([holdout[0]]).items()}
    model.eval()
    reloaded, reload_info = load_text_model(out/'final', cfg['liger'], cfg['attention'], cfg.get('model_family', 'qwen3_5'))
    reloaded.to('cuda').eval()
    original_state, reload_state = model.state_dict(), reloaded.state_dict()
    assert original_state.keys() == reload_state.keys(), 'Reloaded state keys differ'
    mismatched = [key for key in original_state if not torch.equal(original_state[key], reload_state[key])]
    assert not mismatched, f'Reloaded tensors differ: {mismatched[:5]}'
    with torch.no_grad():
        original_losses = [trainer.compute_loss(model,batch).item() for _ in range(8)]
    with torch.no_grad():
        reload_losses = [trainer.compute_loss(reloaded,batch).item() for _ in range(8)]
    original, reload_loss = sum(original_losses)/len(original_losses), sum(reload_losses)/len(reload_losses)
    assert math.isclose(original,reload_loss,abs_tol=0.002,rel_tol=0.002), (original_losses,reload_losses)
    del reloaded
    summary = {'completed':True,'global_step':trainer.state.global_step,'elapsed_seconds':elapsed,
               'peak_allocated_gib':peak,'train_metrics':result.metrics, **before_holdout, **before_train,
               **after_holdout, **after_train, 'parameter_updates':updates, 'checkpoint':str(out/'final'),
               'reload_loss':reload_loss,'original_loss':original,
               'reload_loss_samples':reload_losses,'original_loss_samples':original_losses,
               'reload_exact_tensor_match':True,'reload_loading_info':reload_info,
               'actual_context_tokens':trainer.context_tokens,'actual_supervised_tokens':trainer.supervised_tokens,
               'context_tokens_per_second':trainer.context_tokens/elapsed,
               'supervised_tokens_per_second':trainer.supervised_tokens/elapsed}
    if cfg.get('require_overfit'):
        assert after_train['train_after_loss'] < before_train['train_before_loss'] * 0.9, 'Overfit gate needs at least 10% train loss reduction'
    write_json(out/'result.json',summary)
    print((out/'result.json').read_text(),flush=True)

if __name__ == '__main__':
    main()
