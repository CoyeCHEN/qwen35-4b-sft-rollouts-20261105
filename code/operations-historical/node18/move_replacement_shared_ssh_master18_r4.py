"""Candidate: move only verified slot1 replacement into a new native scope.

Default is read-only. No Stop/Kill operation, process restart or rollback signal.
The existing non-delegated four-master scope is not reconfigured.
"""
from pathlib import Path
import argparse
import hashlib
import json
import re
import shlex
import subprocess
import time

R=Path('/ssd/chenkeyi/qwen35-sft-772-20261101')
C=Path('/data/chenkeyi/qwen35-sft-772-20261101/control')
D=R/'checks/shared-ssh-master-native-scope-r3'
OLD_SCOPE='qwen35-native-engine149-shared-masters18-20261103-r1.scope'
NEW_SCOPE='qwen35-native-engine149-shared-master-slot1-generation3-20261103-r1.scope'
ORIGIN='qwen35-772-native-advance-node18-20261103-r45-serving-acceptance.service'
CG_PREFIX='0::/user.slice/user-1002.slice/user@1002.service/app.slice/'
CONF=R/'control-ssh/formal-engine149-mux-r2.conf'
CONF_SHA='5e3affe0fd026b6fa8c083435222b93467215fd93d60b2511a153044f903f50c'
FIXTURE=R/'checks/shared-ssh-master-onepid-fixture-r2/ACTUAL_SINGLE_PID_NATIVE_SCOPE_CPU_ACCEPTANCE_R2.json'
FIXTURE_SHA='72e612962055e28a835e8a5f97ae4b503329e0cb090df638e64ce730baac2af6'
EXPECTED={1:(86725,'104949104',82470991)}
ABSENT_SLOTS=(0,2,3)
ENGINE='c6e16cdf-e878-4cc5-84c8-78a56c54b5c5'


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def run(args,timeout=8):
 value=subprocess.run(args,capture_output=True,text=True,timeout=timeout)
 return dict(returncode=value.returncode,stdout=value.stdout,stderr=value.stderr)


def props(unit):
 value=run(['systemctl','--user','show',unit,'-p','MainPID','-p','LoadState','-p','ActiveState','-p','ControlGroup','-p','KillMode','-p','Controller','-p','PartOf','-p','BindsTo','-p','Requires'])
 assert value['returncode']==0,value
 return dict(line.split('=',1)for line in value['stdout'].splitlines())


def owner():
 value=json.loads((C/'NATIVE_ADVANCE_OWNER.json').read_text())
 assert value['pid']==4181549 and value['start_ticks']=='104863759'and value['deployment_revision']=='r45-six-request-serving-acceptance'and value['controller_unit']==ORIGIN
 assert Path('/proc/4181549/stat').read_text().rsplit(')',1)[1].split()[19]==value['start_ticks']
 return value


def validate_master(row,slot,moved=False):
 pid,ticks,inode=EXPECTED[slot]
 assert row['pid']==pid and row['start_ticks']==ticks and row['uid']==1002 and row['comm']=='ssh'and row['state']!='Z'
 assert row['socket_uid']==1002 and row['socket_inode']==inode and row['socket_device']==66304 and row['socket_mode']==0o140600
 assert row['no_children']and row['control_socket']==str(R/'.ssh-mux-r2'/(str(slot)+'.sock'))
 assert row['argv'].rstrip()=='ssh: '+row['control_socket']+' [mux]'
 expected=NEW_SCOPE if moved else ORIGIN
 assert row['cgroup']==CG_PREFIX+expected
 return row


