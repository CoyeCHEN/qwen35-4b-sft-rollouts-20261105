"""Finite admitted CPU integration, executed with the separately installed native wheel."""
import hashlib,json,os,sys,time
from pathlib import Path
R=Path('/ssd/chenkeyi/qwen35-sft-772-20261101');C=Path('/data/chenkeyi/qwen35-sft-772-20261101/control');B=R/'lifecycle-boundary-r1';S=B/'remote-docker-fixtures-source-r2'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
owner=json.loads((C/'NATIVE_ADVANCE_OWNER.json').read_text())
assert owner['deployment_revision']=='r36-campaign-scoped-cli-leases-and-env89-gates'
assert (Path('/proc')/str(owner['pid'])/'stat').read_text().rsplit(')',1)[1].split()[19]==owner['start_ticks']
assert sha(R/'run-native772-advance-r36-env-repair.py')=='b42c82e6f7a57f3ec939045c39603c348a7d37368c31bdf4ae809db7f9d8e2bd'
manifest=S/'SOURCE_MANIFEST_R2.json';assert sha(manifest)=='72e85fe69b43155843b6fea7b55ec7e3d014728d30f2d9bce9a7fbd1f4471c48'
for row in json.loads(manifest.read_text())['files']:assert sha(S/row['path'])==row['sha256']
wheel=B/'wheels/harbor-0.23.0+rsi.2-py3-none-any.whl';assert sha(wheel)=='6c0baaf5d19eead3b599d15894766f4e399ba3c24f2f5463615581a3a4cab0ca'
receipt=B/'INSTALLED_NATIVE_PACKAGE_SOURCE_ACCEPTANCE_R3.json';assert sha(receipt)=='2f858716cd45d9512aa7741c84d985299dd98e777764ec9d8cb42061bfe75978'
assert not(B/'remote-docker-fixtures-r2').exists()
previous=B/'remote-docker-fixtures-r1/FIXTURE_ACCEPTANCE_R1.json';old=json.loads(previous.read_text());assert old['completed_fixture_cases']==2 and not old['passed']
import importlib.util
prior=B/'remote-docker-fixtures-source-r1/run_remote_docker_fixtures_r1.py'
spec=importlib.util.spec_from_file_location('prior_fixture_evidence',prior);prior_module=importlib.util.module_from_spec(spec);spec.loader.exec_module(prior_module)
os.environ['RSI_NATIVE_ACK_FIXTURE_POLICY']=str(B/'remote-docker-fixtures-r1/FIXTURE_DOCKER_POLICY_R1.json')
os.environ['PATH']=str(B/'remote-docker-fixtures-r1/native-client-bin')+':'+os.environ['PATH']
cleanup={}
for row in old['cases']:
 handle=row['actual_environment'];identity=handle['identity'];directory=Path(row['trial_directory']);events=list(directory.glob('remote-docker-*.jsonl'));assert len(events)==1
 assert json.loads(events[0].read_text().splitlines()[-1])['action']=='cleaned'
 cleanup[identity]={}
 for kind,args in [('containers',['ps','-aq']),('networks',['network','ls','-q']),('volumes',['volume','ls','-q'])]:
  resources=prior_module.docker(args+['--filter','label=io.harbor.remote-docker.identity='+identity]).split();assert not resources,(identity,kind,resources);cleanup[identity][kind]=resources
proof=B/'REMOTE_DOCKER_FIXTURE_EXECUTION_HANDOFF_R2.json';assert not proof.exists()
proof.write_text(json.dumps(dict(at=time.time(),unique_controller_owner=owner,source_manifest_sha256=sha(manifest),harbor_wheel_sha256=sha(wheel),installed_source_receipt_sha256=sha(receipt),native_python=str(R/'env/harbor-native-eval-boundary-r1/bin/python'),finite_cpu_fixture_only=True,real_model_generation_calls=0,previous_failed_fixture_sha256=sha(previous),previous_identities_actual_cleanup=cleanup,source_sha256=sha(Path(__file__))),indent=2)+'\n')
py=str(R/'env/harbor-native-eval-boundary-r1/bin/python');entry=str(S/'run_remote_docker_fixtures_r2.py')
os.execv(py,[py,entry,'--harbor-wheel',str(wheel)])
