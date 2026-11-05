"""Optional real upstream exporter test; entirely synthetic, never approved SFT data."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from adapters.openharness_v2 import _raw_rows,_closure_issues
from sft.sources import verify_recorders
from sft.runtime.checkpoint_archive import sha256


class UpstreamContract(unittest.TestCase):
    @unittest.skipUnless(os.environ.get('OPENHARNESS_SOURCE'),'Set pinned OPENHARNESS_SOURCE for real exporter contract')
    def test_native_recorder_export_preserves_actual_compacted_request(self):
        source=Path(os.environ['OPENHARNESS_SOURCE']).resolve()
        commit=subprocess.check_output(['git','-C',str(source),'rev-parse','HEAD'],text=True).strip()
        self.assertEqual(commit,'4b136692905ba5818620f99d55a7d9d77f2c0b9a')
        sys.path.insert(0,str(source))
        from foundation.rollouts.store import Recorder
        from foundation.rollouts.export import exportDirectories
        with tempfile.TemporaryDirectory(prefix='synthetic-recorder-contract-')as temp:
            raw=Path(temp)/'raw';export=Path(temp)/'export'
            recorder=Recorder('synthetic-session',raw)
            recorder.append('run_start',run_id='r',operation='prompt',task_input={'text':'synthetic unit fixture'})
            payload=dict(model='synthetic-teacher',messages=[dict(role='user',content='ACTUAL_COMPACTED_CONTEXT')])
            recorder.append('call_start',run_id='r',call_id='c',source='agent',input={'messages':[dict(role='user',content='OLDER_UNCOMPACTED_CONTEXT')]})
            recorder.append('call_payload',run_id='r',call_id='c',payload=payload,fidelity='provider_payload')
            response=dict(role='assistant',content=[dict(type='thinking',thinking='synthetic reasoning'),dict(type='text',text='synthetic answer')],stopReason='stop')
            recorder.append('call_end',run_id='r',call_id='c',response=response,status='stop')
            recorder.append('run_end',run_id='r',status='completed');recorder.close()
            exportDirectories([raw],export)
            manifest,calls,tools,runs,integrity=_raw_rows(export)
            self.assertTrue(manifest['integrity']['complete']);self.assertFalse(integrity['issues'])
            self.assertFalse(_closure_issues(runs,calls,tools))
            self.assertEqual(calls[0]['payload'],payload)
            self.assertNotEqual(calls[0]['input'],payload)
            self.assertEqual(calls[0]['response']['content'][0]['thinking'],'synthetic reasoning')
            def identity():return dict(raw_recorders=[dict(path=str(raw),manifest_sha256=sha256(raw/'manifest.json'),events_sha256=sha256(raw/'events.jsonl'))])
            self.assertEqual(verify_recorders(identity(),manifest,calls,tools),['synthetic-session'])
            # A valid but older export of the SAME session must not be joined
            # to a newer, separately complete Recorder just by session_id.
            reopened=Recorder('synthetic-session',raw)
            reopened.append('run_start',run_id='r2',operation='prompt',task_input={'text':'another synthetic call'})
            reopened.append('call_start',run_id='r2',call_id='c2',source='agent',input={'messages':[]})
            reopened.append('call_payload',run_id='r2',call_id='c2',payload=payload,fidelity='provider_payload')
            reopened.append('call_end',run_id='r2',call_id='c2',response=response,status='stop')
            reopened.append('run_end',run_id='r2',status='completed');reopened.close()
            with self.assertRaisesRegex(ValueError,'differs from original Recorder'):
                verify_recorders(identity(),manifest,calls,tools)


if __name__=='__main__':unittest.main()
