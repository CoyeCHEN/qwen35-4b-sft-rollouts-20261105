"""Attach only an explicitly owned, stopped native driver; queue a GIL-safe hook."""
import argparse,hashlib,json,os,re,signal,subprocess,time
from pathlib import Path

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main(spec_path):
 spec=json.loads(spec_path.read_text());pid=spec['pid'];proc=Path('/proc')/str(pid)
 assert proc.stat().st_uid==os.getuid()and proc.joinpath('stat').read_text().rsplit(')',1)[1].split()[19]==spec['start_ticks']
 command=proc.joinpath('cmdline').read_bytes().replace(b'\0',b' ').decode();assert spec['required_command_substring']in command and 'sglang'not in command
 assert proc.joinpath('stat').read_text().rsplit(')',1)[1].split()[0]=='T'
 assert sha(Path(spec['hook_source']))==spec['hook_source_sha256']
 base=spec_path.parent;code="exec(open("+repr(spec['hook_source'])+").read(), {'PAUSE_SPEC':"+repr(str(spec_path))+"})\n"
 program=base/('admission-'+str(pid)+'.gdb')
 program.write_text('set pagination off\nset confirm off\nset auto-load off\nset debuginfod enabled off\nset sysroot /proc/'+str(pid)+'/root\nattach '+str(pid)+'\nset $srcbuf=(void*)mmap(0,65536,3,34,-1,0)\nset {char['+str(len(code.encode())+1)+']} $srcbuf = '+json.dumps(code)+'\ncall (int)Py_AddPendingCall((int(*)(void*))PyRun_SimpleString,$srcbuf)\ndetach\nquit\n')
 gdb=Path('/usr/local/cuda/bin/cuda-gdb').resolve().with_name('cuda-gdb-minimal');assert gdb.exists()
 candidates=json.loads(subprocess.check_output(['docker','image','inspect',spec['tool_image']],text=True));image=candidates[0];assert image['Os']=='linux'and image['Architecture']=='amd64'
 name='q35-owned-native-admission-'+str(pid)+'-'+str(int(time.time()))
 args=['docker','run','--rm','--name',name,'--label','io.rsi.project=qwen35-772-admission-hold','--network','none','--pid','host','--read-only','--no-healthcheck','--runtime','runc','--user','0:0','--cap-drop','ALL','--cap-add','SYS_PTRACE','--security-opt','apparmor=unconfined','--security-opt','no-new-privileges','--cpus','.5','--memory','512m','--tmpfs','/tmp:rw,nosuid,nodev,size=64m','--workdir','/tmp']
 for item in image['Config'].get('Env')or[]:
  key=item.split('=',1)[0];assert re.fullmatch('[A-Za-z_][A-Za-z0-9_]*',key);args+=['--env',key+'=']
 args+=['--env','PATH=/nonexistent','--env','HOME=/tmp','--env','TERM=dumb']
 for source,dest in [(gdb,'/owned-tools/gdb'),(Path('/lib/x86_64-linux-gnu'),'/owned-libs'),(Path('/lib64/ld-linux-x86-64.so.2').resolve(),'/owned-tools/ld.so'),(program,'/owned-tools/pause.gdb')]:args+=['--mount','type=bind,src='+str(source)+',dst='+dest+',readonly']
 args+=['--entrypoint','/owned-tools/ld.so',image['Id'],'--library-path','/owned-libs','/owned-tools/gdb','-nx','-nh','--batch','-x','/owned-tools/pause.gdb']
 started=time.time();result=subprocess.run(args,capture_output=True,text=True,timeout=35)
 op=dict(at=time.time(),pid=pid,source_sha256=sha(Path(__file__)),debugger_sha256=sha(gdb),target_command=command,target_start_ticks=spec['start_ticks'],tool_image_id=image['Id'],read_only_cpu_tool_container=True,network_disabled=True,only_capability='SYS_PTRACE',no_gpu_devices=True,driver_quiescence_end_attempt_at=time.time(),debugger_return_code=result.returncode,debugger_stdout=result.stdout[-6000:],debugger_stderr=result.stderr[-3000:],elapsed_seconds=time.time()-started)
 (base/('admission-'+str(pid)+'-attach.json')).write_text(json.dumps(op,indent=2)+'\n')
 assert result.returncode==0,result.stderr[-1500:]+'\n'+result.stdout[-1500:]
 if proc.joinpath('stat').read_text().rsplit(')',1)[1].split()[0]=='T':os.kill(pid,signal.SIGCONT)
 receipt=Path(spec['receipt_path'])
 for _ in range(80):
  if receipt.exists():break
  time.sleep(.1)
 assert receipt.exists(),'No native-hook receipt; inspect exact attach record'
 assert json.loads(receipt.read_text())['passed']
 print(json.dumps(dict(passed=True,pid=pid,start_ticks=spec['start_ticks'],receipt=str(receipt),attach_seconds=op['elapsed_seconds'])))
if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('spec',type=Path);args=parser.parse_args();main(args.spec)
