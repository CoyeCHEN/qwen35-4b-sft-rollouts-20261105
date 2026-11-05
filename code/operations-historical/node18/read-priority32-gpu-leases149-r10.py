"""Campaign-only read-only CLI identity and bounded Recorder evidence; no dispatch."""
import argparse,concurrent.futures,datetime,hashlib,json,os,shlex,subprocess,time,sys,urllib.parse,urllib.request
from pathlib import Path
KNOWN=('q35gpu78','q35new772','q35accepted30','q35synth32','q35envpreflight30')
OLD_TAGS=['old-M1','old-M2']+[a+'-epoch'+str(e)for a in 'ABCD'for e in(1,3,5)]
FUTURE_SCOPE=('q35selected267-','q35envpreflight59r1-')+tuple('q35old112'+tag.lower().replace('-','')+'-'for tag in OLD_TAGS)
NOP=('q35synth32prep','q35envpreflight30')
R=Path('/ssd/chenkeyi/qwen35-sft-772-20261101')
PROBE="import pathlib,json,hashlib,urllib.parse,time,os\nWINDOW=1024*1024;HEAD_WINDOW=128*1024;decoder=json.JSONDecoder();rows=[];errors=[]\ndef with_call_id(value,meta):\n candidates=[]\n for key in ['call_id','callId']:\n  if isinstance(value.get(key),str):candidates.append((key,value[key]))\n for container in ['payload','data']:\n  nested=value.get(container)\n  if isinstance(nested,dict):\n   for key in ['call_id','callId']:\n    if isinstance(nested.get(key),str):candidates.append((container+'.'+key,nested[key]))\n if len({v for k,v in candidates})==1:meta.update(call_id=candidates[0][1],call_id_source_path=candidates[0][0])\n data=value.get('data',{})\n if isinstance(data,dict):\n  event=data.get('event',{})\n  if value.get('type')=='call_event' and isinstance(event,dict) and isinstance(event.get('type'),str):\n   meta['stream_event_type']=event['type'];delta=event.get('delta')\n   if event['type']in ['thinking_delta','text_delta','toolcall_delta'] and isinstance(delta,str) and delta:\n    meta.update(model_generated_delta=True,delta_characters=len(delta),delta_utf8_sha256=hashlib.sha256(delta.encode()).hexdigest())\n  if value.get('type')=='call_chunk' and isinstance(data.get('chunk'),str):\n   meta.update(provider_wire_chunk_characters=len(data['chunk']),provider_wire_chunk_sha256=hashlib.sha256(data['chunk'].encode()).hexdigest())\n return meta\ndef metadata_prefix(raw):\n # Parse only actual top-level scalar fields from a known physical line start.\n # Never regex-match metadata inside prompt/tool/result strings.\n text=raw.decode('utf-8',errors='replace');out={};i=0\n try:\n  if not text.startswith('{'):return {}\n  i=1\n  while i<len(text):\n   while i<len(text)and text[i].isspace():i+=1\n   if i>=len(text)or text[i]=='}':break\n   key,i=decoder.raw_decode(text,i)\n   while i<len(text)and text[i].isspace():i+=1\n   if i>=len(text)or text[i]!=':':break\n   i+=1\n   while i<len(text)and text[i].isspace():i+=1\n   value,i=decoder.raw_decode(text,i)\n   if key in ['seq','timestamp','type','call_id']:out[key]=value\n   while i<len(text)and text[i].isspace():i+=1\n   if i>=len(text)or text[i]!=',':break\n   i+=1\n except(json.JSONDecodeError,ValueError):pass\n return out\ndef recorder(path):\n if not path.is_file():return dict(path=str(path),exists=False,metadata_events=[],response_events=[])\n stat=path.stat();size=stat.st_size;ranges=[('head',0,min(size,HEAD_WINDOW)),('tail',max(0,size-WINDOW),min(size,WINDOW))];windows=[];events={};discarded=0\n with path.open('rb')as f:\n  for role,start,length in ranges:\n   boundary=True\n   if start:f.seek(start-1);boundary=f.read(1)==b'\\n'\n   f.seek(start);raw=f.read(length);windows.append(dict(role=role,offset=start,bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest(),starts_at_physical_line_boundary=boundary))\n   cursor=0\n   if not boundary:\n    first=raw.find(b'\\n')\n    if first<0:discarded+=1;continue\n    cursor=first+1;discarded+=1\n   while cursor<len(raw):\n    end=raw.find(b'\\n',cursor);complete=end>=0;piece=raw[cursor:end]if complete else raw[cursor:];absolute=start+cursor;meta={}\n    if complete:\n     try:\n      value=json.loads(piece);meta=with_call_id(value,{k:value[k]for k in ['seq','timestamp','type','call_id']if k in value})\n     except(ValueError,UnicodeDecodeError):pass\n    else:meta=metadata_prefix(piece)\n    if meta.get('type'):\n     entry=dict(**meta,byte_offset=absolute,complete_jsonl_record=complete,observed_bytes=len(piece),observed_bytes_sha256=hashlib.sha256(piece).hexdigest(),metadata_from_known_line_prefix=not complete)\n     previous=events.get(absolute)\n     if previous is None or complete:events[absolute]=entry\n    if not complete:break\n    cursor=end+1\n observed=sorted(events.values(),key=lambda x:x['byte_offset']);responses=[x for x in observed if x.get('model_generated_delta')is True and isinstance(x.get('timestamp'),(int,float))]\n return dict(path=str(path),exists=True,size_at_start=size,size_after=path.stat().st_size,mtime_ns_at_start=stat.st_mtime_ns,windows=windows,leading_fragments_discarded=discarded,metadata_events_count=len(observed),metadata_events_sha256=hashlib.sha256(json.dumps(observed,sort_keys=True,separators=(',',':')).encode()).hexdigest(),response_events_count=len(responses),response_events_sha256=hashlib.sha256(json.dumps(responses,sort_keys=True,separators=(',',':')).encode()).hexdigest(),response_events=list({x['byte_offset']:x for x in responses[:1]+responses[-8:]}.values()),response_event_evidence_is_bounded_subset=True,first_response_event=responses[0]if responses else None,last_response_event=responses[-1]if responses else None,observation_limited_to_head_tail=True)\nfor p in pathlib.Path('/proc').iterdir():\n if not p.name.isdigit():continue\n try:\n  argv=[s.decode(errors='replace')for s in(p/'cmdline').read_bytes().split(b'\\x00')if s]\n  if not any(pathlib.Path(s).name=='open-harness'for s in argv)or'--config'not in argv:continue\n  config=pathlib.Path(argv[argv.index('--config')+1])\n  if not str(config).startswith('/harbor/agent-runtime/harbor-open-harness-'):continue\n  st=(p/'stat').read_text().rsplit(')',1)[1].split();raw=config.read_bytes();model=json.loads(raw)['model'];url=model['baseUrl'];hz=os.sysconf('SC_CLK_TCK');observed_at=time.time();boot=time.clock_gettime(time.CLOCK_BOOTTIME)\n  root=pathlib.Path(argv[argv.index('--trajectory-dir')+1])if'--trajectory-dir'in argv else pathlib.Path('/logs/agent/openharness-rollout');assert str(root).startswith('/logs/agent/')\n  event=recorder(root/'events.jsonl');until=time.clock_gettime(time.CLOCK_BOOTTIME);again=(p/'stat').read_text().rsplit(')',1)[1].split();live=again[19]==st[19]and again[0]!='Z'\n  rows.append(dict(pid=int(p.name),start_ticks=st[19],start_boottime_upper_bound=(int(st[19])+1)/hz,live_until_boottime_lower_bound=until,live_after_probe=live,config_path=str(config),config_sha256=hashlib.sha256(raw).hexdigest(),model_id=model.get('id'),base_url=url,port=urllib.parse.urlsplit(url).port,observed_at=observed_at,observed_boottime=boot,time_namespace=os.readlink('/proc/self/ns/time'),time_namespace_offsets={parts[0]:[int(parts[1]),int(parts[2])]for line in pathlib.Path('/proc/self/timens_offsets').read_text().splitlines()if len(parts:=line.split())==3},recorder=event))\n except(FileNotFoundError,ProcessLookupError):continue\n except Exception as exc:errors.append(dict(pid=p.name,error=repr(exc)))\np=pathlib.Path('/logs/agent/open-harness.complete.json')\nprint(json.dumps(dict(at=time.time(),active_cli_leases=rows,errors=errors,cli_completion=json.loads(p.read_text())if p.exists()else None)))"
compile(PROBE,'<bounded-recorder-probe-r8>','exec')

