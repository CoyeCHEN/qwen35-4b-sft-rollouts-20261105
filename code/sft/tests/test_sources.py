import json
from pathlib import Path
import shutil
import tempfile
import unittest

from sft.sources import read_source
from sft.runtime.checkpoint_archive import sha256

ROOT=Path(__file__).parents[1]


class SourceGate(unittest.TestCase):
    def fixture(self,directory,reward=1):
        directory=Path(directory);raw=directory/'rollout';shutil.copytree(ROOT/'fixtures/openharness_v2',raw)
        source=directory/'instruction.md';source.write_text('Synthetic unit fixture only, never approved training data')
        result=directory/'result.json';result.write_text(json.dumps(dict(id='trial',task_name='dev-shell',verifier_result={'rewards':{'reward':reward}})))
        entry=dict(task_id='dev-shell',trial_id='trial',origin={'kind':'integration_fixture','source_files':[dict(path=str(source),sha256=sha256(source))]},
            harbor_result=str(result),harbor_result_sha256=sha256(result),rollout_export_dir=str(raw),recorder_manifest_sha256=sha256(raw/'manifest.json'))
        return entry,raw

    def test_bool_reward_is_not_verified_success(self):
        with tempfile.TemporaryDirectory()as temp:
            entry,_=self.fixture(temp,True)
            with self.assertRaisesRegex(ValueError,'Verified Harbor success'):read_source(entry,allow_fixture=True)

    def test_fixture_cannot_become_formal_data(self):
        with tempfile.TemporaryDirectory()as temp:
            entry,_=self.fixture(temp)
            with self.assertRaisesRegex(ValueError,'Independent non-evaluation'):read_source(entry)

    def test_closed_tool_error_is_observation_not_missing_execution(self):
        with tempfile.TemporaryDirectory()as temp:
            entry,raw=self.fixture(temp)
            path=raw/'events.jsonl';events=[json.loads(line)for line in path.read_text().splitlines()]
            start=next(event for event in events if event['type']=='call_start')
            payload=dict(type='call_payload',timestamp=start['timestamp'],data={
                'call_id':start['data']['call_id'],'run_id':start['data']['run_id'],
                'payload':{'messages':[{'role':'user','content':'Synthetic unit task'}]},'fidelity':'provider_payload'})
            events.insert(events.index(start)+1,payload)
            for index,event in enumerate(events,1):event['seq']=index
            tool=next(event for event in events if event['type']=='tool_start')
            for event in events:
                if event['type']=='tool_end':event['data']['status']='error'
                if event['type']=='call_end':
                    event['data']['status']='toolUse'
                    event['data']['response']=dict(role='assistant',stopReason='toolUse',content=[
                        dict(type='toolCall',id=tool['data']['tool_call_id'],name='bash',arguments={'command':'false'})])
            path.write_text('\n'.join(map(json.dumps,events))+'\n')
            calls,identity=read_source(entry,allow_fixture=True)
            self.assertEqual(len(calls),1)
            self.assertFalse(identity['formal_training_eligible'])

    def test_renamed_evaluation_origin_is_refused(self):
        with tempfile.TemporaryDirectory()as temp:
            entry,_=self.fixture(temp);entry['task_id']='renamed';entry['origin']['upstream_benchmark']='terminal-bench-2.1'
            with self.assertRaisesRegex(ValueError,'Evaluation task forbidden'):read_source(entry,allow_fixture=True)


if __name__=='__main__':unittest.main()
