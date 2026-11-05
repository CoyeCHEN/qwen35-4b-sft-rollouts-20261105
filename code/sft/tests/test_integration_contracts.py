"""Immutable study identities and file contracts shared by the two implementations."""
import csv
import gzip
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
STUDY=ROOT/'studies/tmax32k'


class IntegrationContracts(unittest.TestCase):
    def test_eight_training_and_thirteen_NLL_identities_are_distinct(self):
        arms=json.loads((STUDY/'historical-arms.json').read_text())
        models=json.loads((STUDY/'historical-model-identities.json').read_text())
        self.assertEqual(len(arms),8);self.assertEqual(len({a['name']for a in arms}),8)
        self.assertEqual(len(models),13);self.assertEqual(len({m['model']for m in models}),13)
        self.assertTrue(all(len(m['weight_sha256'])==64 and len(m['nll_archive_sha256'])==64 for m in models))
        for arm in arms:
            self.assertEqual(arm['config']['max_length'],32768)
            self.assertEqual(arm['config']['gradient_accumulation'],4)
            self.assertEqual(arm['historical_identity']['epochs'],1)
            self.assertEqual(arm['historical_identity']['source_trainer_sha256'],
                             hashlib.sha256((STUDY/'sources/original-train.py').read_bytes()).hexdigest())
        self.assertFalse((ROOT/'train.py').exists())
        self.assertNotIn('llamafactory',(STUDY/'scripts/training_candidate.py').read_text())

    def test_original_training_and_serving_sources_match_recorded_hashes(self):
        for name,item in json.loads((STUDY/'SOURCE_ORIGINS.json').read_text()).items():
            self.assertEqual(hashlib.sha256((STUDY/name).read_bytes()).hexdigest(),item['repository_sha256'],name)
        for name,digest in json.loads((STUDY/'serving/PRODUCTION_SOURCE_SHA256.json').read_text()).items():
            self.assertEqual(hashlib.sha256((STUDY/'serving'/name).read_bytes()).hexdigest(),digest,name)

    def test_scalar_NLL_denominators_use_calls_tokens_and_tasks_separately(self):
        with tempfile.TemporaryDirectory()as directory:
            root=Path(directory);numeric=root/'numerical';numeric.mkdir()
            rows=[]
            for call,task,count,total in [('a1','A',10,10.),('a2','A',1,4.),('b','B',2,4.)]:
                rows.append(dict(call_id=call,task_id=task,model='synthetic-only',split='validation',condition='teacher_full',input_tokens=20,
                    region_nll_sum={'final_text':total},region_counts={'final_text':count},
                    paired_region_nll_sum={'final_text':total},paired_region_counts={'final_text':count}))
            (numeric/'TRAJECTORY_COVERAGE_INDEX.json').write_text(json.dumps({'calls':{r['call_id']:{'quartile':'Q1'}for r in rows}}))
            with gzip.open(numeric/'synthetic-region-nll-v2.jsonl.gz','wt')as stream:
                for row in rows:stream.write(json.dumps(row)+'\n')
            env=os.environ|{'TMAX_ABLATION_ROOT':str(root)}
            subprocess.run([sys.executable,str(STUDY/'scripts/aggregate_nll.py')],env=env,check=True,capture_output=True)
            with(root/'REGION_NLL_RESULTS.csv').open()as stream:
                result=next(r for r in csv.DictReader(stream)if r['input_length_bucket']=='all'and r['trajectory_quartile']=='all'and r['paired_identical_target_suffix']=='False')
            self.assertAlmostEqual(float(result['token_weighted_nll']),18/13)
            self.assertAlmostEqual(float(result['call_macro_nll']),7/3)
            self.assertAlmostEqual(float(result['task_macro_nll']),(14/11+2)/2)
            self.assertEqual(result['independent_tasks'],'2')
            repeated=subprocess.run([sys.executable,str(STUDY/'scripts/aggregate_nll.py')],env=env,capture_output=True)
            self.assertNotEqual(repeated.returncode,0)


if __name__=='__main__':unittest.main()
