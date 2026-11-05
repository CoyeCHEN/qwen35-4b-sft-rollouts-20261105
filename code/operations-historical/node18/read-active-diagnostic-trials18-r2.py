"""Read actual owned containers, Recorder streams, native configs and GPU processes."""
import base64,concurrent.futures,hashlib,json,shlex,subprocess,time
from pathlib import Path
R=Path('/ssd/chenkeyi/qwen35-sft-772-20261101');E=R/'formal-native-eval-r1';C=Path('/data/chenkeyi/qwen35-sft-772-20261101/control')
REMOTE=r'''
import base64,concurrent.futures,json,pathlib,subprocess,time
rows=[x.split()for x in subprocess.check_output(['docker','ps','--format','{{.ID}} {{.Names}}'],text=True).splitlines()if x.split()[1].startswith(('q35gpu78','q35new772e3fixednewm1','q35selected267'))]
def observe(pair):
 cid,name=pair
 out=subprocess.run(['docker','exec',cid,'tail','-c','32768','/logs/agent/openharness-rollout/events.jsonl'],capture_output=True,timeout=10)
 return dict(container_id=cid,name=name,observed_at=time.time(),tail_base64=base64.b64encode(out.stdout).decode(),tail_return_code=out.returncode)
with concurrent.futures.ThreadPoolExecutor(max_workers=4)as pool:observed=list(pool.map(observe,rows))
original_configs={}
A=pathlib.Path('/home/chenkeyi/.local/share/harbor-rsi/qwen35-new772-tb21-20261101')
for p in (A/'jobs').glob('qwen35-new772*/*/remote-docker-*.jsonl'):
 cfg=p.parent/'config.json'
 if cfg.exists():original_configs[p.stem.removeprefix('remote-docker-')]=dict(config=json.loads(cfg.read_text()),trial_path=str(p.parent),result_exists=(p.parent/'result.json').exists())
print(json.dumps(dict(containers=observed,original_configs=original_configs)))
'''
def read(p):return json.loads(p.read_text())
def main():
 t=time.time();remote=json.loads(subprocess.check_output(['/usr/bin/ssh','-F',str(R/'control-ssh/formal-engine149-r1.conf'),'127.0.0.1','python3 -c '+shlex.quote(REMOTE)],text=True,timeout=45));mapping=remote['original_configs']
 for p in(E/'jobs').glob('*/*/remote-docker-*.jsonl'):
  cfg=p.parent/'config.json'
  if cfg.exists():mapping[p.stem.removeprefix('remote-docker-')]=dict(config=read(cfg),trial_path=str(p.parent),result_exists=(p.parent/'result.json').exists())
 directory=R/'runtime-snapshots'/('active-diagnostics-clock-aware-'+str(int(t)));directory.mkdir(parents=True);rows=[]
 gpu_by_port={18300:0,18301:1,18302:2,18308:3,18303:4,18309:5,18306:6,18307:7}
 for item in remote['containers']:
  raw=base64.b64decode(item.pop('tail_base64'));p=directory/(item['container_id']+'.events-tail.bin');p.write_bytes(raw)
  events=[]
  for line in raw.splitlines():
   try:
    v=json.loads(line);events.append({k:v[k]for k in ['seq','timestamp','type','call_id']if k in v})
   except(ValueError,UnicodeDecodeError):pass
  identity=item['name'].removesuffix('-main-1').rsplit('-',1)[1];link=mapping.get(identity);row=dict(item,identity=identity,tail_path=str(p),tail_sha256=hashlib.sha256(raw).hexdigest(),events_observed=len(events),last_event=events[-1]if events else None)
  if link:
   cfg=link['config'];model=cfg['agent']['kwargs']['config']['model'];port=int(model['baseUrl'].split(':')[-1].split('/')[0]);chunks=[e for e in events if e['type']in ['call_chunk','call_event']]
   row.update(trial_path=link['trial_path'],task_id=Path(cfg['task']['path']).name,model_id=model['id'],base_url=model['baseUrl'],port=port,gpu_index=gpu_by_port.get(port),native_result_already_exists=link['result_exists'],recent_model_stream=bool(chunks and 0<=item['observed_at']-chunks[-1].get('timestamp',0)<30 and not link['result_exists']),last_stream_event=chunks[-1]if chunks else None)
  rows.append(row)
 gpu=subprocess.check_output(['nvidia-smi','--query-gpu=index,uuid,utilization.gpu,memory.used','--format=csv,noheader,nounits'],text=True)
 processes=subprocess.check_output(['nvidia-smi','--query-compute-apps=gpu_uuid,pid,used_memory','--format=csv,noheader,nounits'],text=True)
 active={x['gpu_index']for x in rows if x.get('recent_model_stream')and x.get('gpu_index')is not None}
 value=dict(at=t,finished_at=time.time(),owner=read(C/'NATIVE_ADVANCE_OWNER.json'),owned_containers=len(rows),native_trials_with_recent_model_stream=sum(bool(x.get('recent_model_stream'))for x in rows),gpu_indices_with_recent_model_stream=sorted(active),all_eight_gpu_backends_with_actual_recorder_stream=len(active)==8,rows=rows,gpu_query=gpu,gpu_processes=processes,event_age_uses_engine149_clock_for_both_observer_and_event=True,raw_recorders_unmodified=True,read_only=True,source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
 proof=directory/'ACTUAL_DIAGNOSTIC_CONCURRENCY.json';proof.write_text(json.dumps(value,indent=2)+'\n')
 latest=R/'checks/ACTUAL_DIAGNOSTIC_CONCURRENCY_LATEST_R2.json';temporary=latest.with_suffix('.tmp');temporary.write_bytes(proof.read_bytes());temporary.replace(latest)
 print(json.dumps(dict(proof=str(proof),owned_containers=len(rows),actual_model_stream_trials=value['native_trials_with_recent_model_stream'],gpu_indices=sorted(active),all_eight=len(active)==8)))
if __name__=='__main__':main()
