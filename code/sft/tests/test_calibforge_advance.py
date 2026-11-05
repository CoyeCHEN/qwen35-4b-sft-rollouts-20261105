import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import yaml

from sft.runtime.checkpoint_archive import sha256

from sft.runtime.calibforge_advance import next_stage,release_prior_serving,advance


class CalibForgeAdvanceTests(unittest.TestCase):
    def test_fixed_order_and_unknown_job_never_resubmitted(self):
        self.assertEqual(next_stage({}),('m3-a-128k','NOT_SUBMITTED'))
        for status in ('running','submitted','failed','UNKNOWN'):
            self.assertEqual(next_stage({'m3-a-128k':dict(status=status)})[1],
                             'WAIT_OR_INSPECT_ORIGINAL_JOB')
        first=dict(status='completed')
        self.assertEqual(next_stage({'m3-a-128k':first})[1],'VERIFY_FINAL_HF')
        first['hf_verified']=True
        self.assertEqual(next_stage({'m3-a-128k':first}),('c1-b-128k','NOT_SUBMITTED'))
        self.assertEqual(next_stage({s:first for s in ('m3-a-128k','c1-b-128k')})[0],None)

    def runtime(self):
        return dict(prior_campaign_release_receipt='/receipt',prior_campaign_release_receipt_sha256='r',
            prior_campaign_report_sha256='p',prior_serving_unit='project-serving.service',
            prior_serving_process=dict(pid=100,startticks='10',boot_id='unit-only'))

    def receipt(self):
        return dict(primary_report_sha256='p',all_controllers_ended=True,campaign_running_containers=[],
                    source_verification='LIVE_SSH_AFTER_PRIMARY_COMPLETION')

    def test_no_resource_signal_before_actual_predecessor_passes(self):
        with patch('sft.runtime.calibforge.validate_predecessor',side_effect=ValueError('incomplete')),\
             patch('sft.runtime.calibforge_advance.subprocess.run')as run:
            with self.assertRaisesRegex(ValueError,'incomplete'):release_prior_serving(self.runtime())
            run.assert_not_called()

    def test_changed_serving_pid_is_never_stopped(self):
        with patch('sft.runtime.calibforge.validate_predecessor'),\
             patch('sft.runtime.calibforge.checked_json',return_value=self.receipt()),\
             patch('sft.runtime.calibforge_advance.subprocess.check_output',return_value='MainPID=200\nActiveState=active\n'),\
             patch('sft.runtime.calibforge_advance.subprocess.run')as run:
            with self.assertRaisesRegex(ValueError,'changed'):release_prior_serving(self.runtime())
            run.assert_not_called()

    def test_only_recorded_own_unit_stopped_after_drain(self):
        with patch('sft.runtime.calibforge.validate_predecessor'),\
             patch('sft.runtime.calibforge.checked_json',return_value=self.receipt()),\
             patch('sft.runtime.calibforge_advance.jobs.process_matches',return_value=True),\
             patch('sft.runtime.calibforge_advance.subprocess.check_output',return_value='MainPID=100\nActiveState=active\n'),\
             patch('sft.runtime.calibforge_advance.subprocess.run')as run:
            release_prior_serving(self.runtime())
            self.assertEqual(run.call_args.args[0],['systemctl','--user','stop','project-serving.service'])

    def test_failed_or_inactive_empty_unit_needs_no_further_signal(self):
        for state in ('failed','inactive'):
            with self.subTest(state=state),\
                 patch('sft.runtime.calibforge.validate_predecessor'),\
                 patch('sft.runtime.calibforge.checked_json',return_value=self.receipt()),\
                 patch('sft.runtime.calibforge_advance.jobs.process_matches',return_value=False),\
                 patch('sft.runtime.calibforge_advance.subprocess.check_output',
                       return_value=f'MainPID=0\nActiveState={state}\nControlGroup=\nResult=signal\n'),\
                 patch('sft.runtime.calibforge_advance.subprocess.run')as run:
                observed=release_prior_serving(self.runtime())
                self.assertTrue(observed['already_stopped']);self.assertTrue(observed['recorded_process_gone'])
                run.assert_not_called()

    def test_zero_main_pid_with_live_rank_cgroup_is_not_released(self):
        with tempfile.TemporaryDirectory()as folder:
            base=Path(folder);group=base/'unit/rank';group.mkdir(parents=True)
            (group/'cgroup.procs').write_text('123\n')
            with patch('sft.runtime.calibforge.validate_predecessor'),\
                 patch('sft.runtime.calibforge.checked_json',return_value=self.receipt()),\
                 patch('sft.runtime.calibforge_advance.jobs.process_matches',return_value=False),\
                 patch('sft.runtime.calibforge_advance.CGROUP_ROOT',base),\
                 patch('sft.runtime.calibforge_advance.subprocess.check_output',
                       return_value='MainPID=0\nActiveState=failed\nControlGroup=/unit\n'),\
                 patch('sft.runtime.calibforge_advance.subprocess.run')as run:
                with self.assertRaisesRegex(ValueError,'live cgroup'):release_prior_serving(self.runtime())
                run.assert_not_called()

    def test_zero_main_pid_but_original_process_alive_is_rejected(self):
        with patch('sft.runtime.calibforge.validate_predecessor'),\
             patch('sft.runtime.calibforge.checked_json',return_value=self.receipt()),\
             patch('sft.runtime.calibforge_advance.jobs.process_matches',return_value=True),\
             patch('sft.runtime.calibforge_advance.subprocess.check_output',
                   return_value='MainPID=0\nActiveState=failed\nControlGroup=\n'),\
             patch('sft.runtime.calibforge_advance.subprocess.run')as run:
            with self.assertRaisesRegex(ValueError,'still exists'):release_prior_serving(self.runtime())
            run.assert_not_called()

    def test_missing_corpus_does_not_submit_canary_or_formal_job(self):
        with tempfile.TemporaryDirectory()as name:
            root=Path(name)
            for folder in ('checks','locks','logs'):(root/folder).mkdir()
            with patch('sft.runtime.calibforge_advance.workspace',return_value=root),\
                 patch('sft.runtime.calibforge_advance.runtime_config',return_value={}),\
                 patch('sft.runtime.calibforge.validate_predecessor'),\
                 patch('sft.runtime.calibforge_advance.release_prior_serving',return_value={}),\
                 patch('sft.runtime.calibforge_advance.data_manifest_path',return_value=root/'absent'),\
                 patch('sft.runtime.calibforge_advance.jobs.submit')as submit:
                result=advance()
                self.assertEqual(result['status'],'BLOCKED_BY_FROZEN_CORPUS')
                submit.assert_not_called()
                self.assertEqual(json.loads((root/'checks/sequence-observation.json').read_text())['actions'],[])

    def test_final_eval_cleanup_checks_process_identity_and_never_starts_training(self):
        for matches in (False,True):
            with self.subTest(matches=matches),tempfile.TemporaryDirectory()as name:
                root=Path(name)
                for folder in ('checks','locks','logs','configs'):(root/folder).mkdir()
                corpus=root/'corpus.json';corpus.write_text('{}')
                probe=root/'probe';probe.mkdir();(probe/'new-entry-acceptance.json').write_text('{"passed":true}')
                (root/'configs/verify-calibforge-data.yaml').write_text(yaml.safe_dump(dict(output_dir=str(probe))))
                configurations={}
                for stage in ('m3-a-128k','c1-b-128k'):
                    model=root/stage;model.mkdir();(model/'HF_EXPORT_COMPLETE.json').write_text('{}')
                    configurations[stage]=dict(output_dir=str(model))
                    job=root/'jobs'/('calibforge-'+stage+'-20261027');job.mkdir(parents=True)
                    (job/'job.json').write_text('{}')
                    (job/'HF_VERIFIED.json').write_text(json.dumps(dict(model=str(model),export_manifest_sha256=sha256(model/'HF_EXPORT_COMPLETE.json'))))
                (root/'checks/calibforge-evaluation-final.json').write_text(json.dumps(dict(scope='CALIBFORGE_AB_PREDECLARED_FIRST_89',completed_primary_trials=178)))
                unit='project-final-serving.service'
                (root/'checks/evaluation-serving-submitted.json').write_text(json.dumps(dict(unit=unit,status='STARTED',process=dict(pid=100))))
                with patch('sft.runtime.calibforge_advance.workspace',return_value=root),\
                     patch('sft.runtime.calibforge_advance.runtime_config',return_value=dict(evaluation_serving_unit=unit,service_prefix='unit-only')),\
                     patch('sft.runtime.calibforge.validate_predecessor'),\
                     patch('sft.runtime.calibforge_advance.release_prior_serving',return_value={}),\
                     patch('sft.runtime.calibforge_advance.data_manifest_path',return_value=corpus),\
                     patch('sft.runtime.calibforge.validate_pair',return_value=configurations),\
                     patch('sft.runtime.hf_export.final_verified',return_value=True),\
                     patch('sft.runtime.calibforge_advance.jobs.status',return_value=dict(status='completed')),\
                     patch('sft.runtime.calibforge_advance.jobs.process_matches',return_value=matches),\
                     patch('sft.runtime.calibforge_advance.jobs.submit')as submit,\
                     patch('sft.runtime.calibforge_advance.subprocess.check_output',return_value='100'),\
                     patch('sft.runtime.calibforge_advance.subprocess.run')as run:
                    result=advance();submit.assert_not_called()
                    if matches:
                        self.assertEqual(result['status'],'SEQUENCE_COMPLETED_EVIDENCE_READY',result)
                        self.assertEqual(run.call_args.args[0],['systemctl','--user','stop',unit])
                    else:
                        self.assertEqual(result['status'],'BLOCKED_OR_FAILED_EVIDENCE');run.assert_not_called()


if __name__=='__main__':unittest.main()
