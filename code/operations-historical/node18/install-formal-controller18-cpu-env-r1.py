"""Install an isolated replica of the existing Harbor CPU runtime on18 SSD."""
from pathlib import Path
import hashlib,json,os,subprocess,time,zipfile
R=Path('/ssd/chenkeyi/qwen35-sft-772-20261101');SOURCE=R/'formal-controller18-source-r1';ENV=R/'env/harbor-native-eval-r1'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 manifest=json.loads((SOURCE/'STAGING_MANIFEST.json').read_text())
 assert sha(SOURCE/'STAGING_MANIFEST.json')=='fb4a7f2af992e92540af62bf03b8e3eb1aee382c8049d444bd50398a626e943e'
 assert not ENV.exists(),'Inspect an existing installation before repeating'
 base=R/'python-formal-eval-r1/cpython-3.12.3-linux-x86_64-gnu/bin/python3.12'
 subprocess.run([str(base),'-m','venv',str(ENV)],check=True)
 uv=SOURCE/'replica/home/chenkeyi/.local/share/harbor-rsi/pr-delivery-20261021/uv'
 wheels=[str(SOURCE/x['file'])for x in manifest['packages']]
 child=os.environ|dict(UV_CACHE_DIR=str(R/'cache/uv-native-eval-r1'),PIP_CACHE_DIR=str(R/'cache/pip-native-eval-r1'),TMPDIR=str(R/'tmp'),PYTHONNOUSERSITE='1')
 subprocess.run([str(uv),'pip','install','--python',str(ENV/'bin/python'),'--constraint',str(R/'formal-controller18-resolved-constraints-r1.txt'),'--only-binary',':all:',*wheels],check=True,env=child)
 subprocess.run([str(ENV/'bin/python'),'-m','pip','check'],check=True,env=child)
 program=r'''
import hashlib,importlib.metadata as m,json,sys,zipfile
from pathlib import Path
import harbor,harbor_remote_docker
from harbor.job import Job
from harbor.models.job.config import JobConfig
from harbor.verifier.factory import VerifierFactory
from foundation.rollouts.export import RolloutView
source=Path(sys.argv[1]);manifest=json.loads((source/'STAGING_MANIFEST.json').read_text());rows=[]
for package in manifest['packages']:
 d=m.distribution(package['name']);root=Path(d.locate_file(''));diff=[];count=0
 with zipfile.ZipFile(source/package['file'])as z:
  for n in z.namelist():
   if n.endswith('.py')and '.dist-info/'not in n:
    count+=1;p=root/n
    if not p.exists()or hashlib.sha256(p.read_bytes()).hexdigest()!=hashlib.sha256(z.read(n)).hexdigest():diff.append(n)
 assert d.version==package['version']and not diff,(package['name'],diff)
 rows.append(dict(name=package['name'],version=d.version,python_files=count,installed_differences=diff,wheel_sha256=package['sha256']))
print(json.dumps(dict(python=sys.version,environment=sys.prefix,packages=rows,imports_passed=True,installed_versions={d.metadata['Name']:d.version for d in m.distributions()if d.metadata.get('Name')})))
'''
 x=subprocess.run([str(ENV/'bin/python'),'-c',program,str(SOURCE)],capture_output=True,text=True,check=True,env=child)
 value=json.loads(x.stdout);value.update(passed=True,at=time.time(),kind='ISOLATED_FORMAL_CONTROLLER18_CPU_RUNTIME',joint_task_or_model_acceptance=False,actual_trials_started=0,source_manifest_sha256=sha(SOURCE/'STAGING_MANIFEST.json'),resolved_constraints_sha256=sha(R/'formal-controller18-resolved-constraints-r1.txt'),source_sha256=sha(Path(__file__)),training_serving_harness_environments_unchanged=True)
 p=R/'checks/FORMAL_CONTROLLER18_CPU_ENV_ACCEPTANCE_R1.json';assert not p.exists();p.write_text(json.dumps(value,indent=2)+'\n');print(json.dumps({k:v for k,v in value.items()if k!='installed_versions'}))
if __name__=='__main__':main()
