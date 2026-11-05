"""Briefly quiesce only owned native drivers to install an admission hold safely."""
from pathlib import Path
import json,os,signal,subprocess,time
R=Path('/ssd/chenkeyi/qwen35-sft-772-20261101');C=Path('/data/chenkeyi/qwen35-sft-772-20261101/control')
assert(C/'USER_ENV_PREFLIGHT30_PAUSE_R1.json').exists()
units=['qwen35-new772-diag30-native-new-m1-e5-diag-20261102-r2.service','qwen35-new772-diag30-native-new-m2-e3-diag-20261102-r2.service','qwen35-new772-diag150-native-new-m2-e1-diag-20261102-r1.service','qwen35-new772-diag150-native-new-m2-e5-diag-20261102-r1.service','qwen35-new772-premodel-env-new-m1-e3-diag-20261102-r1.service']
rows=[]
for unit in units:
 v=dict(x.split('=',1)for x in subprocess.check_output(['systemctl','--user','show',unit,'-p','MainPID','-p','ActiveState'],text=True).splitlines())
 if v['ActiveState']!='active':continue
 pid=int(v['MainPID']);base=Path('/proc')/str(pid);cmd=base.joinpath('cmdline').read_bytes().replace(b'\0',b' ').decode();assert base.stat().st_uid==os.getuid()and 'native'in cmd and '.py'in cmd and 'sglang'not in cmd
 stat=base.joinpath('stat').read_text().rsplit(')',1)[1].split();row=dict(unit=unit,pid=pid,start_ticks=stat[19],command=cmd,previous_state=stat[0]);os.kill(pid,signal.SIGSTOP);rows.append(row)
path=C/'NATIVE_EVAL_ADMISSION_DRIVER_QUIESCENCE_R1.json';assert not path.exists();value=dict(at=time.time(),reason='user explicitly paused new evaluations; temporary native-driver quiescence pending native START admission hook',drivers=rows,model_servers_not_signalled=True,container_agents_not_signalled=True,agent_recorders_original=True,requires_driver_resume_after_hook=True);path.write_text(json.dumps(value,indent=2)+'\n');print(json.dumps(dict(drivers=rows,model_servers_untouched=True)))