def canonical_sha(value):
 return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()

def command_value(command,flag):
 positions=[i for i,x in enumerate(command)if x==flag]
 if not positions:raise ValueError('Missing frozen serving flag: '+flag)
 return command[positions[-1]+1]

def campaign_bindings(root=R):
 """Read existing campaign identities. Do not infer a model from a port alone."""
 root=Path(root);sources=[];rows=[]
 def read(path):
  path=Path(path);blob=path.read_bytes();sources.append(dict(path=str(path),sha256=hashlib.sha256(blob).hexdigest(),bytes=len(blob)));return json.loads(blob)
 runtime=read(root/'new-sft/workspace/configs/runtime.json');authorized=runtime['authorized_gpu_uuids']
 assert len(authorized)==len(set(authorized))==8
 def bind(model,replica,source):
  index=replica.get('gpu_index');uuid=replica['gpu_uuid']
  if index is None:index=authorized.index(uuid)
  assert isinstance(index,int)and 0<=index<8 and authorized[index]==uuid
  manifest=Path(model['model_manifest']);blob=manifest.read_bytes();digest=hashlib.sha256(blob).hexdigest()
  assert digest==model['weight_version'],'Frozen HF release identity differs'
  sources.append(dict(path=str(manifest),sha256=digest,bytes=len(blob)))
  row=dict(model_id=model['model_id'],model_path=model['model_path'],weight_version=model['weight_version'],
   port=replica['port'],gpu_index=index,gpu_uuid=uuid,unit=replica.get('unit',model.get('serving_unit')),source=source)
  assert isinstance(row['port'],int)and 1024<=row['port']<=65535 and isinstance(row['model_id'],str)and row['model_id']
  rows.append(row)
 config_path=root/'configs/diagnostic150-five-model-r1.json';config=read(config_path)
 current={}
 for model in config['models']:
  for replica in model.get('replicas')or[dict(gpu_index=model['gpu_index'],gpu_uuid=model['gpu_uuid'],port=model['port'],unit=model['serving_unit'])]:
   current[replica['gpu_index']]=(model,replica,str(config_path))
 priority=root/'synthetic32/priority-gpu-replicas-r1/COLD_REPLICAS_LAUNCHED.json'
 if priority.exists():
  proof=read(priority)
  for item in proof['replicas']:
   replica=item['new_replica'];command=replica['command'];alias=command_value(command,'--served-model-name')
   model=next(x for x in config['models']if x['model_path']==replica['model_path']and x['weight_version']==replica['weight_version'])
   assert command_value(command,'--model-path')==replica['model_path']and command_value(command,'--weight-version')==replica['weight_version']
   assert int(command_value(command,'--port'))==replica['port']and '--setenv=CUDA_VISIBLE_DEVICES='+replica['gpu_uuid']in command
   current[replica['gpu_index']]=(model|dict(model_id=alias),replica,str(priority))
 for model,replica,source in current.values():bind(model,replica,source)
 selected=root/'checks/SELECTED267_MODEL_BINDING_R1.json'
 if selected.exists():
  model=read(selected);assert model['tag']=='selected267'and model['new_trials']==267
  for replica in model['replicas']:bind(model,replica,str(selected))
 # Historical receipts can share a port. Actual CLI alias AND current model_info
 # must match; an old receipt alone never declares the current service identity.
 for tag in OLD_TAGS:
  path=root/'old-four-arm/checks'/('OLD112_COLD_DEPLOYMENT_'+tag+'.json')
  if not path.exists():continue
  model=read(path);command=model['command'];assert model['tag']==tag
  assert command_value(command,'--served-model-name')==model['model_id']
  assert command_value(command,'--model-path')==model['model_path']and command_value(command,'--weight-version')==model['weight_version']
  assert int(command_value(command,'--port'))==model['port']and '--setenv=CUDA_VISIBLE_DEVICES='+model['gpu_uuid']in command
  bind(model,dict(gpu_uuid=model['gpu_uuid'],port=model['port'],unit=model['unit']),str(path))
 unique={}
 for row in rows:
  key=row['model_id'],row['port'];previous=unique.get(key)
  if previous:assert all(previous[k]==row[k]for k in['model_path','weight_version','gpu_index','gpu_uuid'])
  else:unique[key]=row
 return dict(kind='FROZEN_CAMPAIGN_MODEL_BINDINGS_FOR_READ_ONLY_OBSERVATION_R1',authorized_gpu_uuids=authorized,
  bindings=list(unique.values()),sources=list({x['path']:x for x in sources}.values()),future_scope_prefixes=FUTURE_SCOPE,
  old_env8_namespace_note='Native old-env8 shares q35old112oldm1 with old-M1; always inspect CLI, never skip this prefix as NOP')

