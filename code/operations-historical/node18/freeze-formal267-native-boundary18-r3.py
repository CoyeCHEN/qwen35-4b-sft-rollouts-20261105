"""Freeze the unchanged native runtime plus the actual R6 pipeline preparation."""
import importlib,json,hashlib,os,subprocess,sys,time
from pathlib import Path
R=Path('/ssd/chenkeyi/qwen35-sft-772-20261101');E=R/'formal-native-eval-r1';C=Path('/data/chenkeyi/qwen35-sft-772-20261101/control')
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(p):return json.loads(Path(p).read_text())
owner=read(C/'NATIVE_ADVANCE_OWNER.json');assert owner['deployment_revision']=='r38-real89-environment-and-native-execution-binding'
assert(Path('/proc')/str(owner['pid'])/'stat').read_text().rsplit(')',1)[1].split()[19]==owner['start_ticks']
parent=R/'checks/FORMAL267_NATIVE_BOUNDARY_ACCEPTANCE_R1.json';assert sha(parent)=='48971a8a5124a4aa466fe54d912184efea1f1616fc0af3c7931b1c7aa61f7e83'
sys.path[:0]=[str(R),str(E/'scripts')]
assert importlib.import_module('winner267-phase18-r12').native_boundary_runtime_gate()['passed']
proof=read(parent);plan=E/'manifests/SELECTED267_PIPELINE_PUBLIC_CACHE_PLAN_R1.json';assert sha(plan)=='5db5cd8671c59269b703b3f97854704ca1a06054cc766ebc2185cfc669492c70'
assert sha(E/'scripts/run-user-evaluation-native18-r6.py')=='422c7a7e6e71973a004b850b55ca7d68452a14ec07f3f284ebafc17dd21c9d79'
assert sha(R/'run-selected267-pipeline-cache-nop18-r1.py')=='5bf2b79c6abbba3ad7e8b7e7e37d3b5fe4752252cab1d8dfe0c5a6d643cf1e50'
integration=R/'lifecycle-boundary-r1/selected267-pipeline-cache-nop-r1/PIPELINE_CACHE_NATIVE_NOP_ACCEPTANCE_R1.json'
code='import importlib.metadata as m,json;print(json.dumps({d.metadata["Name"].lower().replace("_","-"):d.version for d in m.distributions()}))'
def versions(py):return json.loads(subprocess.check_output([str(py),'-c',code],text=True,timeout=20))
base=versions(R/'env/harbor-native-eval-r1/bin/python');native=versions(R/'env/harbor-native-eval-boundary-r1/bin/python')
assert base['harbor']=='0.23.0+rsi.1'and native['harbor']=='0.23.0+rsi.2'
assert{k:v for k,v in base.items()if k!='harbor'}=={k:v for k,v in native.items()if k!='harbor'}
proof.update(at=time.time(),source_worker_sha256=sha(E/'scripts/run-user-evaluation-native18-r6.py'),parent_native_acceptance_path=str(parent),parent_native_acceptance_sha256=sha(parent),public_pipeline_cache_plan_path=str(plan),public_pipeline_cache_plan_sha256=sha(plan),pipeline_native_nop_path=str(integration),pipeline_native_nop_sha256=sha(integration),unique_controller_owner=owner,freeze_script_sha256=sha(Path(__file__)),dependency_versions_match_base=True)
winner=importlib.import_module('winner267-phase18-r13');winner.pipeline_native_preparation_gate(proof)
out=R/'checks/FORMAL267_NATIVE_BOUNDARY_ACCEPTANCE_R2.json';assert not out.exists();temporary=out.with_name(out.name+'.tmp-native-r2')
with temporary.open('x')as stream:json.dump(proof,stream,indent=2);stream.write('\n');stream.flush();os.fsync(stream.fileno())
os.link(temporary,out);temporary.unlink();gate=winner.native_boundary_runtime_gate();assert gate['passed'];print(json.dumps(gate))
