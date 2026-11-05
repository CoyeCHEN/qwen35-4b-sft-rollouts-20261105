"""Read-only CLI and bounded Recorder evidence in one probe per container."""
import argparse,concurrent.futures,datetime,hashlib,json,os,subprocess,time,sys
from pathlib import Path
KNOWN=('q35gpu78','q35new772','q35accepted30','q35synth32','q35envpreflight30')
NOP=('q35synth32prep','q35envpreflight30')
PORT_GPU={18300:0,18301:1,18302:2,18308:3,18303:4,18309:5,18306:6,18307:7}
PROBE=r'''import pathlib,json,hashlib,urllib.parse,time,os
WINDOW=128*1024;decoder=json.JSONDecoder();rows=[];errors=[]
def with_call_id(value,meta):
 candidates=[]
 for key in ['call_id','callId']:
  if isinstance(value.get(key),str):candidates.append((key,value[key]))
 for container in ['payload','data']:
  nested=value.get(container)
  if isinstance(nested,dict):
   for key in ['call_id','callId']:
    if isinstance(nested.get(key),str):candidates.append((container+'.'+key,nested[key]))
 if len({v for k,v in candidates})==1:meta.update(call_id=candidates[0][1],call_id_source_path=candidates[0][0])
 data=value.get('data',{})
 if isinstance(data,dict):
  event=data.get('event',{})
  if isinstance(event,dict) and isinstance(event.get('type'),str):
   meta['stream_event_type']=event['type'];delta=event.get('delta')
   if event['type']in ['thinking_delta','text_delta','toolcall_delta'] and isinstance(delta,str) and delta:
    meta.update(model_generated_delta=True,delta_characters=len(delta),delta_utf8_sha256=hashlib.sha256(delta.encode()).hexdigest())
  if value.get('type')=='call_chunk' and isinstance(data.get('chunk'),str):
   meta.update(provider_wire_chunk_characters=len(data['chunk']),provider_wire_chunk_sha256=hashlib.sha256(data['chunk'].encode()).hexdigest())
 return meta
def metadata_prefix(raw):
 # Parse only actual top-level scalar fields from a known physical line start.
 # Never regex-match metadata inside prompt/tool/result strings.
 text=raw.decode('utf-8',errors='replace');out={};i=0
 try:
  if not text.startswith('{'):return {}
  i=1
  while i<len(text):
   while i<len(text)and text[i].isspace():i+=1
   if i>=len(text)or text[i]=='}':break
   key,i=decoder.raw_decode(text,i)
   while i<len(text)and text[i].isspace():i+=1
   if i>=len(text)or text[i]!=':':break
   i+=1
   while i<len(text)and text[i].isspace():i+=1
   value,i=decoder.raw_decode(text,i)
   if key in ['seq','timestamp','type','call_id']:out[key]=value
   while i<len(text)and text[i].isspace():i+=1
   if i>=len(text)or text[i]!=',':break
   i+=1
 except(json.JSONDecodeError,ValueError):pass
 return out
def recorder(path):
 if not path.is_file():return dict(path=str(path),exists=False,metadata_events=[],response_events=[])
 stat=path.stat();size=stat.st_size;ranges=[('head',0,min(size,WINDOW)),('tail',max(0,size-WINDOW),min(size,WINDOW))];windows=[];events={};discarded=0
 with path.open('rb')as f:
  for role,start,length in ranges:
   boundary=True
   if start:f.seek(start-1);boundary=f.read(1)==b'\n'
   f.seek(start);raw=f.read(length);windows.append(dict(role=role,offset=start,bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest(),starts_at_physical_line_boundary=boundary))
   cursor=0
   if not boundary:
    first=raw.find(b'\n')
    if first<0:discarded+=1;continue
    cursor=first+1;discarded+=1
   while cursor<len(raw):
    end=raw.find(b'\n',cursor);complete=end>=0;piece=raw[cursor:end]if complete else raw[cursor:];absolute=start+cursor;meta={}
    if complete:
     try:
      value=json.loads(piece);meta=with_call_id(value,{k:value[k]for k in ['seq','timestamp','type','call_id']if k in value})
     except(ValueError,UnicodeDecodeError):pass
    else:meta=metadata_prefix(piece)
    if meta.get('type'):
     entry=dict(**meta,byte_offset=absolute,complete_jsonl_record=complete,observed_bytes=len(piece),observed_bytes_sha256=hashlib.sha256(piece).hexdigest(),metadata_from_known_line_prefix=not complete)
     previous=events.get(absolute)
     if previous is None or complete:events[absolute]=entry
    if not complete:break
    cursor=end+1
 observed=sorted(events.values(),key=lambda x:x['byte_offset']);responses=[x for x in observed if x.get('model_generated_delta')is True and isinstance(x.get('timestamp'),(int,float))]
 return dict(path=str(path),exists=True,size_at_start=size,size_after=path.stat().st_size,mtime_ns_at_start=stat.st_mtime_ns,windows=windows,leading_fragments_discarded=discarded,metadata_events=observed,response_events=responses,first_response_event=responses[0]if responses else None,last_response_event=responses[-1]if responses else None,observation_limited_to_head_tail=True)
for p in pathlib.Path('/proc').iterdir():
 if not p.name.isdigit():continue
 try:
  argv=[s.decode(errors='replace')for s in(p/'cmdline').read_bytes().split(b'\x00')if s]
  if not any(pathlib.Path(s).name=='open-harness'for s in argv)or'--config'not in argv:continue
  config=pathlib.Path(argv[argv.index('--config')+1])
  if not str(config).startswith('/harbor/agent-runtime/harbor-open-harness-'):continue
  st=(p/'stat').read_text().rsplit(')',1)[1].split();raw=config.read_bytes();model=json.loads(raw)['model'];url=model['baseUrl'];hz=os.sysconf('SC_CLK_TCK');observed_at=time.time();boot=time.clock_gettime(time.CLOCK_BOOTTIME)
  root=pathlib.Path(argv[argv.index('--trajectory-dir')+1])if'--trajectory-dir'in argv else pathlib.Path('/logs/agent/openharness-rollout');assert str(root).startswith('/logs/agent/')
  event=recorder(root/'events.jsonl');until=time.clock_gettime(time.CLOCK_BOOTTIME);again=(p/'stat').read_text().rsplit(')',1)[1].split();live=again[19]==st[19]and again[0]!='Z'
  rows.append(dict(pid=int(p.name),start_ticks=st[19],start_boottime_upper_bound=(int(st[19])+1)/hz,live_until_boottime_lower_bound=until,live_after_probe=live,config_path=str(config),config_sha256=hashlib.sha256(raw).hexdigest(),model_id=model.get('id'),base_url=url,port=urllib.parse.urlsplit(url).port,observed_at=observed_at,observed_boottime=boot,time_namespace=os.readlink('/proc/self/ns/time'),time_namespace_offsets={parts[0]:[int(parts[1]),int(parts[2])]for line in pathlib.Path('/proc/self/timens_offsets').read_text().splitlines()if len(parts:=line.split())==3},recorder=event))
 except(FileNotFoundError,ProcessLookupError):continue
 except Exception as exc:errors.append(dict(pid=p.name,error=repr(exc)))
p=pathlib.Path('/logs/agent/open-harness.complete.json')
print(json.dumps(dict(at=time.time(),active_cli_leases=rows,errors=errors,cli_completion=json.loads(p.read_text())if p.exists()else None)))'''
compile(PROBE,'<bounded-recorder-probe>','exec')
def main(output_root,stdout_only=False,source_sha256=None):
 start_wall=time.time();start_boot=time.clock_gettime(time.CLOCK_BOOTTIME);start=time.monotonic();namespace=os.readlink('/proc/self/ns/time');time_offsets={parts[0]:[int(parts[1]),int(parts[2])]for line in Path('/proc/self/timens_offsets').read_text().splitlines()if len(parts:=line.split())==3}
 raw=subprocess.check_output(['docker','ps','--no-trunc','--format','{{json .}}','--filter','label=io.harbor.remote-docker.identity'],text=True,timeout=12)
 docs=[]
 for line in raw.splitlines():
  item=json.loads(line);labels=dict(part.split('=',1) for part in item.get('Labels','').split(',') if '='in part)
  docs.append(dict(Id=item['ID'],Name=item['Names'],State=dict(Status=item['State']),Config=dict(Labels=labels)))
 def inspect(d):
  labels=d['Config'].get('Labels')or{};project=labels.get('com.docker.compose.project','');row=dict(container_id=d['Id'],project=project,identity=labels.get('io.harbor.remote-docker.identity'),name=d['Name'],state=d['State']['Status'])
  if not project.startswith(KNOWN):return dict(**row,status='OUTSIDE_PROJECT_SCOPE_NOT_ENTERED')
  if project.startswith(NOP):return dict(**row,status='DECLARED_NO_MODEL_PREFLIGHT_LANE',active_cli_leases=[])
  try:
   p=subprocess.run(['docker','exec','-u','root',d['Id'],'/harbor/agent-runtime/harbor-open-harness-venv/bin/python','-c',PROBE],capture_output=True,text=True,timeout=20)
   if p.returncode:return dict(**row,status='UNKNOWN',error=p.stderr[-1000:])
   value=json.loads(p.stdout);return dict(**row,status='UNKNOWN'if value['errors']else'OBSERVED',**value)
  except Exception as exc:return dict(**row,status='UNKNOWN',error=repr(exc))
 with concurrent.futures.ThreadPoolExecutor(max_workers=4)as pool:rows=list(pool.map(inspect,docs))
 leases=[]
 for row in rows:
  for lease in row.get('active_cli_leases',[]):
   x=dict(container_id=row['container_id'],project=row['project'],identity=row['identity'],completion_marker=row.get('cli_completion'),**lease);responses=x['recorder']['response_events'];last=responses[-1]if responses else None;age=x['observed_at']-last['timestamp']if last else None
   x.update(gpu_index=PORT_GPU.get(x['port']),response_event_observed=bool(responses),recent_response_event=age is not None and 0<=age<30,last_response_age_seconds=age)
   x['activity_status']='CLI_CLOSED_OR_CHANGED'if row.get('cli_completion')or not x['live_after_probe']else('ACTIVE_CLI_WITH_RECENT_RESPONSE'if x['recent_response_event']else'ACTIVE_CLI_WITH_RESPONSE_HISTORY_TOOL_OR_PROVIDER_PHASE'if responses else'ACTIVE_CLI_NO_RESPONSE_IN_BOUNDED_WINDOWS')
   leases.append(x)
 active=[x for x in leases if x['live_after_probe']and x['completion_marker']is None];confirmed=[x for x in active if x['response_event_observed']];ports=sorted({x['port']for x in confirmed if x['port']in PORT_GPU});recent=sorted({x['port']for x in confirmed if x['recent_response_event']and x['port']in PORT_GPU});representatives={}
 offset=start_wall-start_boot
 for port in ports:
  candidates=[x for x in confirmed if x['port']==port and x['time_namespace_offsets'].get('boottime')==time_offsets.get('boottime') and start_boot-1<=x['observed_boottime']<=time.clock_gettime(time.CLOCK_BOOTTIME)+1]
  if candidates:representatives[port]=min(candidates,key=lambda x:max(x['start_boottime_upper_bound'],x['recorder']['first_response_event']['timestamp']-offset))
 overlap=None
 if set(representatives)==set(PORT_GPU):
  lower=max(max(x['start_boottime_upper_bound'],x['recorder']['first_response_event']['timestamp']-offset)for x in representatives.values());upper=min(x['live_until_boottime_lower_bound']for x in representatives.values());overlap=dict(proven=lower<=upper,boottime_lower_bound=lower,boottime_upper_bound=upper,wall_time_lower_bound=lower+offset,wall_time_upper_bound=upper+offset,clock_domain='same Engine149 CLOCK_BOOTTIME and Recorder CLOCK_REALTIME',engine149_time_namespace=namespace,engine149_time_namespace_offsets=time_offsets,all_representative_boottime_offsets_match=True,representative_container_by_port={str(p):x['container_id']for p,x in representatives.items()},response_history_already_present_at_overlap_start=True)
 value=dict(schema='actual-cli-recorder-generated-delta-overlap-r6-ps-labels',started_at_engine149=start_wall,finished_at_engine149=time.time(),seconds=time.monotonic()-start,engine149_time_namespace=namespace,engine149_time_namespace_offsets=time_offsets,port_to_gpu=PORT_GPU,actual_active_cli_count=len(active),active_cli_with_observed_response=len(confirmed),ports_with_active_cli_and_real_response=ports,gpu_indices_with_active_cli_and_real_response=sorted(PORT_GPU[p]for p in ports),ports_with_recent_response=recent,all_eight_ports_active_with_real_response=set(ports)==set(PORT_GPU),eight_gpu_overlap=overlap,leases=leases,containers=rows,unknown_project_containers=sum(x['status']=='UNKNOWN'for x in rows),recorder_window_bytes_each=128*1024,raw_recorders_unmodified=True,model_generation_calls_by_observer=0,source_sha256=source_sha256 or hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),probe_sha256=hashlib.sha256(PROBE.encode()).hexdigest())
 if stdout_only:
  print(json.dumps(value,indent=2));return
 destination=Path(output_root)/datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ');destination.mkdir(parents=True,exist_ok=False);proof=destination/'ACTUAL_CLI_RESPONSE_OVERLAP_R4.json';proof.write_text(json.dumps(value,indent=2)+'\n')
 print(json.dumps(dict(path=str(proof),sha256=hashlib.sha256(proof.read_bytes()).hexdigest(),active_cli=len(active),with_real_response=len(confirmed),ports=ports,recent_ports=recent,all_eight=value['all_eight_ports_active_with_real_response'],overlap=overlap,seconds=value['seconds'])))
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--output-root',default='/home/chenkeyi/.local/share/harbor-rsi/qwen35-new772-tb21-20261101/checks/active-recorder-evidence-r6');p.add_argument('--stdout',action='store_true');p.add_argument('--source-sha256');args=p.parse_args();main(args.output_root,args.stdout,args.source_sha256)
