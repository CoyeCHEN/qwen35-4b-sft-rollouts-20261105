"""Offline admission checks using real native NOP evidence and isolated fixtures."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import collection_readiness_r4 as readiness
import collection_selection_r4 as selection
from harbor.models.trial.result import TrialResult
from run_collection_stream_r3 import attempt_counts
from collections import Counter
import run_collection_stream_r4 as controller

R=readiness.R

class AdmissionTests(unittest.TestCase):
    def test_ready_and_fresh_work_share_the_same_manifest_order(self):
        rows=[dict(task_id='cf-ready',pool='calibforge'),dict(task_id='tf-fresh',pool='tmax'),dict(task_id='cf-fresh',pool='calibforge')]
        with patch.object(controller,'basic_receipt',return_value=('fixture',{})):
            items=controller.admission_candidates(rows,{'cf-ready':{'status':'ENV_READY'}},{},Counter(),set())
            self.assertEqual([(x['task_id'],kind) for x,kind in items['calibforge']],[('cf-ready','teacher'),('cf-fresh','prepare')])
            self.assertEqual([(x['task_id'],kind) for x,kind in items['tmax']],[('tf-fresh','prepare')])

    def test_second_attempt_waits_for_audited_failure_and_stops_at_two(self):
        rows=[dict(task_id='a',pool='calibforge'),dict(task_id='b',pool='calibforge'),dict(task_id='c',pool='calibforge')]
        outcomes={x['task_id']:{'status':'ENV_READY'} for x in rows}
        items=controller.admission_candidates(rows,outcomes,{},Counter(a=1,b=1,c=2),{'b','c'})
        self.assertEqual([(x['task_id'],kind) for x,kind in items['calibforge']],[('b','teacher')])
    def test_frozen_scope_and_caps(self):
        rows=selection.active_rows(attempt_counts())
        self.assertEqual(len(rows),1000)
        self.assertEqual(len({x['task_id'] for x in rows}),1000)
        self.assertEqual(sum(x['pool']=='calibforge' for x in rows),500)
        self.assertTrue(all(x['split'] in ['train','validation'] for x in rows))
        self.assertLessEqual(max(attempt_counts().values(),default=0),2)

    def test_real_reserves_nop_and_materialized_identity(self):
        paths=list((R/'checks/native-reserve-acceptance-r4').glob('*.json'))
        self.assertGreaterEqual(len(paths),4)
        for file in paths:
            proof=readiness.read(file)
            with self.subTest(task=proof['task_id']):
                self.assertEqual(proof['status'],'ENV_READY')
                self.assertEqual(readiness.sha(Path(proof['raw_outcome'])),proof['raw_outcome_sha256'])
                # Retain the actual immutable proof versions; their raw
                # outcomes and native Result hashes are verified below.
                trial_key=('nop_trial' if proof.get('kind') in {
                    'REGISTERED_SOURCE_RESERVE_NATIVE_ACCEPTANCE',
                    'ORIGINAL_SELECTED_TASK_NETWORK_RECOVERY_NATIVE_ACCEPTANCE',
                    'ORIGINAL_SELECTED_TASK_INFRASTRUCTURE_RECOVERY_NATIVE_ACCEPTANCE',
                } else 'native_nop_trial')
                trial=Path(proof[trial_key])
                result=TrialResult.model_validate(readiness.read(trial/'result.json'))
                self.assertEqual(readiness.verify_nop(result,trial,proof['admitted_task']),proof['nop_reward'])
                row=proof['admitted_task']
                materialized=readiness.prepared(row,readiness.basic_receipt(row))
                self.assertEqual(materialized['prepared_task_toml_sha256'],row['prepared_task_toml_sha256'])

    def test_import_origin_gate(self):
        with tempfile.TemporaryDirectory(prefix='rsi-admission-test-') as directory:
            p=Path(directory);(p/'verifier').mkdir();(p/'instruction.md').write_text('Create /app/product_db.py.')
            (p/'result.json').write_text(json.dumps(dict(verifier=dict(finished_at='done'),verifier_result=dict(rewards=dict(reward=0)))))
            row=dict(task_id='fixture-output-module-only',prepared_task_path=str(p))
            native=SimpleNamespace(exception_info=None,infrastructure_errors=[])
            (p/'verifier/test-stdout.txt').write_text("ModuleNotFoundError: No module named 'product_db'")
            self.assertEqual(readiness.verify_nop(native,p,row),0)
            (p/'verifier/test-stdout.txt').write_text("ModuleNotFoundError: No module named 'numpy'")
            with self.assertRaisesRegex(ValueError,'dependency/import origin'):
                readiness.verify_nop(native,p,row)
            (p/'verifier/test-stdout.txt').write_text('ERROR collecting: invalid official test')
            with self.assertRaisesRegex(ValueError,'collection failed'):
                readiness.verify_nop(native,p,row)
            native.infrastructure_errors=['fixture native failure']
            with self.assertRaisesRegex(ValueError,'infrastructure'):
                readiness.verify_nop(native,p,row)

    def test_binding_guards(self):
        with tempfile.TemporaryDirectory(prefix='rsi-selection-test-') as directory:
            root=Path(directory); manifests=root/'manifests';bindings=manifests/'runtime-bindings-r4';bindings.mkdir(parents=True)
            originals=selection.original_rows()
            for name in selection.MANIFESTS:
                (manifests/name).write_bytes((R/'manifests'/name).read_bytes())
            old=originals[0]
            candidate=copy.deepcopy(old);candidate['task_id']='fixture-untried-reserve';candidate['family_id']='fixture-reserve-family'
            reserve=manifests/(candidate['pool'].upper()+'_RESERVES.jsonl');reserve.write_text(json.dumps(candidate)+'\n')
            proof=root/'native-proof.json';proof.write_text(json.dumps(dict(task_id=candidate['task_id'],status='ENV_READY',model_calls=0)))
            failure=root/'source-failure.json';failure.write_text('fixture original setup failure')
            binding=dict(kind='REGISTERED_SOURCE_ENVIRONMENT_REPLACEMENT',replaced_task_id=old['task_id'],candidate_row=copy.deepcopy(candidate),
             teacher_attempts_before_replacement=0,native_environment_proof=str(proof),native_environment_proof_sha256=selection.sha(proof),
             source_environment_failure=str(failure),source_environment_failure_sha256=selection.sha(failure),
             preregistered_reserves_sha256=selection.sha(reserve))
            file=bindings/'fixture.json';file.write_text(json.dumps(binding))
            with patch.object(selection,'R',root):
                self.assertEqual(len(selection.active_rows({})),1000)
                with self.assertRaisesRegex(ValueError,'Attempted original'):
                    selection.active_rows({old['task_id']:1})
                binding['candidate_row']['split']='validation' if old['split']=='train' else 'train';file.write_text(json.dumps(binding))
                with self.assertRaisesRegex(ValueError,'stratum differs'):
                    selection.active_rows({})
                binding['candidate_row']=candidate;file.write_text(json.dumps(binding))
                proof.write_text(json.dumps(dict(task_id=candidate['task_id'],status='ENV_READY',model_calls=1)))
                binding['native_environment_proof_sha256']=selection.sha(proof);file.write_text(json.dumps(binding))
                with self.assertRaisesRegex(ValueError,'Unaccepted reserve'):
                    selection.active_rows({})

if __name__=='__main__':
    unittest.main(verbosity=2)

