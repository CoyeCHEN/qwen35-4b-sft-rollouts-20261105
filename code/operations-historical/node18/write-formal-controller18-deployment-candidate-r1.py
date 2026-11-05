"""Explicit deployment identities for the still-unstarted formal801 migration."""
from pathlib import Path
import hashlib,json,time
R=Path('/ssd/chenkeyi/qwen35-sft-772-20261101')
def main():
 folder=R/'configs';folder.mkdir(exist_ok=True)
 physical=R/'formal-native-eval-r1'
 value=dict(kind='FORMAL801_CONTROLLER18_DEPLOYMENT_CANDIDATE_R1',created_at=time.time(),activated=False,
  current_sequence_owner=dict(node='18',unit='qwen35-772-native-advance-node18-20261101-r13.service',pid=840835,start_ticks='92847655',cross_node_lock='/data/chenkeyi/qwen35-sft-772-20261101/control/unique-native-advance.lock'),
  current_dispatch_backend='149, unchanged until controlled handoff',
  controller=dict(node='18',python=str(R/'env/harbor-native-eval-r1/bin/python'),asset_alias='/home/chenkeyi/.local/share/harbor-rsi/qwen35-new772-tb21-20261101',physical_root=str(physical),jobs_dir=str(physical/'jobs'),diagnostics_dir=str(physical/'diagnostics'),temporary_dir=str(R/'tmp'),memory_max_bytes=32*1024**3,all_local_download_targets_must_use_real_paths=True),
  task_engine=dict(node='149',id='c6e16cdf-e878-4cc5-84c8-78a56c54b5c5',socket='/var/run/docker.sock',native_endpoint='ssh://chenkeyi@127.0.0.1:18449',staging_root='/home/chenkeyi/.local/share/harbor-rsi/qwen35-new772-tb21-20261101/staging',original_engine_and_images_unchanged=True),
  transport=dict(ssh_configuration=str(R/'control-ssh/formal-engine149-r1.conf'),private_client_bin=str(R/'formal-controller18-client-bin-r1'),native_transfer_timeout_unchanged=True,original_149_client_bin_v2_rsync_unchanged=True),
  model_metadata_control_urls={'qwen35-new772-'+tag:'http://127.0.0.1:'+str(port)for tag,port in [('m0',18300),('new-m1-e5',18301),('new-m2-e5',18302)]},
  original_container_model_urls={'qwen35-new772-'+tag:'http://172.17.0.1:'+str(port)+'/v1'for tag,port in [('m0',18300),('new-m1-e5',18301),('new-m2-e5',18302)]},
  deployment_overrides=['job_config.jobs_dir','trial.trials_dir','trial.environment.kwargs.endpoint'],
  native_harbor_wheel_sha256='b58365884dafc939428be05abbf4fc4acb90eec0d1b142e595ba823c326f5b17',
  native_remote_docker_wheel_sha256='2e86db1fbf47d2b375e6bb6623e17b68e298a2082956cc3048cb85711d8b9174',
  student_wheel_sha256='1d27eef1ca6696275f306d8c653f7a266a4c7aea7321f0d47fd01b739c27fa18',
  original_research_protocol_unchanged=True,main_training_and_running_e3_unchanged=True,
  cpu_environment_acceptance='FORMAL_CONTROLLER18_CPU_ENV_ACCEPTANCE_R1.json',
  original_task_nop_verifier_acceptance='FORMAL_CONTROLLER18_NATIVE_NOP_ACCEPTANCE_R2.json',
  first_nop_original_failure_preserved='FORMAL_CONTROLLER18_NOP_R1_FAILURE_AND_PATH_CORRECTION.json',
  full_native_model_recorder_joint_acceptance_pending=True,actual801_configs_deployment_delta_acceptance_pending=True,
  closed_e3_evidence_replication_required_for_moved_comparison=True,
  old_149_formal_dispatch_must_be_disabled_at_controlled_handoff=True,
  source_raw_evidence_preserved_on149=True,official_task_verifier_reward_and_resources_modified=False,
  source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
 out=folder/'formal-controller18-deployment-candidate-r1.json';assert not out.exists();out.write_text(json.dumps(value,indent=2)+'\n');print(json.dumps(dict(path=str(out),sha256=hashlib.sha256(out.read_bytes()).hexdigest(),activated=False)))
if __name__=='__main__':main()
