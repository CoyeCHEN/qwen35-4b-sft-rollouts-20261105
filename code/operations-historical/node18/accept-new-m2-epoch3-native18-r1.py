"""Audit native E3 save/archive, immutable HF lineage and real training exposure."""
import hashlib
import json
from pathlib import Path
import subprocess
import time
from datetime import datetime

R = Path('/ssd/chenkeyi/qwen35-sft-772-20261101')


def read(path):
    return json.loads(path.read_text())


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def main():
    run = R / 'runs/new-m2-tmax356-128k-e5'
    checkpoint = run / 'checkpoint-75'
    marker = checkpoint / 'CHECKPOINT_COMPLETE.json'
    settings = read(R / 'new-sft/workspace/configs/checkpoint-storage.json')
    archive = Path(settings['archive_root']) / 'new772-new-cf416-tmax356-m2/checkpoint-75'
    receipt = Path(settings['failed_root']).parent / 'archive-results/new772-new-cf416-tmax356-m2-checkpoint-75.json'
    assert read(receipt)['status'] == 'completed'
    archived = read(archive / 'ARCHIVE_COMPLETE.json')
    ended = datetime.fromisoformat(archived['completed_at']).timestamp()
    members = {f['path']: f for f in archived['files']}
    assert len(members) == 26 and members['CHECKPOINT_COMPLETE.json']['sha256'] == sha(marker)
    hf_path = R / 'epoch-models/new-m2-epoch3/EPOCH_MODEL_EXPORT_COMPLETE.json'
    hf = read(hf_path)
    assert hf['optimizer_step'] == 75 and hf['epoch'] == 3 and hf['is_final_epoch5_model'] is False
    assert hf['source_complete_checkpoint_sha256'] == sha(marker)
    hf_weights = {f['name']: f['sha256'] for f in hf['files'] if f['name'].endswith('.safetensors')}
    assert hf_weights['model.safetensors'] == members['model.safetensors']['sha256']
    rank_evidence = {}
    for rank in range(4):
        rows = [json.loads(line) for line in (run / ('preflight-evidence-rank' + str(rank) + '.jsonl')).open()]
        saved = next(e for e in rows if e['event'] == 'checkpoint_save_complete' and e['global_step'] == 75)
        update = next(e for e in rows if e['event'] == 'optimizer_step' and e['global_step'] == 75)
        later = next(e for e in rows if e['event'] == 'optimizer_step' and e['global_step'] > 75 and e['time'] > ended)
        assert update['master_partition_dtypes'] == update['optimizer_moment_dtypes'] == ['torch.float32']
        assert all(g['finite'] for g in update['gradients'].values())
        stable = ['pid', 'process_start_ticks', 'world_size', 'stage', 'config_sha256',
            'cuda_context', 'model_id', 'engine_id', 'optimizer_id']
        assert all(saved['identity'][k] == later['identity'][k] for k in stable)
        assert saved['identity']['config_sha256'] == '1f48ed160a76bea910857bf16c94776f06e1d77a45c76047686303e72e91c716'
        rank_evidence[str(rank)] = dict(save_time=saved['time'], identity=saved['identity'],
            first_optimizer_step_after_archive=later['global_step'], first_post_archive_time=later['time'])
    assert read(checkpoint / 'trainer_state.json')['global_step'] == 75
    subprocess.run([str(R / 'env/train-r1/bin/python'), str(R / 'read-native-training-evidence18-r1.py')],
        check=True, capture_output=True, text=True, timeout=40)
    path = R / 'checks/NATIVE_TRAINING_READOUT_R1.json'
    report = read(path)
    stage = report['stages']['new-cf416-tmax356-m2']
    exposure_path = Path(stage['exposure_rows_path'])
    assert sha(exposure_path) == stage['exposure_rows_sha256']
    exposure = [json.loads(line) for line in exposure_path.open()]
    three = [e for e in exposure if e['optimizer_step'] <= 75]
    third = [e for e in three if e['optimizer_step'] > 50]
    assert len(three) == 2376 and len(third) == len({e['row_index'] for e in third}) == 792
    assert len({e['task_id'] for e in third}) == 325
    assert sum(e['supervised_tokens'] for e in third) == 7815211
    assert sum(e['supervised_tokens'] for e in three) == 23445633
    assert stage['validation_training_exposures'] == 0
    snapshots = {}
    for source, target in [(path, R / 'checks/NEW_M2_EPOCH3_ARCHIVE_NATIVE_READOUT_SNAPSHOT_R1.json'),
                           (exposure_path, R / 'checks/NEW_M2_EPOCH3_ARCHIVE_EXPOSURE_SNAPSHOT_R1.jsonl')]:
        assert not target.exists()
        target.write_bytes(source.read_bytes())
        snapshots[target.name] = sha(target)
    value = dict(passed=True, at=time.time(), actual_epoch=3, native_optimizer_steps_at_save=75,
        planned_optimizer_steps=125, actual_post_archive_step=min(v['first_optimizer_step_after_archive'] for v in rank_evidence.values()),
        checkpoint_complete_marker_sha256=sha(marker), ranks=rank_evidence,
        native_archive_manifest_sha256=sha(archive/'ARCHIVE_COMPLETE.json'), native_archive_receipt_sha256=sha(receipt),
        archive_completed_at=archived['completed_at'], archive_path=str(archive), files=len(members),
        bytes=sum(f['bytes'] for f in members.values()), native_archive_metrics=archived['metrics'],
        hf_manifest_sha256=sha(hf_path), hf_weights=hf_weights, three_epoch_sample_exposures=2376,
        epoch3_unique_train_rows=792, epoch3_independent_train_tasks=325, epoch3_supervised_tokens=7815211,
        three_epoch_supervised_tokens=23445633, validation_training_exposures=0,
        exact_readout_and_exposure_snapshots=snapshots, hot_original_retained=True,
        native_archive_worker_verified_source_and_copy_sha=True, native_update_identities_preserved=True,
        new_model_or_optimizer_calls=0, independent_nll_or_agent_success_not_claimed=True,
        source_sha256=sha(Path(__file__)))
    output = R / 'checks/NEW_M2_EPOCH3_NATIVE_ARCHIVE_ACCEPTANCE_R1.json'
    assert not output.exists()
    output.write_text(json.dumps(value, indent=2) + '\n')
    print(json.dumps(value))


if __name__ == '__main__':
    main()
