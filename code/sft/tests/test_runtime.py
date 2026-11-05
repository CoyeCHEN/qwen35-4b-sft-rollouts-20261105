import fcntl
import json
import io
import os
from pathlib import Path
import tempfile
import subprocess
import unittest
from unittest.mock import patch

from sft.runtime.checkpoint_archive import sha256
from sft.runtime.config import initialize,validate_native
from sft.runtime.jobs import process_identity,process_matches,submit
from sft.runtime.launch import gpu_check,validate_data,validate_resume
from sft.prepare import read_approval


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.env=patch.dict(os.environ,{'OPENHARNESS_SFT_WORKSPACE':str(self.root)})
        self.env.start()
        self.linger=patch('sft.runtime.jobs.require_linger');self.linger.start()
        initialize(self.root,'/models/fixed-qwen35',self.root/'hot',self.root/'archive',['GPU-'+str(i)for i in range(4)])

    def tearDown(self):self.linger.stop();self.env.stop();self.temp.cleanup()

    def test_stale_PID_reuse_is_not_live_job(self):
        identity=process_identity();self.assertTrue(process_matches(identity))
        self.assertFalse(process_matches(identity|{'startticks':str(int(identity['startticks'])+1)}))
        self.assertFalse(process_matches(identity|{'boot_id':'different-boot'}))

    def test_real_linger_guard_refuses_missing_persistence(self):
        self.linger.stop()
        from sft.runtime.jobs import require_linger
        with patch('sft.runtime.jobs.subprocess.check_output',return_value='no\n'):
            with self.assertRaisesRegex(ValueError,'linger'):require_linger()
        self.linger.start()

    def test_readiness_with_missing_data_is_false_and_writes_evidence(self):
        from sft.runtime.readiness import check
        from sft import qwen35
        with patch.object(qwen35,'load_tokenizer',side_effect=ImportError('fixture: tokenizer unavailable')),patch.object(qwen35,'MODEL','/unused'):
            result=check(native=False)
        self.assertTrue(result['checks']['m1-64k_config'])
        self.assertFalse(result['checks']['m1-64k_data'])
        self.assertTrue(all(not stage['ready_to_train']for stage in result['stages'].values()))
        self.assertTrue((self.root/'checks/readiness.json').is_file())

    def test_old_lock_file_does_not_block_but_live_lock_does(self):
        path=self.root/'locks/training.lock';path.write_text('stale PID is irrelevant')
        with path.open('a')as first,path.open('a')as second:
            fcntl.flock(first,fcntl.LOCK_EX|fcntl.LOCK_NB)
            with self.assertRaises(BlockingIOError):fcntl.flock(second,fcntl.LOCK_EX|fcntl.LOCK_NB)
        with path.open('a')as third:fcntl.flock(third,fcntl.LOCK_EX|fcntl.LOCK_NB)

    def test_same_stage_resume_requires_original_config_identity(self):
        from tests.test_checkpoint_archive import fixture
        from sft.runtime.checkpoint_archive import durable_completion
        output=self.root/'hot/runs/m1-64k';checkpoint=output/'checkpoint-1';fixture(checkpoint)
        identity=dict(stage='m1-64k',config_sha256='frozen-config-sha',world_size=4)
        durable_completion(checkpoint,identity)
        validate_resume(checkpoint,output,'m1-64k','frozen-config-sha')
        with self.assertRaisesRegex(ValueError,'configuration identity'):
            validate_resume(checkpoint,output,'m1-64k','changed-config-sha')
        with self.assertRaisesRegex(ValueError,'same stage'):
            validate_resume(checkpoint,self.root/'another-stage','m1-64k','frozen-config-sha')

    def test_duplicate_job_id_refused_and_service_has_no_restart(self):
        with patch('sft.runtime.jobs.subprocess.run')as run:
            submit('m1-64k',[],job_id='cpu-probe',probe_seconds=1)
            command=run.call_args.args[0]
            self.assertIn('--property=Restart=no',command);self.assertIn('--property=KillMode=control-group',command)
            self.assertIn('--property=OOMPolicy=stop',command)
            with self.assertRaises(FileExistsError):submit('m1-64k',[],job_id='cpu-probe',probe_seconds=1)
            self.assertEqual(run.call_count,1)

    def test_lost_submission_response_does_not_erase_an_accepted_job(self):
        def lost(*args,**kwargs):
            path=self.root/'jobs/ambiguous/job.json';job=json.loads(path.read_text());job['status']='running';path.write_text(json.dumps(job))
            raise subprocess.TimeoutExpired('systemd-run',30)
        with patch('sft.runtime.jobs.subprocess.run',side_effect=lost):
            with self.assertRaises(subprocess.TimeoutExpired):submit('m1-64k',[],job_id='ambiguous',probe_seconds=1)
        self.assertEqual(json.loads((self.root/'jobs/ambiguous/job.json').read_text())['status'],'running')
        self.assertTrue((self.root/'jobs/ambiguous/submission-error.json').exists())

    def test_noncritical_query_and_sample_write_failures_do_not_stop_child(self):
        from sft.runtime import jobs
        from unittest.mock import MagicMock
        runtime_path=self.root/'configs/runtime.json'
        runtime=json.loads(runtime_path.read_text());runtime.update(formal_training_authorized=True,formal_authorized_stage='m1-64k')
        runtime_path.write_text(json.dumps(runtime))
        (self.root/'manifests/m1-64k.json').write_text('{}')
        with patch.object(jobs.subprocess,'run'):
            jobs.submit('m1-64k',[],job_id='observer-failure')
        child=MagicMock();child.pid=os.getpid();child.wait.return_value=0
        native_open=Path.open
        class BrokenSample(io.StringIO):
            def write(self,value):raise OSError('fixture: sample log unavailable')
        def open_file(path,*args,**kwargs):
            return BrokenSample()if path.name=='gpu-samples.jsonl'else native_open(path,*args,**kwargs)
        native_atomic=jobs.atomic_json
        def atomic(path,value):
            if path.name=='job.json'and value.get('status')=='running'and'launcher_process'in value:
                raise OSError('fixture: live observation unavailable')
            return native_atomic(path,value)
        with patch.object(jobs.subprocess,'Popen',return_value=child),\
             patch.object(jobs.subprocess,'check_output',side_effect=OSError('fixture: nvidia query unavailable')),\
             patch.object(Path,'open',open_file),patch.object(jobs,'atomic_json',atomic):
            self.assertEqual(jobs.work('observer-failure'),0)
        child.terminate.assert_not_called();child.kill.assert_not_called()
        self.assertEqual(json.loads((self.root/'jobs/observer-failure/job.json').read_text())['status'],'completed')

    def test_cache_corruption_and_all_masked_manifest_refused(self):
        directory=self.root/'fake-cache';directory.mkdir();file=directory/'part.arrow';file.write_bytes(b'fixture')
        manifest=dict(no_truncation=True,task_groups_disjoint=True,formal_training_eligible=True,
            artifacts=[dict(path='part.arrow',bytes=7,sha256=sha256(file))],
            counts={s:dict(rows=1,supervised_tokens=1)for s in ('train','validation')})
        validate_data(directory,manifest)
        file.write_bytes(b'corrupt')
        with self.assertRaisesRegex(ValueError,'corruption'):validate_data(directory,manifest)
        file.write_bytes(b'fixture');manifest['counts']['train']['supervised_tokens']=0
        with self.assertRaisesRegex(ValueError,'masked'):validate_data(directory,manifest)

    def test_empty_M2_and_task_group_leakage_refused(self):
        path=self.root/'approval.json';path.write_text(json.dumps(dict(purpose='formal_m2',entries=[])))
        with self.assertRaisesRegex(ValueError,'no approved'):read_approval(path)
        entries=[dict(task_group_id='same',split=s,trial_id=s)for s in ('train','validation')]
        path.write_text(json.dumps(dict(purpose='formal_m2',entries=entries)))
        with self.assertRaisesRegex(ValueError,'leakage'):read_approval(path)

    def test_utilization_zero_does_not_make_an_allocated_GPU_available(self):
        rows='\n'.join(f'{i}, GPU-{i}, 71000, 81920'for i in range(4))
        config=dict(host='authorized',authorized_gpu_uuids=['GPU-'+str(i)for i in range(4)])
        with patch('sft.runtime.launch.socket.gethostname',return_value='authorized'),\
             patch('sft.runtime.launch.subprocess.check_output',side_effect=[rows,'GPU-0, 123']):
            with self.assertRaisesRegex(ValueError,'Existing allocation'):gpu_check(['0','1','2','3'],config)


if __name__=='__main__':unittest.main()