def master(slot,moved=False):
 sock=R/'.ssh-mux-r2'/(str(slot)+'.sock')
 check=run(['/usr/bin/ssh','-F',str(CONF),'-S',str(sock),'-o','ControlMaster=no','-o','ProxyCommand=/bin/false','-O','check','-p','18449','chenkeyi@127.0.0.1'],timeout=3)
 match=re.fullmatch(r'Master running \(pid=([0-9]+)\)\n?',check['stderr'])
 assert check['returncode']==0 and match,(slot,check)
 pid=int(match[1]);root=Path('/proc')/str(pid);values=(root/'stat').read_text().rsplit(')',1)[1].split();info=sock.stat()
 row=validate_master(dict(slot=slot,pid=pid,start_ticks=values[19],state=values[0],uid=root.stat().st_uid,comm=(root/'comm').read_text().strip(),argv=(root/'cmdline').read_bytes().replace(b'\0',b' ').decode(),cgroup=(root/'cgroup').read_text().strip(),control_socket=str(sock),socket_uid=info.st_uid,socket_inode=info.st_ino,socket_device=info.st_dev,socket_mode=info.st_mode,no_children=not(root/'task'/str(pid)/'children').read_text().strip()),slot,moved)
 row.pop('state');return row


def other_masters():
 """Guard only this project's other slots; never enter or change any process."""
 sockets={}
 for slot in ABSENT_SLOTS:
  path=R/'.ssh-mux-r2'/(str(slot)+'.sock')
  try:
   info=path.lstat();sockets[str(slot)]=dict(present=True,inode=info.st_ino,uid=info.st_uid,mode=info.st_mode)
  except FileNotFoundError:sockets[str(slot)]=dict(present=False)
 processes=[];errors=[]
 for p in Path('/proc').iterdir():
  if not p.name.isdigit():continue
  try:
   if p.stat().st_uid!=1002 or(p/'comm').read_text().strip()!='ssh':continue
   argv=(p/'cmdline').read_bytes().replace(b'\0',b' ').decode()
   if not any(str(R/'.ssh-mux-r2'/(str(slot)+'.sock'))in argv for slot in ABSENT_SLOTS):continue
   stat=(p/'stat').read_text().rsplit(')',1)[1].split()
   processes.append(dict(pid=int(p.name),start_ticks=stat[19],argv=argv,cgroup=(p/'cgroup').read_text().strip()))
  except(FileNotFoundError,ProcessLookupError):continue
  except Exception as error:errors.append(dict(pid=p.name,error=repr(error)))
 return dict(sockets=sockets,processes=processes,errors=errors)


def guard_others():
 value=other_masters()
 assert not any(x['present']for x in value['sockets'].values())and not value['processes']and not value['errors'],value
 return value


def host_io():
 value=run(['/usr/bin/ssh','-vv','-F',str(CONF),'-S',str(R/'.ssh-mux-r2/1.sock'),'-o','ControlMaster=no','-o','ProxyCommand=/bin/false','-p','18449','chenkeyi@127.0.0.1',shlex.join(['docker','info','--format','{{.ID}}'])])
 assert value['returncode']==0 and value['stdout'].strip()==ENGINE and'mux_client_request_session: master session id:'in value['stderr'],value
 return dict(passed=True,mux_session_confirmed=True,engine_id=ENGINE,fallback_prevented_by_proxycommand_false=True,
  stdout_sha256=hashlib.sha256(value['stdout'].encode()).hexdigest(),stderr_sha256=hashlib.sha256(value['stderr'].encode()).hexdigest())


