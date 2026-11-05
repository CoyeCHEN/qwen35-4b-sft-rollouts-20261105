import unittest
import tempfile
from pathlib import Path
import yaml
from sft.runtime.config import initialize,validate_native
from sft.runtime.new_entry_acceptance import new_entry_acceptance
from sft.runtime.identity import training_source_sha256

class LaunchAcceptance(unittest.TestCase):
    def test_formal_and_bounded_are_separate_and_keep_frozen_hyperparameters(self):
        with tempfile.TemporaryDirectory()as folder:
            root=Path(folder);initialize(root,'/fixed',root/'hot',root/'archive',['GPU-'+str(i)for i in range(4)])
            cfg=yaml.safe_load((root/'configs/m1-64k.yaml').read_text())
            validate_native(cfg)
            bounded=cfg|dict(max_steps=3,save_steps=1,do_eval=False)
            with self.assertRaisesRegex(ValueError,'no bounded'):validate_native(bounded)
            validate_native(bounded,bounded=True)
            for field,value in [('gradient_accumulation_steps',1),('warmup_ratio',0.0),('seed',1),('learning_rate',1e-5),('mask_history',True)]:
                with self.subTest(field=field),self.assertRaises(ValueError):validate_native(bounded|{field:value},bounded=True)
    def test_old_GPU_directory_cannot_satisfy_new_entry(self):
        self.assertFalse(new_entry_acceptance(None,65536)['passed'])
        with tempfile.TemporaryDirectory()as folder:self.assertFalse(new_entry_acceptance(folder,131072)['passed'])
        self.assertEqual(len(training_source_sha256()),64)

    def test_pending_candidate_release_never_becomes_formal_data(self):
        import json
        from sft.prepare import adopt_m2_candidates
        with tempfile.TemporaryDirectory()as folder:
            approval=Path(folder)/'pending.json';approval.write_text(json.dumps(dict(status='PENDING_TOOL_DECISION',classification='TB21_SAME_TASK_ADAPTATION')))
            with self.assertRaisesRegex(ValueError,'not approved'):adopt_m2_candidates(approval)

    def test_ZeRO3_config_change_is_rejected(self):
        import json
        with tempfile.TemporaryDirectory()as folder:
            root=Path(folder);initialize(root,'/fixed',root/'hot',root/'archive',['GPU-'+str(i)for i in range(4)])
            cfg=yaml.safe_load((root/'configs/m1-64k.yaml').read_text());path=Path(cfg['deepspeed']);ds=json.loads(path.read_text());ds['zero_optimization']['stage']=2;path.write_text(json.dumps(ds))
            with self.assertRaisesRegex(ValueError,'ZeRO-3'):validate_native(cfg)

    def test_M1_HF_gate_requires_generation_proof_and_unchanged_files(self):
        import json
        from sft.runtime.hf_export import final_verified
        from sft.runtime.checkpoint_archive import sha256
        with tempfile.TemporaryDirectory()as folder:
            p=Path(folder);(p/'trainer_state.json').write_text(json.dumps(dict(epoch=1,global_step=333,max_steps=333)));(p/'config.json').write_text('{}');w=p/'model.safetensors';w.write_bytes(b'unit fixture')
            self.assertFalse(final_verified(p))
            seal=p/'HF_EXPORT_COMPLETE.json';seal.write_text(json.dumps(dict(complete_final_hf=True,base_revision='851bf6e806efd8d0a36b00ddf55e13ccb7b8cd0a',files=[dict(path=w.name,bytes=w.stat().st_size,mtime_ns=w.stat().st_mtime_ns,sha256=sha256(w))])))
            self.assertFalse(final_verified(p))
            (p/'HF_LOAD_SMOKE.json').write_text(json.dumps(dict(model_loaded=True,generated_tokens=1,export_manifest_sha256=sha256(seal))))
            self.assertTrue(final_verified(p));w.write_bytes(b'changed file');self.assertFalse(final_verified(p))

    def test_partial_epoch_budget_is_not_a_complete_final_export(self):
        import json
        from sft.runtime.launch import exported_m1
        with tempfile.TemporaryDirectory()as folder:
            path=Path(folder)
            (path/'config.json').write_text('{}')
            (path/'model.safetensors').write_bytes(b'unit fixture; not a real model')
            for state in (dict(epoch=2,global_step=20,max_steps=100),dict(epoch=2,global_step=20)):
                (path/'trainer_state.json').write_text(json.dumps(state))
                with self.assertRaisesRegex(ValueError,'budget incomplete'):
                    exported_m1(path)
