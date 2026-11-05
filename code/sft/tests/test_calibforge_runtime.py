"""A/B uses existing native jobs; identity and phase boundaries are explicit."""
import copy
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import yaml

from sft import qwen35 as codec
from sft.runtime.config import initialize
from sft.runtime.paths import CALIBFORGE_STAGES,config_path,data_manifest_path
from sft.runtime.calibforge import validate_pair,validate_initialization,validate_predecessor,validate_stage_order,canary_input_contract
from sft.runtime.checkpoint_archive import sha256
from sft.runtime import jobs


class CalibForgeRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.env=patch.dict(os.environ,{'OPENHARNESS_SFT_WORKSPACE':str(self.root)})
        self.env.start();self.addCleanup(self.env.stop)
        initialize(self.root,'/base',self.root/'hot',self.root/'archive',['GPU-'+str(i)for i in range(4)])
        seed=yaml.safe_load(config_path('m2-128k').read_text())
        self.config=seed|dict(runtime_recipe='calibforge_appendix_e',learning_rate=1e-5,
            num_train_epochs=10,gradient_accumulation_steps=32,weight_decay=0.0,warmup_ratio=0.05,
            mask_history=False,save_strategy='epoch',eval_strategy='epoch',save_total_limit=None,
            load_best_model_at_end=False,eval_on_start=True,tokenized_path=str(self.root/'shared-cache'))
        for stage in CALIBFORGE_STAGES:
            cfg=self.config|dict(model_name_or_path=str(self.root/('m2-hf'if stage.startswith('m3')else'm0-hf')),
                                 output_dir=str(self.root/'hot/runs'/stage))
            config_path(stage).write_text(yaml.safe_dump(cfg))
        self.runtime=json.loads((self.root/'configs/runtime.json').read_text())
        self.runtime.update(training_recipe='calibforge_appendix_e',hot_root=str(self.root/'hot'))
        self.save_runtime()

    def save_runtime(self):
        (self.root/'configs/runtime.json').write_text(json.dumps(self.runtime))

    def initialization_fixture(self):
        model=self.root/'m2-hf';model.mkdir()
        weight=model/'model.safetensors';weight.write_bytes(b'UNIT_NOT_REAL_WEIGHTS')
        proof=self.root/'unit-source-proof.json'
        proof.write_text(json.dumps(dict(status='M2_COMPLETED_HF_VERIFIED',
            hf_export=dict(complete_final_hf=True,files=[dict(path=weight.name,sha256=sha256(weight))]),
            hf_load_smoke=dict(model_loaded=True,generated_tokens=1))))
        route=dict(initial_model_path=str(model),initial_optimizer='NEW',initial_scheduler='NEW',
            weight_sha256=sha256(weight),source_verification=str(proof),source_verification_sha256=sha256(proof),
            expected_files=[dict(path=weight.name,bytes=weight.stat().st_size,mtime_ns=weight.stat().st_mtime_ns,sha256=sha256(weight))])
        identity=self.root/'unit-initial-models.json'
        identity.write_text(json.dumps(dict(base_model='Qwen/Qwen3.5-4B',revision=codec.REVISION,routes={'M3-A':route})))
        self.runtime.update(initial_models_manifest=str(identity),initial_models_manifest_sha256=sha256(identity));self.save_runtime()
        return weight,route

    def test_same_native_cache_and_only_initialization_output_can_differ(self):
        configs=validate_pair()
        self.assertEqual(data_manifest_path('m3-a-128k'),data_manifest_path('c1-b-128k'))
        self.assertEqual(len(configs),2)
        path=config_path('c1-b-128k');cfg=yaml.safe_load(path.read_text());cfg['logging_steps']=2;path.write_text(yaml.safe_dump(cfg))
        with self.assertRaisesRegex(ValueError,'A/B data order'):validate_pair()

    def test_output_alias_and_unrelated_old_output_are_rejected(self):
        a=yaml.safe_load(config_path('m3-a-128k').read_text());b=config_path('c1-b-128k')
        cfg=yaml.safe_load(b.read_text());cfg['output_dir']=a['output_dir'];b.write_text(yaml.safe_dump(cfg))
        with self.assertRaisesRegex(ValueError,'distinct'):validate_pair()
        cfg['output_dir']=str(self.root/'old-frozen-experiment');b.write_text(yaml.safe_dump(cfg))
        with self.assertRaisesRegex(ValueError,'own hot storage'):validate_pair()

    def test_initialization_checks_source_proof_and_actual_weights_at_handoff(self):
        weight,route=self.initialization_fixture();cfg=validate_pair()['m3-a-128k']
        validate_initialization('m3-a-128k',cfg,verify_weights=True)
        with self.assertRaisesRegex(ValueError,'wrong model'):
            validate_initialization('m3-a-128k',cfg|dict(model_name_or_path='/original-m0'))
        stat=weight.stat();weight.write_bytes(b'X'*stat.st_size);os.utime(weight,ns=(stat.st_atime_ns,stat.st_mtime_ns))
        # The cheap reused observation is explicitly different from full launch hashing.
        validate_initialization('m3-a-128k',cfg)
        with self.assertRaisesRegex(ValueError,'SHA mismatch'):
            validate_initialization('m3-a-128k',cfg,verify_weights=True)

    def predecessor_fixture(self):
        policy=json.loads((Path(codec.__file__).parent/'policies/evaluation-exclusion.json').read_text())
        tasks=list(policy['instruction_normalized_sha256']);models={}
        for model in ('m0','m1','m2'):
            rows=[dict(task_id=task,trial_id=f'{model}-{index}',trial_name=f'{model}-{index}',
                       result_path=f'/original/{model}/{index}/result.json',result_sha256='a'*64)
                  for index,task in enumerate(tasks)]
            models[model]=dict(primary=True,terminal=89,trials=rows,job_name=f'qwen35-{model}-r1-20261026')
        report=dict(models=models,scope='PREDECLARED_FIRST_89_PER_MODEL',planned_primary_trials=267,
                    completed_primary_trials=267,primary_complete=True)
        path=self.root/'unit-prior-report.json';path.write_text(json.dumps(report))
        self.runtime.update(prior_campaign_report=str(path),prior_campaign_report_sha256=sha256(path));self.save_runtime()
        return path,report

    def save_predecessor(self,path,report):
        path.write_text(json.dumps(report));self.runtime['prior_campaign_report_sha256']=sha256(path);self.save_runtime()

    def test_prior_campaign_requires_267_unique_predeclared_first_round_trials(self):
        path,report=self.predecessor_fixture()
        self.assertEqual(validate_predecessor()['terminal_trials'],267)
        report['models']['m0']['trials'][1]['trial_id']=report['models']['m0']['trials'][0]['trial_id']
        self.save_predecessor(path,report)
        with self.assertRaisesRegex(ValueError,'identity/quota'):validate_predecessor()

    def test_missing_m0_or_unknown_task_cannot_release_new_training(self):
        path,report=self.predecessor_fixture();model=report['models'].pop('m0')
        self.save_predecessor(path,report)
        with self.assertRaisesRegex(ValueError,'not sealed'):validate_predecessor()
        report['models']['m0']=model;model['trials'][0]['task_id']='unit-unknown-task'
        self.save_predecessor(path,report)
        with self.assertRaisesRegex(ValueError,'quota incomplete'):validate_predecessor()

    def test_supplementary_attempts_cannot_replace_a_primary_first_round(self):
        path,report=self.predecessor_fixture()
        report['models']['m0']['job_name']='qwen35-m0-r2-r5-20261026'
        self.save_predecessor(path,report)
        with self.assertRaisesRegex(ValueError,'quota incomplete'):validate_predecessor()

    def test_c1_waits_for_final_epoch_ten_hf_instead_of_an_early_checkpoint(self):
        output=Path(validate_pair()['m3-a-128k']['output_dir']);output.mkdir(parents=True)
        state=output/'trainer_state.json'
        with patch('sft.runtime.hf_export.final_verified',return_value=True):
            for epoch,step,maximum in [(2,2,10),(2,10,10),(10,9,10)]:
                state.write_text(json.dumps(dict(epoch=epoch,global_step=step,max_steps=maximum)))
                with self.assertRaisesRegex(ValueError,'epoch-10'):validate_stage_order('c1-b-128k')
            state.write_text(json.dumps(dict(epoch=10,global_step=10,max_steps=10)))
            validate_stage_order('c1-b-128k')

    def test_existing_remote_job_submission_binds_shared_data_sha_and_rejects_duplicates(self):
        self.runtime.update(formal_training_authorized=True,formal_authorized_stage='m3-a-128k');self.save_runtime()
        manifest=data_manifest_path('m3-a-128k');manifest.write_text('{"UNIT_TEST_ONLY":true}')
        with patch.object(jobs,'require_linger'),patch.object(jobs.subprocess,'run')as run:
            job=jobs.submit('m3-a-128k',['0','1','2','3'],job_id='unit-shared-cache')
            self.assertEqual(job['data_manifest_sha256'],sha256(manifest))
            self.assertIn('--property=Restart=no',run.call_args.args[0])
            with self.assertRaises(FileExistsError):jobs.submit('m3-a-128k',['0','1','2','3'],job_id='unit-shared-cache')
            self.assertEqual(run.call_count,1)

    def test_missing_data_gpu_and_predecessor_are_false_not_ready(self):
        from sft.runtime.readiness import check
        with patch.object(codec,'MODEL',codec.MODEL),\
             patch('sft.qwen35.load_tokenizer',side_effect=ImportError('unit offline')):
            result=check(native=False)
        self.assertEqual(set(result['stages']),set(CALIBFORGE_STAGES))
        self.assertTrue(result['checks']['shared_recipe'])
        for name in ('shared_data','prior_campaign_complete','current_recipe_gpu_update_resume'):
            self.assertFalse(result['checks'][name])
        self.assertTrue(all(not stage['ready_to_train']for stage in result['stages'].values()))

    def corpus_extremes_fixture(self):
        rows=dict(train=[dict(input_sha256='i0',labels_sha256='l0',text_tokens=8,loss_tokens=2),
                         dict(input_sha256='i1',labels_sha256='l1',text_tokens=12,loss_tokens=3)],
                  validation=[dict(input_sha256='i2',labels_sha256='l2',text_tokens=7,loss_tokens=6)])
        indexes={}
        for split,values in rows.items():
            path=self.root/'manifests'/f'unit-{split}-rows.jsonl'
            path.write_text(''.join(json.dumps(row)+'\n'for row in values))
            indexes[split]=dict(path=str(path),sha256=sha256(path))
        manifest=data_manifest_path('m3-a-128k')
        manifest.write_text(json.dumps(dict(formal_training_eligible=True,row_indexes=indexes,
            counts={split:dict(rows=len(values))for split,values in rows.items()})))
        proof=self.root/'unit-canary-inputs.json'
        data=dict(kind='calibforge_frozen_data_gpu_canary',source_dataset_manifest_sha256=sha256(manifest),diagnostic_exposures=384,
            selected_rows=[rows['train'][1]|dict(source_split='train',index_in_split=1),
                           rows['validation'][0]|dict(source_split='validation',index_in_split=0)])
        proof.write_text(json.dumps(data));return proof,data

    def test_gpu_inputs_bind_both_real_corpus_extremes_and_refuse_an_easier_subset(self):
        proof,data=self.corpus_extremes_fixture()
        contract=canary_input_contract(proof)
        self.assertEqual(contract['maximum_real_input_tokens'],12)
        self.assertEqual(contract['maximum_real_supervised_tokens'],6)
        data['selected_rows']=data['selected_rows'][:1];proof.write_text(json.dumps(data))
        with self.assertRaisesRegex(ValueError,'omits real longest-input or largest-supervision'):
            canary_input_contract(proof)

    def test_gpu_input_manifest_cannot_hide_changed_labels_or_a_new_corpus(self):
        proof,data=self.corpus_extremes_fixture();data['selected_rows'][0]['labels_sha256']='changed'
        proof.write_text(json.dumps(data))
        with self.assertRaisesRegex(ValueError,'differs from source index'):canary_input_contract(proof)
        data['selected_rows'][0]['labels_sha256']='l1';proof.write_text(json.dumps(data))
        with data_manifest_path('m3-a-128k').open('a')as stream:stream.write('\n')
        with self.assertRaisesRegex(ValueError,'not bound to the frozen'):canary_input_contract(proof)

    def test_canary_preparation_refuses_missing_formal_data_before_any_gpu_dispatch(self):
        from sft.runtime.canary import prepare_calibforge
        with patch('sft.runtime.canary.subprocess.Popen')as child:
            with self.assertRaises(FileNotFoundError):prepare_calibforge()
            child.assert_not_called()

    @unittest.skipUnless(importlib.util.find_spec('datasets'),'Native Arrow environment required')
    def test_native_arrow_canary_builder_keeps_tokens_and_adds_only_diagnostic_indices(self):
        # Artificial unit rows in TemporaryDirectory only. Provenance gates are
        # explicitly mocked; this is not a successful source or formal corpus.
        from datasets import Dataset,DatasetDict,Features,Sequence,Value,load_from_disk
        from sft.runtime.canary import prepare_calibforge
        features=Features({key:Sequence(Value('int32'))for key in ('input_ids','attention_mask','labels')}|
            {key:Sequence(Value('string'))for key in ('images','videos','audios')})
        a=dict(input_ids=[1,2,3,4],attention_mask=[1,1,1,1],labels=[-100,-100,-100,4],images=[],videos=[],audios=[])
        b=dict(input_ids=[5,6,7],attention_mask=[1,1,1],labels=[5,6,7],images=[],videos=[],audios=[])
        source=DatasetDict(train=Dataset.from_list([a],features=features),validation=Dataset.from_list([b],features=features))
        cache=self.root/'shared-cache';source.save_to_disk(str(cache))
        indexes={}
        for split,row in (('train',a),('validation',b)):
            index=self.root/'manifests'/f'unit-arrow-{split}.jsonl'
            index.write_text(json.dumps(dict(input_sha256=codec.digest(row['input_ids']),labels_sha256=codec.digest(row['labels']),
                text_tokens=len(row['input_ids']),loss_tokens=sum(x!=-100 for x in row['labels'])))+'\n')
            indexes[split]=dict(path=str(index),sha256=sha256(index))
        data_manifest_path('m3-a-128k').write_text(json.dumps(dict(formal_training_eligible=True,path=str(cache),row_indexes=indexes,
            counts={split:dict(rows=1)for split in ('train','validation')})))
        with patch('sft.runtime.launch.validate_data'),patch('sft.runtime.calibforge.validate_dataset'),\
             patch('sft.runtime.canary.subprocess.Popen')as child:
            result=prepare_calibforge('verify-unit-arrow')
            child.assert_not_called()
        cfg=yaml.safe_load(Path(result['config']).read_text());rows=load_from_disk(cfg['tokenized_path'])['train']
        self.assertEqual(len(rows),384)
        self.assertEqual(sorted(rows['_calibforge_sample_index']),list(range(384)))
        self.assertEqual({tuple(row['input_ids'])for row in rows},{tuple(a['input_ids']),tuple(b['input_ids'])})
        self.assertFalse(cfg['remove_unused_columns']);self.assertFalse(result['gpu_started'])
        contract=canary_input_contract(result['inputs'])
        self.assertEqual((contract['maximum_real_input_tokens'],contract['maximum_real_supervised_tokens']),(4,3))


if __name__=='__main__':unittest.main()
