"""Freeze formal native boundary identity only after the two real fixture Results pass."""
import hashlib,json,subprocess,time
from pathlib import Path
R=Path('/ssd/chenkeyi/qwen35-sft-772-20261101');B=R/'lifecycle-boundary-r1'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_text())
p=B/'INSTALLED_NATIVE_PACKAGE_SOURCE_ACCEPTANCE_R3.json';assert sha(p)=='2f858716cd45d9512aa7741c84d985299dd98e777764ec9d8cb42061bfe75978'
installed=read(p);assert installed['installed_source_acceptance_passed'] and installed['dependency_versions_match_base']
fixture=B/'remote-docker-fixtures-r2/FIXTURE_ACCEPTANCE_R2.json';result=read(fixture)
assert result['passed'] and result['completed_fixture_cases']==2 and result['model_generation_calls']==0
assert result['harbor_wheel_sha256']==installed['harbor_wheel_sha256']=='6c0baaf5d19eead3b599d15894766f4e399ba3c24f2f5463615581a3a4cab0ca'
assert result['harness_wheel_sha256']=='1d27eef1ca6696275f306d8c653f7a266a4c7aea7321f0d47fd01b739c27fa18'
assert {x['case']for x in result['cases']}=={'finish-bg','interrupted'}
for row in result['cases']:
 assert row['passed'] and sha(Path(row['result_path']))==row['result_sha256']
 assert row['actual_resource_cleanup']=={'containers':[],'networks':[],'volumes':[]}
 assert row['native_cleanup_ack']['action']=='cleaned'
for row in installed['installed_source_files']:assert sha(Path(row['path']))==row['sha256']
assert sha(Path(installed['harbor_wheel_path']))==installed['harbor_wheel_sha256']
code='import importlib.metadata as m,json;print(json.dumps({d.metadata["Name"].lower().replace("_","-"):d.version for d in m.distributions()}))'
def versions(py):return json.loads(subprocess.check_output([str(py),'-c',code],text=True,timeout=20))
base=versions(R/'env/harbor-native-eval-r1/bin/python');current=versions(R/'env/harbor-native-eval-boundary-r1/bin/python')
assert current['harbor']=='0.23.0+rsi.2' and base['harbor']=='0.23.0+rsi.1'
assert {k:v for k,v in base.items()if k!='harbor'}=={k:v for k,v in current.items()if k!='harbor'}
owner=read(Path('/data/chenkeyi/qwen35-sft-772-20261101/control/NATIVE_ADVANCE_OWNER.json'))
assert owner['deployment_revision']=='r37-independent-env59-recheck-and-native-fixture-r2'
prior=B/'remote-docker-fixtures-r1/FIXTURE_ACCEPTANCE_R1.json';assert not read(prior)['passed'] and read(prior)['completed_fixture_cases']==2
proof={**installed,'previous_failed_fixture_preserved_sha256':sha(prior),'passed':True,'at':time.time(),'actual_runtime_fixture_passed':True,'dependency_versions_match_base':True,'fixture_result_path':str(fixture),'fixture_result_sha256':sha(fixture),'harness_wheel_sha256':result['harness_wheel_sha256'],'source_worker_sha256':sha(R/'formal-native-eval-r1/scripts/run-user-evaluation-native18-r5.py'),'installed_source_receipt_sha256':sha(p),'unique_controller_owner':owner,'freeze_script_sha256':sha(Path(__file__))}
out=R/'checks/FORMAL267_NATIVE_BOUNDARY_ACCEPTANCE_R1.json';assert not out.exists()
with out.open('x')as f:json.dump(proof,f,indent=2);f.write('\n')
print(json.dumps({'passed':True,'path':str(out),'sha256':sha(out),'actual_runtime_fixture_passed':True}))
