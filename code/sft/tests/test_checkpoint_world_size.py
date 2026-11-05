import json
from pathlib import Path
import tempfile
import unittest

from sft.runtime.checkpoint_archive import validate_checkpoint


class CheckpointWorldSizeTests(unittest.TestCase):
    def checkpoint(self, root, world):
        (root / 'trainer_state.json').write_text(json.dumps(dict(global_step=2)))
        for name in ['config.json', 'scheduler.pt', 'training_args.bin', 'model.safetensors']:
            (root / name).write_bytes(b'native-placeholder')
        (root / 'latest').write_text('global_step2')
        shards = root / 'global_step2'
        shards.mkdir()
        for rank in range(world):
            (root / f'rng_state_{rank}.pth').write_bytes(b'rng')
            (shards / f'zero_pp_rank_{rank}_mp_rank_00_model_states.pt').write_bytes(b'model')
            (shards / f'bf16_zero_pp_rank_{rank}_mp_rank_00_optim_states.pt').write_bytes(b'adam')
        (root / 'CHECKPOINT_COMPLETE.json').write_text(json.dumps(dict(identity=dict(world_size=world), files=[])))

    def test_eight_rank_marker_requires_rank_seven_optimizer(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.checkpoint(root, 8)
            validate_checkpoint(root, require_marker=True)
            (root / 'global_step2/bf16_zero_pp_rank_7_mp_rank_00_optim_states.pt').unlink()
            with self.assertRaisesRegex(ValueError, 'rank 7'):
                validate_checkpoint(root, require_marker=True)

    def test_unsealed_checkpoint_needs_explicit_world_size(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.checkpoint(root, 4)
            (root / 'CHECKPOINT_COMPLETE.json').unlink()
            with self.assertRaisesRegex(ValueError, 'Explicit world size'):
                validate_checkpoint(root)
            validate_checkpoint(root, world_size=4)
