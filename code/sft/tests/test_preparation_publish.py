"""Real Arrow publication, failure preservation and safe retry; tiny test-only rows."""
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from sft.prepare import publish,record_row


@unittest.skipUnless(importlib.util.find_spec('datasets'),'Requires the existing native Arrow environment')
class PreparationPublishTests(unittest.TestCase):
    def setUp(self):
        temporary=tempfile.TemporaryDirectory();self.addCleanup(temporary.cleanup)
        self.root=Path(temporary.name)
        for folder in ('data','manifests','checks'):(self.root/folder).mkdir()
        env=patch.dict(os.environ,{'OPENHARNESS_SFT_WORKSPACE':str(self.root)})
        env.start();self.addCleanup(env.stop)

    def generator(self,split,*,fail=False):
        def rows():
            record_row('unit-corpus',split,dict(task_id='unit-'+split),dict(text_tokens=2,loss_tokens=1))
            yield dict(input_ids=[1,2],attention_mask=[1,1],labels=[-100,2],images=[],videos=[],audios=[])
            if fail:raise ValueError('unit injected source conversion failure')
        return rows

    def prepare(self,*,fail=False):
        return publish('unit-corpus',{s:self.generator(s,fail=fail and s=='validation')for s in ('train','validation')},
            dict(kind='UNIT_FIXTURE_NOT_FORMAL_DATA'),lambda:None)

    def test_failed_conversion_preserves_evidence_and_allows_corrected_retry(self):
        with self.assertRaises(Exception):self.prepare(fail=True)
        self.assertFalse((self.root/'data/unit-corpus').exists())
        self.assertFalse((self.root/'manifests/unit-corpus.json').exists())
        result=self.prepare()
        self.assertEqual(result['kind'],'UNIT_FIXTURE_NOT_FORMAL_DATA')
        from datasets import load_from_disk
        data=load_from_disk(result['path'])
        self.assertEqual({k:len(v)for k,v in data.items()},{'train':1,'validation':1})
        failures=list((self.root/'checks/preparation-failures').glob('*/failure.json'))
        self.assertEqual(len(failures),1)
        evidence=json.loads(failures[0].read_text())
        self.assertEqual(evidence['dataset'],'unit-corpus')
        self.assertEqual(len(evidence['preserved_row_indexes']),2)
        for index in evidence['preserved_row_indexes']:
            self.assertTrue((failures[0].parent/index).is_file())

    def test_published_data_is_never_overwritten(self):
        result=self.prepare();manifest=self.root/'manifests/unit-corpus.json'
        before=manifest.read_bytes()
        with self.assertRaises(FileExistsError):self.prepare()
        self.assertEqual(manifest.read_bytes(),before)
        self.assertTrue(Path(result['path']).is_dir())

    def test_unattributed_preexisting_indexes_are_preserved(self):
        target=self.root/'manifests/unit-corpus-train-rows.jsonl';target.write_text('frozen prior evidence\n')
        with self.assertRaises(FileExistsError):self.prepare()
        self.assertEqual(target.read_text(),'frozen prior evidence\n')
        self.assertFalse((self.root/'data/unit-corpus').exists())


if __name__=='__main__':unittest.main()
