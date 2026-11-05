"""Read the native E4 archive and subsequent updates; never invoke training."""
from datetime import datetime
import hashlib
import json
from pathlib import Path
import subprocess
import time

R = Path('/ssd/chenkeyi/qwen35-sft-772-20261101')


def read(path):
    return json.loads(path.read_text())


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def main():
    run = R / 'runs/new-m2-tmax356-128k-e5'
    checkpoint = run / 'checkpoint-100'
    settings = read(R / 'new-sft/workspace/configs/checkpoint-storage.json')
    archive = Path(settings['archive_root']) / 'new772-new-cf416-tmax356-m2/checkpoint-100'
    receipt = Path(settings['failed_root']).parent / 'archive-results/new772-new-cf416-tmax356-m2-checkpoint-100.json'
    marker = checkpoint / 'CHECKPOINT_COMPLETE.json'
    if not (archive / 'ARCHIVE_COMPLETE.json').exists() or not receipt.exists():
        print(json.dumps(dict(status='WAIT_NATIVE_ARCHIVE',checkpoint_complete=marker.exists())))
        return
    assert read(receipt)['status'] == 'completed'
    archived = read(archive / 'ARCHIVE_COMPLETE.json')
    ended = datetime.fromisoformat(archived['completed_at']).timestamp()
    members = {row['path']: row for row in archived['files']}
    assert len(members) == 26 and members['CHECKPOINT_COMPLETE.json']['sha256'] == sha(marker)
    ranks = {}
    for rank in range(4):
        path = run / ('preflight-evidence-rank' + str(rank) + '.jsonl')
        blob = path.read_bytes()
        complete_lines = blob[:blob.rfind(b'\n') + 1].splitlines()
        rows = [json.loads(line) for line in complete_lines]
        saved = next(row for row in rows if row['event'] == 'checkpoint_save_complete' and row['global_step'] == 100)
        later = next((row for row in rows if row['event'] == 'optimizer_step' and row['global_step'] > 100 and row['time'] > ended), None)
        if later is None:
            print(json.dumps(dict(status='WAIT_NATIVE_UPDATE_AFTER_ARCHIVE',rank=rank)))
            return
        assert later['master_partition_dtypes'] == later['optimizer_moment_dtypes'] == ['torch.float32']
        assert all(value['finite'] for value in later['gradients'].values())
        for field in ('pid','process_start_ticks','world_size','stage','config_sha256','cuda_context','model_id','engine_id','optimizer_id'):
            assert saved['identity'][field] == later['identity'][field]
        ranks[str(rank)] = dict(identity=saved['identity'],save_time=saved['time'],
                                first_post_archive_step=later['global_step'],first_post_archive_time=later['time'])
    state = read(checkpoint / 'trainer_state.json')
    assert state['global_step'] == 100 and state['epoch'] == 4.0
    subprocess.run([str(R/'env/train-r1/bin/python'),str(R/'read-native-training-evidence18-r1.py')],
                   check=True,capture_output=True,text=True,timeout=40)
    report_path = R / 'checks/NATIVE_TRAINING_READOUT_R1.json'
    report = read(report_path)
    stage = report['stages']['new-cf416-tmax356-m2']
    assert stage['validation_training_exposures'] == 0
    exposure_path = Path(stage['exposure_rows_path'])
    assert sha(exposure_path) == stage['exposure_rows_sha256']
    exposures = [json.loads(line) for line in exposure_path.open()]
    four = [row for row in exposures if row['optimizer_step'] <= 100]
    fourth = [row for row in four if row['optimizer_step'] > 75]
    assert len(four) == 3168 and len(fourth) == len({row['row_index'] for row in fourth}) == 792
    assert len({row['task_id'] for row in fourth}) == 325
    assert sum(row['supervised_tokens'] for row in four) == 31260844
    snapshots = {}
    for source,target in [(report_path,R/'checks/NEW_M2_EPOCH4_NATIVE_READOUT_SNAPSHOT_R1.json'),
                          (exposure_path,R/'checks/NEW_M2_EPOCH4_EXPOSURE_SNAPSHOT_R1.jsonl')]:
        with target.open('xb') as stream:
            stream.write(source.read_bytes())
        snapshots[target.name] = sha(target)
    proof = dict(passed=True,at=time.time(),actual_epoch=4,native_optimizer_steps_at_save=100,planned_steps=125,
                 actual_post_archive_step=min(row['first_post_archive_step'] for row in ranks.values()),ranks=ranks,
                 checkpoint_complete_marker_sha256=sha(marker),native_archive_manifest_sha256=sha(archive/'ARCHIVE_COMPLETE.json'),
                 native_archive_receipt_sha256=sha(receipt),archive_completed_at=archived['completed_at'],
                 archive_path=str(archive),files=len(members),bytes=sum(row['bytes'] for row in members.values()),
                 native_archive_metrics=archived['metrics'],four_epoch_sample_exposures=len(four),
                 epoch4_unique_train_rows=792,epoch4_independent_train_tasks=325,
                 four_epoch_supervised_tokens=31260844,validation_training_exposures=0,
                 exact_readout_and_exposure_snapshots=snapshots,hot_original_retained=True,
                 native_update_identities_preserved=True,new_optimizer_or_gpu_calls=0,
                 additional_epoch4_nll_or_hf_selection=False,source_sha256=sha(Path(__file__)))
    output = R / 'checks/NEW_M2_EPOCH4_NATIVE_ARCHIVE_ACCEPTANCE_R1.json'
    with output.open('x') as stream:
        stream.write(json.dumps(proof,indent=2)+'\n')
    print(json.dumps(proof))


if __name__ == '__main__':
    main()