def main(apply=False):
 assert sha(CONF)==CONF_SHA and sha(FIXTURE)==FIXTURE_SHA
 fixture=json.loads(FIXTURE.read_text());assert fixture['passed']and fixture['same_PID_ticks_survives_origin_service_closure']and fixture['production_PIDs_or_units_modified']is False
 current=owner();before={slot:master(slot)for slot in EXPECTED};others=guard_others()
 old=props(OLD_SCOPE);origin=props(ORIGIN);target=props(NEW_SCOPE)
 assert old['ActiveState']=='inactive'and origin['ActiveState']=='active'and origin['MainPID']=='4181549'and origin['KillMode']=='control-group'and target['LoadState']=='not-found'
 proof=dict(passed=False,apply_requested=apply,source_sha256=sha(Path(__file__)),unique_controller_owner=current,before=before,other_master_slots_before=others,original_scope=old,origin_service=origin,target_scope=NEW_SCOPE,fixture_sha256=FIXTURE_SHA,existing_processes_restarted=0,signals_sent=0,model_verifier_calls=0,old_scope_not_reconfigured=True,only_one_PID_selected=True)
 if not apply:
  proof['host_io_before']=host_io()
  assert owner()==current and {slot:master(slot)for slot in EXPECTED}==before and guard_others()==others
  return dict(**proof,read_only_identity_checks_passed=True)
 D.mkdir(exist_ok=False)
 target_path=D/'SLOT1_GENERATION3_NATIVE_SCOPE_ACCEPTANCE_R3.json'
 try:
  proof['host_io_before']=host_io()
  assert owner()==current and {slot:master(slot)for slot in EXPECTED}==before and guard_others()==others
  (D/'VALIDATED_PRE_MOVE_PLAN_R3.json').write_text(json.dumps(proof,indent=2)+'\n')
  args=['busctl','--user','call','org.freedesktop.systemd1','/org/freedesktop/systemd1','org.freedesktop.systemd1.Manager','StartTransientUnit','ssa(sv)a(sa(sv))',NEW_SCOPE,'fail','3','Description','s','RSI Engine149 shared SSH slot1 generation3 verified replacement','Slice','s','app.slice','PIDs','au','1',str(EXPECTED[1][0]),'0']
  proof['rpc_attempted']=True
  proof['rpc']=run(args)
  for _ in range(50):
   row=Path('/proc')/str(EXPECTED[1][0])/'cgroup'
   if row.read_text().strip()==CG_PREFIX+NEW_SCOPE:break
   time.sleep(.1)
  after={slot:master(slot,moved=True)for slot in EXPECTED};proof['after']=after
  for slot in EXPECTED:
   a=dict(after[slot]);b=dict(before[slot]);a.pop('cgroup');b.pop('cgroup');assert a==b
  assert proof['rpc']['returncode']==0,proof['rpc']
  actual=props(NEW_SCOPE);assert actual['ActiveState']=='active'and not any(actual[k]for k in ['Controller','PartOf','BindsTo'])and ORIGIN not in actual['Requires']
  proof['host_io_after_attempted']=True
  proof.update(target_scope_properties=actual,host_io_after=host_io())
  assert owner()==current and sha(CONF)==CONF_SHA and guard_others()==others
  assert {slot:master(slot,moved=True)for slot in EXPECTED}==after
  proof.update(passed=True,all_PID_ticks_and_control_sockets_preserved=True,other_three_master_slots_still_absent=True)
 except Exception as error:
  proof['error']=repr(error)
  raise
 finally:
  # A failed RPC can partially succeed. Record raw observations without any
  # retry, scope stop, process signal, or dependency on a responsive mux.
  observed={}
  for slot,(pid,ticks,inode)in EXPECTED.items():
   p=Path('/proc')/str(pid)
   try:observed[slot]=dict(pid=pid,start_ticks=(p/'stat').read_text().rsplit(')',1)[1].split()[19],cgroup=(p/'cgroup').read_text().strip())
   except Exception as error:observed[slot]=dict(pid=pid,error=repr(error))
  try:final_others=other_masters()
  except Exception as error:final_others=dict(error=repr(error))
  if proof.get('rpc_attempted')and not proof.get('host_io_after_attempted'):
   proof['host_io_after_attempted']=True
   try:proof['host_io_after_failure']=host_io()
   except Exception as error:proof['host_io_after_failure']=dict(error=repr(error))
  proof.update(finished_at=time.time(),actual_final_process_observations=observed,other_master_slots_final_observation=final_others,scope_stopped_as_rollback=False)
  with target_path.open('x')as stream:stream.write(json.dumps(proof,indent=2)+'\n')
  print(json.dumps(dict(passed=proof['passed'],evidence_path=str(target_path),sha256=sha(target_path))),flush=True)


if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('--apply',action='store_true');args=parser.parse_args();value=main(args.apply)
 if value is not None:print(json.dumps(value),flush=True)
