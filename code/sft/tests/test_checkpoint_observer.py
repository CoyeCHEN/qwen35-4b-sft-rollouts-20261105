"""Check observer boundary after the LAST callback; this is CPU fixture evidence only."""
import os
os.environ['CUDA_VISIBLE_DEVICES']=''
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import importlib.util
HAS_ML=all(importlib.util.find_spec(name)for name in ('torch','transformers','deepspeed'))
if HAS_ML:
    from transformers import Trainer
    from transformers.trainer_callback import CallbackHandler
    from sft.runtime.checkpoint_observer import CheckpointObserver
from tests.test_checkpoint_archive import fixture


@unittest.skipUnless(HAS_ML,'Pinned CPU framework environment required')
class SaveBoundary(unittest.TestCase):
    def test_rank0_stat_failure_broadcasts_error_before_exiting(self):
        import torch
        from sft.runtime.config import initialize
        with tempfile.TemporaryDirectory(prefix='rank0-storage-failure-')as temp:
            root=Path(temp)
            with patch.dict(os.environ,{'OPENHARNESS_SFT_WORKSPACE':temp}):
                initialize(root,'/model',root/'hot',root/'archive',['GPU-'+str(i)for i in range(4)])
                trainer=SimpleNamespace(state=SimpleNamespace(global_step=1,is_world_process_zero=True),args=SimpleNamespace(output_dir=temp))
                observer=CheckpointObserver(SimpleNamespace(record=lambda *a,**k:None),lambda x:None,True)
                with patch.object(Trainer,'_save_checkpoint')as native,patch.object(Trainer,'train',lambda *a,**k:None):
                    observer.install();observer.trainer=trainer
                    with patch.object(Path,'stat',side_effect=OSError('fixture: missing hot mount')),\
                         patch.object(torch.distributed,'is_initialized',return_value=True),\
                         patch.object(torch.distributed,'broadcast_object_list')as broadcast:
                        with self.assertRaisesRegex(RuntimeError,'missing hot mount'):Trainer._save_checkpoint(trainer)
                        broadcast.assert_called_once();self.assertIn('missing hot mount',broadcast.call_args.args[0][0])
                        native.assert_not_called()

    def test_late_callback_file_is_durable_and_engine_identity_is_stable(self):
        with tempfile.TemporaryDirectory(prefix='qwen35-save-boundary-') as temp:
            folder=Path(temp)/'checkpoint-1';events=[]
            scheduler=SimpleNamespace(state_dict=lambda:{'last_epoch':1})
            trainer=SimpleNamespace(state=SimpleNamespace(global_step=1,is_world_process_zero=True),
                args=SimpleNamespace(output_dir=temp),model=object(),model_wrapped=object(),optimizer=object(),lr_scheduler=scheduler)
            callback=SimpleNamespace(runtime_recipe='unit_fixture', bounded_acceptance=False,
                                     selected=[('weight',None)],weight=lambda value:'fixed-master-hash',
                                     record=lambda event,state,**data:events.append(dict(event=event,**data)))
            observer=CheckpointObserver(callback,lambda optimizer:{'Adam':'fixed'})
            # The native checkpoint fixture has four ranks; CUDA stays disabled.
            identity = observer.identity
            observer.identity = lambda: identity() | {'world_size': 4}
            def train(instance,*args,**kwargs):return None
            def save(instance,*args,**kwargs):fixture(folder)
            def last_callback(handler,args,state,control):
                (folder/'late-processor.json').write_text('{}')
                return control
            with patch.object(Trainer,'train',train),patch.object(Trainer,'_save_checkpoint',save),\
                 patch.object(CallbackHandler,'on_save',last_callback):
                observer.install()
                Trainer.train(trainer)
                Trainer._save_checkpoint(trainer)
                self.assertFalse((folder/'CHECKPOINT_COMPLETE.json').exists())
                CallbackHandler.on_save(None,trainer.args,trainer.state,object())
            marker=json.loads((folder/'CHECKPOINT_COMPLETE.json').read_text())
            self.assertIn('late-processor.json',{item['path']for item in marker['files']})
            final=next(e for e in events if e['event']=='checkpoint_save_complete')
            self.assertTrue(final['process_context_engine_unchanged'])
            self.assertTrue(final['training_state_unchanged'])
            self.assertIsNone(final['identity']['cuda_context'])


if __name__=='__main__':unittest.main()
