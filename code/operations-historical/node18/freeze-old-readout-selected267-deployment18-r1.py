from pathlib import Path
import argparse,hashlib,json,re,shlex,subprocess,time
R=Path('/ssd/chenkeyi/qwen35-sft-772-20261101');C=Path('/data/chenkeyi/qwen35-sft-772-20261101/control')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def freeze(owner,check_only=False):
 assert json.loads((C/'NATIVE_ADVANCE_OWNER.json').read_text())==owner
 assert(Path('/proc')/str(owner['pid'])/'stat').read_text().rsplit(')',1)[1].split()[19]==owner['start_ticks']
 expected=json.loads((R/'checks/OLD_READOUT_SELECTED267_EXPECTED_REMOTE_FILES_R1.json').read_text())['files']
 code="""from pathlib import Path
import hashlib,json,re,sys
expected=json.loads(sys.argv[1]);found={}
for path,digest in expected.items():
 p=Path(path);actual=hashlib.sha256(p.read_bytes()).hexdigest();assert actual==digest,path;found[path]=actual
p=Path.home()/'.ssh/authorized_keys';tag='qwen35-772-single-advance18-to-native-harbor149';lines=p.read_text().splitlines(keepends=True);selected=[s for s in lines if s.rstrip().rsplit(' ',1)[-1]==tag];assert len(selected)==1;others=''.join(s for s in lines if s not in selected).encode();others_sha=hashlib.sha256(others).hexdigest();assert others_sha=='4345ea16eaa019689642cd301b007cd21bdae307ab8c5e5de1b5833418c5847b'
m=re.search(r'command="([^\"]+)"',selected[0]);assert m and m.group(1)=='/home/chenkeyi/.local/share/harbor-rsi/qwen35-m1-m2-tb21-20261026/venv/bin/python /home/chenkeyi/.local/share/harbor-rsi/qwen35-new772-tb21-20261101/scripts/native-handoff149-r12.py'
print(json.dumps(dict(passed=True,actual_files=found,project_key_comment=tag,project_forced_command=m.group(1),other_keys_sha256=others_sha,other_keys_unchanged=True,model_generation_calls=0)))
"""
 command=['/usr/bin/ssh','-F',str(R/'control-ssh/formal-engine149-r1.conf'),'127.0.0.1',shlex.join(['python3','-c',code,json.dumps(expected)])]
 result=subprocess.run(command,capture_output=True,text=True,timeout=30);assert result.returncode==0,result.stderr[-3000:];proof=json.loads(result.stdout);assert proof['passed']and proof['other_keys_unchanged']
 old='/home/chenkeyi/.local/share/harbor-rsi/qwen35-old-m2-four-arm-20261101';target=R/'checks/OLD_READOUT_SELECTED267_RELEASE_R1.json'
 receipt=dict(at=time.time(),unique_controller_owner=owner,formal801_required=False,forced_command_is_project_key_only=True,actual_remote_deployment_proof=proof,old112_plan_sha256=expected[old+'/manifests/OLD112_NATIVE_DEPLOYMENT_PLAN_R1.json'],native_runner_sha256=expected[old+'/scripts/run-old112-native149-r2.py'],environment_nop_runner_sha256=expected[old+'/scripts/old112-env-preflight149-r1.py'],runtime_profiles_sha256=expected[old+'/configs/old112-runtime-profiles-r2.json'],runtime_binding_sha256=expected[old+'/configs/old112-runtime-binding-r2.json'],explicit_ipam_manifest_sha256=expected[old+'/manifests/OLD112_EXPLICIT_IPAM_R2.json'],actual_model_or_trial_or_gpu_operations=0)
 if check_only:return receipt
 if target.exists():
  old_receipt=json.loads(target.read_text());assert old_receipt['actual_remote_deployment_proof']==proof;return old_receipt
 tmp=target.with_name(target.name+'.tmp');tmp.write_text(json.dumps(receipt,indent=2)+'\n');tmp.replace(target);return receipt
if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('--check-only',action='store_true');args=parser.parse_args();print(json.dumps(freeze(json.loads((C/'NATIVE_ADVANCE_OWNER.json').read_text()),args.check_only)))