def observe_from_node18(root=R):
 """Existing project SSH transport, stdout only; no remote files or model calls."""
 root=Path(root);binding=campaign_bindings(root);blob=json.dumps(binding,separators=(',',':'));source=Path(__file__).read_text();digest=hashlib.sha256(source.encode()).hexdigest()
 command=['python3','-','--stdout','--source-sha256',digest,'--bindings-json',blob,'--bindings-sha256',canonical_sha(binding)]
 process=subprocess.run([str(root/'reliability-repair/native-client-bin-r1/ssh'),'-p','18449','chenkeyi@127.0.0.1',shlex.join(command)],
  input=source,capture_output=True,text=True,timeout=35,
  env=dict(os.environ,RSI_REMOTE_DOCKER_SSH_CONFIG=str(root/'control-ssh/formal-engine149-mux-r2.conf')))
 if process.returncode:raise RuntimeError('Read-only campaign observer failed: '+process.stderr[-1200:])
 value=json.loads(process.stdout)
 assert value['source_sha256']==digest and value['campaign_bindings_sha256']==canonical_sha(binding)
 return value

def in_scope(project,identity):
 return isinstance(identity,str)and len(identity)==32 and all(x in'0123456789abcdef'for x in identity)and project.endswith('-'+identity)and project.startswith(KNOWN+FUTURE_SCOPE)

