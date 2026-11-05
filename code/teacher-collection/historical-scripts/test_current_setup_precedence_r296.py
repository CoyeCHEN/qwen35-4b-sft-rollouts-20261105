"""Offline metadata fixtures only; never official Task/Result/Reward evidence."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from collection_current_setup_blocks_r293 import current_setup_blocks


class PrecedenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.stream = self.root / 'stream/collection-r4'
        self.stream.mkdir(parents=True)
        self.events = self.stream / 'teacher-lifecycle.jsonl'
        self.events.write_text('')
        self.ready = {}

    def tearDown(self):
        self.tmp.cleanup()

    def result(self, name, hour):
        path = self.root / name / 'result.json'
        path.parent.mkdir()
        path.write_text(json.dumps(dict(finished_at=f'2026-10-31T{hour:02d}:00:00Z', agent_execution=None, exception_info=None, infrastructure_errors=[], verifier=dict(finished_at=f'2026-10-31T{hour:02d}:00:00Z'))))
        return path

    def failed(self, hour=12):
        result = self.result('failed', hour)
        path = self.stream / 'deployment-test/setup-failures/one.json'
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps(dict(task_id='one', model_calls=0, native_result=str(result))))

    def accepted(self, hour):
        proof = {}
        for kind in ['install', 'nop']:
            path = self.result(kind, hour)
            proof['native_' + kind + '_trial'] = str(path.parent)
            proof[kind + '_result_sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
        self.ready['one'] = proof

    def test_later_failure_blocks_old_ready_without_erasing_history(self):
        self.failed(); self.accepted(11)
        before = json.dumps(self.ready, sort_keys=True)
        self.assertEqual(current_setup_blocks(self.root, self.ready)['one']['status'], 'ENV_BLOCKED')
        self.assertEqual(json.dumps(self.ready, sort_keys=True), before)

    def test_new_verified_ready_supersedes_old_failure(self):
        self.failed(); self.accepted(13)
        self.assertEqual(current_setup_blocks(self.root, self.ready), {})

    def test_new_ready_with_bad_hash_is_rejected(self):
        self.failed(); self.accepted(13)
        self.ready['one']['install_result_sha256'] = 'bad'
        with self.assertRaisesRegex(ValueError, 'exact clean'):
            current_setup_blocks(self.root, self.ready)

    def test_later_actual_admission_supersedes_old_setup_failure(self):
        self.failed()
        self.events.write_text(json.dumps(dict(event='TEACHER_ADMITTED', task_id='one', agent_admitted_at='2026-10-31T13:00:00+00:00')) + '\n')
        self.assertEqual(current_setup_blocks(self.root, self.ready), {})

    def test_agent_execution_is_not_reclassified_as_setup_only(self):
        self.failed()
        path = self.root / 'failed/result.json'
        value = json.loads(path.read_text()); value['agent_execution'] = dict(started_at='2026-10-31T11:00:00Z')
        path.write_text(json.dumps(value))
        with self.assertRaisesRegex(ValueError, 'unreviewed Agent'):
            current_setup_blocks(self.root, self.ready)


if __name__ == '__main__':
    unittest.main()
