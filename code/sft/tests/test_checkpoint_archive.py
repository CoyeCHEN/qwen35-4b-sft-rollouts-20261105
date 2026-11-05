"""Exercise file durability/rotation/failure boundaries without CUDA or model loads."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from sft.runtime import checkpoint_archive as archive


def fixture(path):
    path.mkdir(parents=True)
    files = {'trainer_state.json': json.dumps({'global_step': 1}), 'config.json': '{}',
             'scheduler.pt': 'scheduler', 'training_args.bin': 'args', 'latest': 'global_step1',
             'model.safetensors': 'model'}
    for rank in range(4):
        files[f'rng_state_{rank}.pth'] = 'rng'
        files[f'global_step1/zero_pp_rank_{rank}_mp_rank_00_model_states.pt'] = 'modelstate'
        files[f'global_step1/bf16_zero_pp_rank_{rank}_mp_rank_00_optim_states.pt'] = 'optimizer'
    for name, contents in files.items():
        file = path / name
        file.parent.mkdir(exist_ok=True, parents=True)
        file.write_text(contents)


class ArchiveContract(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='qwen35-archive-test-')
        self.root = Path(self.temp.name)
        self.source = self.root / 'run/checkpoint-1'
        fixture(self.source)
        archive.durable_completion(self.source, {'fixture_only': True, 'world_size': 4})
        self.settings = {key: str(self.root / key) for key in ('pin_root', 'queue_root', 'failed_root', 'archive_root')}
        self.settings['transfer_workers'] = 2
        Path(self.settings['archive_root']).mkdir()
        self.settings['archive_device']=self.root.stat().st_dev

    def tearDown(self):
        self.temp.cleanup()

    def test_rotation_archive_restore_and_corruption(self):
        archive.validate_checkpoint(self.source, world_size=4, require_marker=True)
        entry = archive.enqueue(self.source, self.settings, 'test-job')
        # Simulate Trainer rotation ONLY inside this temporary fixture.
        import shutil
        shutil.rmtree(self.source)
        result = archive.archive_one(entry, self.settings)
        destination = self.root / 'restore/checkpoint-1'
        archive.restore(result['archive'], destination, 1)
        self.assertEqual((destination / 'model.safetensors').read_text(), 'model')
        self.assertFalse(Path(entry['pin']).exists())
        (Path(result['archive']) / 'model.safetensors').write_text('wrong')
        with self.assertRaises(ValueError):
            archive.verify_archive(result['archive'])

    def test_incomplete_native_checkpoint_rejected(self):
        (self.source / 'rng_state_3.pth').unlink()
        with self.assertRaises(ValueError):
            archive.enqueue(self.source, self.settings, 'test-job')

    def test_mutated_pin_quarantines_queue_keeps_native(self):
        entry = archive.enqueue(self.source, self.settings, 'test-job')
        (Path(entry['pin']) / 'model.safetensors').write_text('mutation')
        self.assertEqual(archive.worker(self.settings), 1)
        self.assertTrue(self.source.exists())
        self.assertTrue(Path(entry['pin']).exists())
        self.assertFalse(list(Path(self.settings['queue_root']).glob('*.json')))
        self.assertEqual(len(list(Path(self.settings['failed_root']).glob('*.json'))), 1)

    def test_malformed_queue_is_not_busy_retried(self):
        queue = Path(self.settings['queue_root'])
        queue.mkdir()
        (queue / 'bad.json').write_text('broken-json')
        self.assertEqual(archive.worker(self.settings), 1)
        self.assertFalse(list(queue.glob('*.json')))

    def test_copy_failure_keeps_original_checkpoint_and_pin(self):
        before={item['path']:archive.sha256(self.source/item['path'])for item in archive.inventory(self.source)}
        entry=archive.enqueue(self.source,self.settings,'copy-failure')
        with patch.object(archive,'copy_files',side_effect=OSError('fixture: archive I/O unavailable')):
            self.assertEqual(archive.worker(self.settings),1)
        self.assertEqual(before,{item['path']:archive.sha256(self.source/item['path'])for item in archive.inventory(self.source)})
        self.assertTrue(Path(entry['pin']).is_dir())
        self.assertEqual(len(list(Path(self.settings['failed_root']).glob('*.json'))),1)

    def test_published_archive_is_not_recopied_after_worker_interruption(self):
        entry=archive.enqueue(self.source,self.settings,'publish-replay')
        first=archive.archive_one(entry,self.settings)
        with patch.object(archive,'copy_files',side_effect=AssertionError('must not recopy')):
            second=archive.archive_one(entry,self.settings)
        self.assertEqual(first['archive'],second['archive'])
        self.assertTrue(second['already_published'])

    def test_missing_archive_mount_keeps_original_and_quarantines(self):
        entry=archive.enqueue(self.source,self.settings,'mount-failure')
        self.settings['archive_device']+=1
        self.assertEqual(archive.worker(self.settings),1)
        self.assertTrue(self.source.exists());self.assertTrue(Path(entry['pin']).exists())


if __name__ == '__main__':
    unittest.main()