def get_model_info(url):
 parsed=urllib.parse.urlsplit(url)
 if parsed.scheme!='http'or parsed.hostname not in['172.17.0.1','127.0.0.1','localhost']or parsed.username or parsed.password:
  raise ValueError('Model service URL is outside campaign local forwards')
 request=urllib.parse.urlunsplit((parsed.scheme,parsed.netloc,'/model_info','',''))
 opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
 with opener.open(request,timeout=5)as response:return json.load(response)

def identify(lease,binding,model_info):
 matches=[r for r in binding['bindings']if r['model_id']==lease['model_id']and r['port']==lease['port']]
 if len(matches)!=1:return dict(passed=False,status='UNKNOWN_ALIAS_OR_PORT_BINDING')
 expected=matches[0]
 if not isinstance(model_info,dict)or model_info.get('model_path')!=expected['model_path']or model_info.get('weight_version')!=expected['weight_version']:
  return dict(passed=False,status='UNKNOWN_CURRENT_SERVICE_IDENTITY',expected=expected,actual_model_info=model_info)
 assert binding['authorized_gpu_uuids'][expected['gpu_index']]==expected['gpu_uuid']
 return dict(passed=True,status='FROZEN_ALIAS_PORT_AND_ACTUAL_SERVICE_MATCH',binding=expected,actual_model_info=model_info)

def summarize(rows,binding,start_wall,start_boot,namespace,time_offsets,source_sha256):
 info={};leases=[]
 urls={x['base_url']for row in rows for x in row.get('active_cli_leases',[])if x['live_after_probe']}
 def fetch(url):
  try:return url,get_model_info(url)
  except Exception as error:return url,dict(error=repr(error))
 with concurrent.futures.ThreadPoolExecutor(max_workers=4)as pool:info.update(pool.map(fetch,urls))
 for row in rows:
  for lease in row.get('active_cli_leases',[]):
   x=dict(container_id=row['container_id'],project=row['project'],identity=row['identity'],completion_marker=row.get('cli_completion'),**lease)
   identity=identify(x,binding,info.get(x['base_url']))if x['live_after_probe']else dict(passed=False,status='CLI_CLOSED_OR_CHANGED')
   x['model_identity']=identity;x.update(gpu_index=identity.get('binding',{}).get('gpu_index'),gpu_uuid=identity.get('binding',{}).get('gpu_uuid'))
   responses=x['recorder']['response_events'];last=responses[-1]if responses else None;age=x['observed_at']-last['timestamp']if last else None
   x.update(response_event_observed=bool(responses),recent_response_event=age is not None and 0<=age<30,last_response_age_seconds=age,
    recent_generation_status='OBSERVED_NONEMPTY_DELTA'if age is not None and 0<=age<30 else'UNKNOWN_BOUNDED_WINDOWS_NO_RECENT_DELTA')
   x['activity_status']='CLI_CLOSED_OR_CHANGED'if not x['live_after_probe']else'ACTIVE_CLI_IDENTITY_UNKNOWN'if not identity['passed']else'ACTIVE_CLI_WITH_RECENT_RESPONSE'if x['recent_response_event']else'ACTIVE_CLI_RECENT_GENERATION_UNKNOWN_TOOL_OR_PROVIDER_PHASE'
   if x['live_after_probe']and x['completion_marker']is not None:
    x['model_identity']=dict(passed=False,status='UNKNOWN_LIVE_CLI_WITH_COMPLETION_MARKER',prior=identity)
   leases.append(x)
 # A completion marker and missing delta never override a still-live PID identity.
 active=[x for x in leases if x['live_after_probe']]
 confirmed=[x for x in active if x['model_identity']['passed']and x['response_event_observed']]
 ports=sorted({x['port']for x in confirmed});recent=sorted({x['port']for x in confirmed if x['recent_response_event']})
 representatives={};offset=start_wall-start_boot
 for index in {x['gpu_index']for x in confirmed}:
  candidates=[x for x in confirmed if x['gpu_index']==index and x['time_namespace_offsets'].get('boottime')==time_offsets.get('boottime')and start_boot-1<=x['observed_boottime']<=time.clock_gettime(time.CLOCK_BOOTTIME)+1]
  if candidates:representatives[index]=min(candidates,key=lambda x:max(x['start_boottime_upper_bound'],x['recorder']['first_response_event']['timestamp']-offset))
 overlap=None
 if set(representatives)==set(range(len(binding['authorized_gpu_uuids']))):
  lower=max(max(x['start_boottime_upper_bound'],x['recorder']['first_response_event']['timestamp']-offset)for x in representatives.values());upper=min(x['live_until_boottime_lower_bound']for x in representatives.values())
  overlap=dict(proven=lower<=upper,boottime_lower_bound=lower,boottime_upper_bound=upper,wall_time_lower_bound=lower+offset,wall_time_upper_bound=upper+offset,
   clock_domain='same Engine149 CLOCK_BOOTTIME and Recorder CLOCK_REALTIME',engine149_time_namespace=namespace,engine149_time_namespace_offsets=time_offsets,
   representative_container_by_gpu={str(i):x['container_id']for i,x in representatives.items()},response_history_already_present_at_overlap_start=True)
 unknown_rows=[x for x in rows if x['status']=='UNKNOWN'];unknown_leases=[x for x in active if not x['model_identity']['passed']]
 return dict(schema='actual-cli-campaign-identity-and-bounded-recorder-r8',at=time.time(),started_at_engine149=start_wall,finished_at_engine149=time.time(),
  engine149_time_namespace=namespace,engine149_time_namespace_offsets=time_offsets,actual_active_cli_count=len(active),active_cli_with_observed_response=len(confirmed),
  active_cli_leases=active,leases=leases,ports_with_active_cli_and_real_response=ports,ports_with_recent_response=recent,
  gpu_indices_with_active_cli_and_real_response=sorted({x['gpu_index']for x in confirmed}),
  all_eight_ports_active_with_real_response=set(representatives)==set(range(len(binding['authorized_gpu_uuids']))),eight_gpu_overlap=overlap,
  containers=rows,unknown_project_containers=len({x['container_id']for x in unknown_rows+unknown_leases}),unknown_model_identity_leases=len(unknown_leases),
  complete=not unknown_rows and not unknown_leases,read_only=True,model_generation_calls=0,model_generation_calls_by_observer=0,
  campaign_bindings=binding,campaign_bindings_sha256=canonical_sha(binding),recorder_head_window_bytes=128*1024,recorder_tail_window_bytes=1024*1024,
  no_recent_delta_is_not_an_empty_slot=True,raw_recorders_unmodified=True,source_sha256=source_sha256,probe_sha256=hashlib.sha256(PROBE.encode()).hexdigest())

def main(output_root,stdout_only=False,source_sha256=None,binding=None):
 assert binding and binding['kind']=='FROZEN_CAMPAIGN_MODEL_BINDINGS_FOR_READ_ONLY_OBSERVATION_R1'
 assert tuple(binding['future_scope_prefixes'])==FUTURE_SCOPE
 start_wall=time.time();start_boot=time.clock_gettime(time.CLOCK_BOOTTIME);start=time.monotonic();namespace=os.readlink('/proc/self/ns/time')
 offsets={parts[0]:[int(parts[1]),int(parts[2])]for line in Path('/proc/self/timens_offsets').read_text().splitlines()if len(parts:=line.split())==3}
 raw=subprocess.check_output(['docker','ps','--no-trunc','--format','{"ID":{{json .ID}},"Names":{{json .Names}},"State":{{json .State}},"Labels":{{json .Labels}}}','--filter','label=io.harbor.remote-docker.identity'],text=True,timeout=12)
 docs=[]
 for line in raw.splitlines():
  item=json.loads(line);labels=dict(part.split('=',1)for part in item.get('Labels','').split(',')if'='in part)
  docs.append(dict(Id=item['ID'],Name=item['Names'],State=dict(Status=item['State']),Config=dict(Labels=labels)))
 def inspect(d):
  labels=d['Config'].get('Labels')or{};project=labels.get('com.docker.compose.project','');row=dict(container_id=d['Id'],project=project,identity=labels.get('io.harbor.remote-docker.identity'),name=d['Name'],state=d['State']['Status'])
  if not project.startswith(KNOWN+FUTURE_SCOPE):return dict(**row,status='OUTSIDE_PROJECT_SCOPE_NOT_ENTERED')
  if not in_scope(project,row['identity']):return dict(**row,status='UNKNOWN',error='Campaign project and native identity labels disagree')
  if project.startswith(NOP):return dict(**row,status='DECLARED_NO_MODEL_PREFLIGHT_LANE',active_cli_leases=[])
  try:
   p=subprocess.run(['docker','exec','-u','root','-w','/',d['Id'],'/harbor/agent-runtime/harbor-open-harness-venv/bin/python','-c',PROBE],capture_output=True,text=True,timeout=20)
   if p.returncode:return dict(**row,status='UNKNOWN',error='Read-only docker exec probe failed with returncode '+str(p.returncode),returncode=p.returncode,stdout=p.stdout,stderr=p.stderr)
   value=json.loads(p.stdout);return dict(**row,status='UNKNOWN'if value['errors']else'OBSERVED',**value)
  except Exception as error:return dict(**row,status='UNKNOWN',error=repr(error),returncode=getattr(error,'returncode',None),stdout=(getattr(error,'stdout',None)or b'').decode(errors='replace')if isinstance(getattr(error,'stdout',None),bytes)else(getattr(error,'stdout',None)or''),stderr=(getattr(error,'stderr',None)or b'').decode(errors='replace')if isinstance(getattr(error,'stderr',None),bytes)else(getattr(error,'stderr',None)or''))
 with concurrent.futures.ThreadPoolExecutor(max_workers=4)as pool:rows=list(pool.map(inspect,docs))
 value=summarize(rows,binding,start_wall,start_boot,namespace,offsets,source_sha256 or hashlib.sha256(Path(__file__).read_bytes()).hexdigest());value['seconds']=time.monotonic()-start
 if stdout_only:print(json.dumps(value));return
 destination=Path(output_root)/datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ');destination.mkdir(parents=True,exist_ok=False)
 proof=destination/'ACTUAL_CLI_CAMPAIGN_IDENTITY_R8.json';proof.write_text(json.dumps(value,indent=2)+'\n')
 print(json.dumps(dict(path=str(proof),sha256=hashlib.sha256(proof.read_bytes()).hexdigest(),complete=value['complete'],active_cli=value['actual_active_cli_count'],seconds=value['seconds'])))

if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('--output-root',default='/home/chenkeyi/.local/share/harbor-rsi/qwen35-new772-tb21-20261101/checks/active-recorder-evidence-r8');parser.add_argument('--stdout',action='store_true');parser.add_argument('--source-sha256');parser.add_argument('--bindings-json',required=True);parser.add_argument('--bindings-sha256',required=True);args=parser.parse_args()
 binding=json.loads(args.bindings_json);assert canonical_sha(binding)==args.bindings_sha256
 main(args.output_root,args.stdout,args.source_sha256,binding)
