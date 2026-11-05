"""Read-only collection/data observer appended to the existing 20-minute timer."""
from collections import Counter
import datetime
import hashlib
import json
import csv
import io
from logging import Formatter, getLogger
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import subprocess
import shlex
from pydantic_core import from_json


def parse_metadata_json(payload):
    """Use the already installed native JSON parser for health metadata."""
    return from_json(payload, cache_strings=False)

ROOT = Path('/home/chenkeyi/.local/share/harbor-rsi/qwen35-new-cf500-tmax500-20261029')


def protocol_report_metadata(path):
    """Read fixed root metadata from the native writer's indented JSON.

    Trial rows are large and are audited separately. This observer needs only
    the first root timestamp and the final root cache counters. One descriptor
    retains a coherent old or new file when the producer atomically replaces it.
    """
    if not path.exists():return {}
    with path.open('rb') as stream:
        head=stream.read(2048)
        stream.seek(0,2);size=stream.tell();stream.seek(max(0,size-8192))
        tail=stream.read(8192)
    decoder=json.JSONDecoder()
    marker=b'\n  "checked_at": '
    if marker not in head:raise ValueError('Protocol root timestamp not observed')
    timestamp,_=decoder.raw_decode(head.split(marker,1)[1].splitlines()[0].decode())
    marker=b'\n  "terminal_protocol_cache": '
    cache=None
    if marker in tail:
        payload=tail.rsplit(marker,1)[1].decode()
        cache,end=decoder.raw_decode(payload)
        if payload[end:].strip()!='}' or not isinstance(cache,dict):
            raise ValueError('Protocol final root cache counters are malformed')
    return dict(checked_at=timestamp,terminal_protocol_cache=cache)


def first_environment_outcome(paths):
    """Keep the original first-positive precedence with one read per path."""
    first=None
    for path in paths:
        if not path.exists():continue
        doc=parse_metadata_json(path.read_text())
        if first is None:first=(path,doc)
        if doc['status']=='ENV_READY':return path,doc
    return first if first is not None else (paths[0],None)


def finite_environment_failures(root):
    """Show completed current17 failures instead of stale preparation-pending rows.

    Positive Ready receipts keep their existing precedence. Administrative
    skips and live preparation never become a terminal environment failure.
    """
    scopes={
        'direct17-native-source-r17':'prepare_unstarted_direct17_r17.py',
        'native-transport-recheck17-r20':'recheck_native_transport_failures17_r20.py',
        'native-verifier-timeout-recheck17-r24':'recheck_native_verifier_timeouts17_r24.py',
        'native-exact-archive-recheck17-r29':'recheck_exact_original_archives17_r29.py',
        'native-setup-recheck17-r32':'recheck_native_setup17_r32.py',
        'native-exact-archive-recheck17-r34':'recheck_exact_original_archives17_r34.py',
        'native-exact-archive-recheck17-r43':'recheck_exact_original_archives17_r43.py',
        'unaccepted-original-archive-native17-r56':'accept_unaccepted_original_archives17_r56.py',
        'original-initial-failure-build17-r58':'prepare_original_initial_failures17_r58.py',
        'public-dependency-native17-r63':'accept_public_dependencies17_r63.py',
        'original-runtime-process-native17-r71':'accept_original_runtime_processes17_r71.py',
        'original-report-startup-native17-r78':'accept_original_report_startup17_r78.py',
        'existing-original-archive-variant17-r94':'accept_existing_original_archive_variant17_r94.py',
        'original-process-format-native17-r106':'accept_original_process_format17_r106.py',
        'original-process-format-native17-r109':'accept_original_process_format17_r109.py',
    }
    failures={}
    for scope,worker in scopes.items():
        directory=root/'stream'/scope;plan=directory/'PLAN.json'
        if not plan.exists():continue
        contract=parse_metadata_json(plan.read_text())
        if contract['engine_id']!='59c8ba22-0aa4-4aed-bc43-4e1b5989fa22' or contract['model_calls']!=0:
            raise ValueError('Finite environment report belongs to another runtime')
        if hashlib.sha256((root/'scripts'/worker).read_bytes()).hexdigest()!=contract['source_sha256']:
            raise ValueError('Frozen finite environment worker changed')
        for path in (directory/'environment-outcomes').glob('*.json'):
            doc=parse_metadata_json(path.read_text())
            if doc['task_id']!=path.stem:raise ValueError('Finite environment Task identity differs')
            if doc['status']!='ENV_FAILED':continue
            ident=doc['task_id'];prior=failures.get(ident)
            if prior is None or (path.stat().st_mtime_ns,str(path))>(prior[0].stat().st_mtime_ns,str(prior[0])):
                failures[ident]=(path,doc)
    return failures


def observed_selection(attempts):
    """Reuse an exactly validated immutable native sampling snapshot.

    Every source/binding/evidence hash remains checked. New source changes use
    the strict resolver until a fresh equivalent snapshot is registered.
    """
    file=ROOT/'checks/monitor-active-selection-cache-r6.json'
    if file.exists():
        cache=parse_metadata_json(file.read_text())
        valid=all(Path(name).is_file() and hashlib.sha256(Path(name).read_bytes()).hexdigest()==digest for name,digest in cache['input_sha256'].items())
        snapshot=Path(cache['selection_snapshot'])
        if valid and hashlib.sha256(snapshot.read_bytes()).hexdigest()==cache['selection_snapshot_sha256']:
            rows=parse_metadata_json(snapshot.read_text())
            if len(rows)!=1000 or len({x['task_id'] for x in rows})!=1000 or Counter(x['pool'] for x in rows)!={'calibforge':500,'tmax':500}:
                raise ValueError('Validated native sampling snapshot has changed scope')
            if not set(attempts)<={x['task_id'] for x in rows} or any(attempts.get(x,0) for x in cache['replaced_original_task_ids']):
                raise ValueError('Observed attempts no longer match the validated sampling binding')
            return rows
    from collection_selection_r4 import active_rows
    return active_rows(attempts)


def teacher_slot_telemetry(controller):
    path=ROOT/'stream/collection-r4/teacher-lifecycle.jsonl'
    records=[]
    if path.exists():
        lines=path.read_text().splitlines()
        for i,line in enumerate(lines):
            try:records.append(parse_metadata_json(line))
            except ValueError:
                if i!=len(lines)-1:raise
    active={};waiting={};ends=[];backfills=[];maximum=0;slot_empty_since={n:None for n in range(1,9)}
    occupied={}
    for row in records:
        name=row['trial_name']
        if row['event']=='SETUP_READY_WAITING_FOR_TEACHER_SLOT':waiting[name]=row
        elif row['event']=='TEACHER_ADMITTED':
            waiting.pop(name,None);active[name]=row;maximum=max(maximum,len(active))
            free=next(n for n in range(1,9) if n not in occupied.values())
            occupied[name]=free;slot_empty_since[free]=None
            if ends:
                previous=ends.pop(0)
                gap=(datetime.datetime.fromisoformat(row['agent_admitted_at'])-datetime.datetime.fromisoformat(previous['observed_at'])).total_seconds()
                backfills.append(dict(completed_trial=previous['trial_name'],replacement_trial=name,
                    completed_at=previous['observed_at'],replacement_agent_admitted_at=row['agent_admitted_at'],gap_seconds=gap))
        elif row['event'] in ['TEACHER_AGENT_ENDED','TEACHER_FINALIZED']:
            if name not in active:continue
            active.pop(name,None);ends.append(row)
            slot=occupied.pop(name,None)
            if slot is not None:slot_empty_since[slot]=row['observed_at']
    waiting={name:row for name,row in waiting.items() if not (ROOT/'stream/collection-r4/trials'/name/'result.json').exists()}
    observed=datetime.datetime.now(datetime.timezone.utc)
    vacancies=[dict(slot=n,empty_since=since,empty_seconds=(observed-datetime.datetime.fromisoformat(since)).total_seconds() if since else None)
        for n,since in slot_empty_since.items() if n not in occupied.values()]
    return dict(native_admitted_agent_phase_trials=len(active),maximum_observed_native_agent_permits=maximum,
        installed_waiting_for_teacher_slot=len(waiting),resident_image_buffer=controller.get('ready_buffer'),
        setup_or_gate_waiting=controller.get('teacher_setup_or_gate_waiting'),
        last_teacher_dispatch_at=controller.get('last_teacher_dispatch_at'),
        empty_slots=controller.get('empty_teacher_slots',[]),completion_to_replacement=backfills,
        empty_slot_duration=vacancies,slot_numbers_are_observer_accounting_only=True,
        completed_backfill_cycles=len(backfills),all_recorded_counts_at_most_eight=maximum<=8,
        source=str(path),installation_and_nop_do_not_count_as_teachers=True)


def live_teacher_model_evidence(controller):
    native=controller.get('actual_teacher_trials',0)
    if native==0:return dict(status='NO_NATIVE_AGENT_PHASES',native_agent_phases=0,model_evidenced_slots=0)
    try:
        import sys
        reply=subprocess.run([sys.executable,str(ROOT/'scripts/capture_active_teacher_phases149_r322.py')],capture_output=True,text=True,timeout=20)
        if reply.returncode:raise ValueError('Read-only slot sampler did not complete')
        summary=parse_metadata_json(reply.stdout);path=Path(summary['proof']);proof=parse_metadata_json(path.read_text())
        stable=proof['stable_actual_active_trial_names_through_all_probes']
        evidenced=[row for row in proof['rows'] if row.get('recorder_metadata',{}).get('sampled_provider_event_count',0)>0 and row.get('agent_phase_metadata',{}).get('agent_execution_active') is True and not row['native_result_present']]
        unknown=[];observed=datetime.datetime.now(datetime.timezone.utc)
        for row in proof['rows']:
            if row in evidenced:continue
            unknown.append(dict(trial_name=row['trial_name'],task_id=row['task_id'],native_admitted_at=row['agent_admitted_at'],
                seconds_since_native_admission=(observed-datetime.datetime.fromisoformat(row['agent_admitted_at'])).total_seconds(),
                recorder_exists=row.get('recorder_metadata',{}).get('recorder_exists'),
                completed_cli_wait_seconds=row.get('agent_phase_metadata',{}).get('completed_cli_wait_seconds'),
                reason='CLI_COMPLETED_NATIVE_COMPLETION_CONFIRMATION_PENDING' if row.get('agent_phase_metadata',{}).get('completion_marker_present') else 'CLI_STARTUP_OR_FIRST_PROVIDER_EVENT_NOT_YET_OBSERVED' if row.get('probe_returncode')==0 else 'READ_ONLY_OBSERVATION_INCOMPLETE',agent_phase_metadata=row.get('agent_phase_metadata')))
        return dict(status='STABLE_LIVE_MODEL_EVIDENCE' if stable else 'ACTIVE_SET_CHANGED_DURING_PROBE',
            native_agent_phases=native,model_evidenced_slots=len(evidenced) if stable else None,
            all_eight_verified=proof['all_eight_current_have_provider_events'],unverified_slots=unknown,
            evidence=str(path),evidence_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),checked_at=proof['checked_at'],
            missing_or_incomplete_evidence_is_not_counted_as_eight_models=True)
    except (OSError,ValueError,KeyError,subprocess.SubprocessError) as error:
        return dict(status='READ_ONLY_MODEL_SLOT_PROBE_INCOMPLETE',native_agent_phases=native,model_evidenced_slots=None,
            all_eight_verified=False,error_type=type(error).__name__,teacher_dispatch_or_cancel_actions=0)


def student_progress():
    code = '''from pathlib import Path
import json
r=Path("/home/chenkeyi/workspace/RSI/runtime-evidence/qwen35-new-cf500-tmax500-20261029")
report={}
for label,base in [("initial",r),("original-environment",r/"validation/original-env-20261030"),("original-environment-final2",r/"validation/original-env-final2-20261030"),("legal-cf-zero",r/"validation/original-env-cf-zero-20261030")]:
 for name in ["canary-qwen-projection-all-v4", "canary-native-loader-all-v4", "canary-native-serving-parsers-all-v4", "DATA_AUDIT"]:
  p=base/"checks"/(name+".json")
  if not p.exists():continue
  x=json.loads(p.read_text());key=label+"/"+name
  if isinstance(x,list):report[key]=dict(trials=len(x),original_decisions=sum(v.get("calls",0) for v in x),projected_decisions=sum(v.get("projected",0) for v in x),quarantined_decisions=sum(len(v.get("errors",[])) for v in x))
  else:report[key]={k:x[k] for k in ["passed","status","targets","cuda_initialized"] if k in x}
for pool in ["calibforge","tmax"]:
 base=r/"staging/canary-qualified-r2"/pool
 p=base/"DATA_MANIFEST.json";a=base/"NATIVE_CACHE_AUDIT.json"
 if p.exists():
  x=json.loads(p.read_text());report["staging-qualified/"+pool]=dict(qualified_tasks=x["qualified_independent_tasks"],native_cache_audit_passed=json.loads(a.read_text())["passed"] if a.exists() else None,release=False)
archives=Path("/ssd/chenkeyi/qwen35-new-cf500-tmax500-20261029/registry/tasks-local-skopeo-r1")
selected={x["task_id"]:x["source"]["pinned"] for x in json.loads((r/"manifests/CF_PUBLIC_OCI_REMOTE17_R5.json").read_text())["tasks"]}
staged={}
for directory in [archives,archives.parent/"tasks"]:
 for p in directory.glob("*/cache.json"):
  x=json.loads(p.read_text());ident=x.get("task_id")
  if ident not in selected or x.get("status")!="PINNED_PUBLIC_IMAGE_ARCHIVE_READY":continue
  if x["pinned"]!=selected[ident]:raise ValueError("Frozen public archive source differs")
  if Path(x["archive"]).is_file():staged[ident]=x["pinned"]
report["public-oci-staged-on-17"]=dict(ready_archives=len(staged),unique_selected_tasks=len(staged),planned_unique_tasks=500,scope="Union of original and new immutable cache receipts; no double counting",model_calls=0)
size=r/"checks/cf-cold-sizes-r1.json"
if size.exists():
 x=json.loads(size.read_text());report["cf500-exact-cold-size-audit"]={k:x[k] for k in ["status","checked_at","planned_tasks","observed_tasks","counts","model_calls"] if k in x}
import subprocess,os,pwd
worker=r/"checks/cf-public17-r5-full.json"
if worker.exists():
 x=json.loads(worker.read_text());items=x.get("records",[])
 report["cf-public-ssd17-worker-r5"]={k:x[k] for k in ["status","pid","checked_at","planned_tasks","observed_tasks"] if k in x}
 report["cf-public-ssd17-worker-r5"].update(actual_pid_alive=Path("/proc/"+str(x.get("pid",0))).exists(),counts=dict(__import__("collections").Counter(v.get("status","UNKNOWN") for v in items)),model_calls=0)
backup=r/"checks/cf-public17-preserve149-r6-full.json"
if backup.exists():
 x=json.loads(backup.read_text());report["cf-public-ssd17-preserve149-r6"]={k:x[k] for k in ["status","pid","checked_at","planned_tasks","observed_tasks","counts"] if k in x}
docker=subprocess.run(["docker","inspect","rsi-cftmax-buildkit-rootless-r2"],capture_output=True,text=True,timeout=3)
if docker.returncode==0:
 x=json.loads(docker.stdout)[0]
 report["tmax-ssd17-native-builder-r2"]=dict(running=x["State"]["Running"],image=x["Image"],privileged=x["HostConfig"]["Privileged"],device_requests=x["HostConfig"].get("DeviceRequests"),mounts=[{k:m[k] for k in ["Source","Destination"]} for m in x["Mounts"]],model_calls=0)
disk=os.statvfs("/ssd/chenkeyi/qwen35-new-cf500-tmax500-20261029")
report["ssd17-capacity"]=dict(available_bytes=disk.f_bavail*disk.f_frsize)
target_processes=[]
for p in Path("/proc").iterdir():
 if not p.name.isdigit():continue
 try:
  args=[x for x in (p/"cmdline").read_bytes().decode(errors="replace").split("\\0") if x]
  if any(str(r/"scripts"/name) in args for name in ["audit_stream_data_17.py","audit_stream_canonical17_r163.py","audit_stream_nfc_canonical17_r366.py"]):target_processes.append(dict(pid=int(p.name),trial_id=args[-1]))
 except OSError:pass
audit_root=r/"validation/stream-r3"
report["actual-student-target-cpu-audits"]=dict(checked_at=__import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),processes=target_processes,actual_active=len(target_processes),configured_max=2,cache_root=str(audit_root.resolve()),completed_proof_files=len(list(audit_root.glob("*/checks/STUDENT_AUDIT_TRIALS_ALL.json"))))
canonical_base=Path("/ssd/chenkeyi/qwen35-new-cf500-tmax500-20261029")
for label in ["training","serving"]:
 p=canonical_base/"data-canonical-primary-r161"/label/"PROGRESS.json"
 if p.exists():report["canonical-student-backend-r161-"+label]=json.loads(p.read_text())
for label in ["training","serving"]:
 p=canonical_base/"data-canonical-primary-r240"/label/"PROGRESS.json"
 if p.exists():report["canonical-student-gap-r240-"+label]=json.loads(p.read_text())
for name,relative in [("canonical-combined-cache-r242","data-combined-audit-r242/state.json"),("canonical-primary-cache-progress-r238","data-primary-snapshots/r238/progress.json")]:
 p=canonical_base/relative
 if p.exists():report[name]=json.loads(p.read_text())
for name,relative in [("student-tokenizer-checkpoint-serving-r255","student-protocol-r255/TOKENIZER_CHECKPOINT_SERVING_ACCEPTANCE.json"),("student-policy-configs-r256","student-protocol-r256/STUDENT_DATA_AND_SERVING_POLICY_LOCK_R256.json"),("student-runtime-candidate-r257","student-protocol-r257/STUDENT_RUNTIME_WIRING_ACCEPTANCE.json"),("public-python-prewarm-r263","public-python-prewarm-r263/state.json"),("public-python-original-cache-r265","staging-private-engine17-r1/public-python-origin-cache-r265/state.json"),("public-cli-native-provider-r269","provider-public-cache-r268/BUILD_ACCEPTANCE_R269.json")]:
 p=canonical_base/relative
 if p.exists():
  item=json.loads(p.read_text())
  report[name]={k:item[k] for k in ["passed","status","stage","checked_at","pid","version","python","source_uv_sha256","canonical_backend_semantics_sha256","training_started","model_or_optimizer_loaded","cuda_initialized","scope"] if k in item}
  if name=="public-python-prewarm-r263":report[name]["actual_pid_exists"]=Path("/proc/"+str(item.get("pid",0))).exists()
p=canonical_base/"controller17-r1/bootstrap/RUNTIME_INSTALL_ACCEPTANCE_R160.json"
if p.exists():report["controller17-runtime-preparation-r160"]=json.loads(p.read_text())
p=canonical_base/"data-tokenizer-revalidation-r159/ddc3d97b-cd36-44c5-b911-28451892baeb/checks/TOKENIZER_FULL_TRIAL_ACCEPTANCE_R159.json"
if p.exists():report["canonical-student-full-trial-r159"]=json.loads(p.read_text())
registry=r/"checks/tmax-original-registry-recovery-r9.json"
if registry.exists():
 x=json.loads(registry.read_text());report["original-tmax-registry-recovery-r9"]=x
 report["original-tmax-registry-recovery-r9"]["actual_pid_alive"]=Path("/proc/"+str(x.get("pid",0))).exists()
registry_plan=r/"manifests/TMAX_ORIGINAL_REGISTRY_EOF_RECOVERY_R9.json"
if registry_plan.exists():report["registry_recovery_manifest"]=json.loads(registry_plan.read_text())
network=r/"checks/tmax-original-network-recovery-r10.json"
if network.exists():
 x=json.loads(network.read_text());report["original-tmax-network-recovery-r10"]=x
 report["original-tmax-network-recovery-r10"]["actual_pid_alive"]=Path("/proc/"+str(x.get("pid",0))).exists()
private_engine=Path("/ssd/chenkeyi/qwen35-new-cf500-tmax500-20261029/engine17-r1/ENGINE_READY_R3.json")
if private_engine.exists():report["private-ssd-engine17-r3"]=json.loads(private_engine.read_text())
candidate=Path("/ssd/chenkeyi/qwen35-new-cf500-tmax500-20261029/cf-verifier-public-dependency-r36/state.json")
if candidate.exists():report["public-verifier-dependency-build-candidates-r36"]=json.loads(candidate.read_text())
basic=r/"checks/cf-basic-ssd17-r6-full.json"
if basic.exists():
 x=json.loads(basic.read_text());report["cf-original-basic-ssd17-r6"]={k:x[k] for k in ["status","pid","checked_at","planned_tasks","observed_tasks","remaining_tasks","counts","docker_root_free_bytes"] if k in x}
 report["cf-original-basic-ssd17-r6"]["actual_pid_alive"]=Path("/proc/"+str(x.get("pid",0))).exists()
report["native_cf17_basic_receipts"]=[json.loads(p.read_text()) for p in (r/"checks/cf-environments-ssd17-r6").glob("*.json")]
report["native_cf17_recheck_receipts"]=[json.loads(p.read_text()) for p in (r/"checks/cf-environments-ssd17-recheck-r7").glob("*.json")]
report["native_tmax17_initial_receipts"]=[json.loads(p.read_text()) for p in (r/"checks/tmax-environments-ssd17-r7").glob("*.json")]
initial=r/"checks/tmax-initial-ssd17-r7.json"
if initial.exists():
 x=json.loads(initial.read_text());report["tmax-original-initial-ssd17-r7"]={k:x[k] for k in ["status","pid","checked_at","planned_tasks","observed_tasks","remaining_tasks","counts","docker_root_free_bytes"] if k in x}
 report["tmax-original-initial-ssd17-r7"]["actual_pid_alive"]=Path("/proc/"+str(x.get("pid",0))).exists()
recovery=Path("/ssd/chenkeyi/qwen35-new-cf500-tmax500-20261029/buildkit-rootless-r2/archives/task_009921_1b294fdc/network-recovery-r5")
if (recovery/"PLAN.json").exists():
 x=json.loads((recovery/"build.json").read_text()) if (recovery/"build.json").exists() else {}
 report["tmax-original-apt502-recovery-r5"]={k:x[k] for k in ["status","checked_at","seconds","archive_bytes","native_manifest_digest"] if k in x}
 report["tmax-original-apt502-recovery-r5"].update(model_calls=0,original_task_modifications=0,build_log_bytes=(recovery/"build.log").stat().st_size if (recovery/"build.log").exists() else 0)
mirror=r/"checks/tmax-original-mirror403-build-r7.json"
if mirror.exists():
 x=json.loads(mirror.read_text());report["tmax-original-mirror403-build-r7"]={k:x[k] for k in ["status","pid","checked_at","planned_tasks","observed_tasks","current_task_id","records","model_calls"] if k in x}
 report["tmax-original-mirror403-build-r7"]["actual_pid_alive"]=Path("/proc/"+str(x.get("pid",0))).exists()
receipts=report["native_cf17_basic_receipts"]
if receipts:
 processes=[]
 for process in Path("/proc").iterdir():
  if not process.name.isdigit():continue
  try:
   if process.stat().st_uid!=os.getuid():continue
   arguments=(process/"cmdline").read_bytes().split(b"\\0")
   if str(r/"scripts/prepare_cf_original_basic_ssd17_r6.py").encode() in arguments:processes.append(int(process.name))
  except (OSError,ValueError):continue
 report["cf-original-basic-ssd17-r6-actual-progress"]=dict(observed_tasks=len(receipts),counts=dict(__import__("collections").Counter(x["status"] for x in receipts)),last_task_checked_at=max(x["checked_at"] for x in receipts),actual_worker_pids=processes,native_cli_and_verifier_pending=True)
allowed={"GPU-bb31693b-95f6-4416-ec41-dd75511c2c59","GPU-0db8aea7-b003-06fb-d197-d047c1d67bcb","GPU-d2499600-e80e-4fb8-40ef-b6f0f919d2d8","GPU-00f3c3df-16e0-f31f-4066-bdee4c8cdff2"}
gpu=subprocess.run(["nvidia-smi","--query-gpu=uuid,index,memory.used,memory.total,utilization.gpu","--format=csv,noheader,nounits"],capture_output=True,text=True,timeout=2)
processes=subprocess.run(["nvidia-smi","--query-compute-apps=gpu_uuid,pid,process_name,used_memory","--format=csv,noheader,nounits"],capture_output=True,text=True,timeout=2)
report["authorized-gpu-inventory"]={"gpu_rows":[line for line in gpu.stdout.splitlines() if line.split(",")[0].strip() in allowed],"processes":[],"query_returncode":gpu.returncode}
for line in processes.stdout.splitlines():
 fields=[v.strip() for v in line.split(",")]
 if fields[0] not in allowed:continue
 try:owner=pwd.getpwuid(Path("/proc/"+fields[1]).stat().st_uid).pw_name
 except (OSError,KeyError):owner="UNOBSERVED"
 report["authorized-gpu-inventory"]["processes"].append(dict(gpu_uuid=fields[0],pid=fields[1],process_name=fields[2],used_memory_mib=fields[3],owner=owner))
print(json.dumps(report))'''
    try:
        reply = subprocess.run(['ssh', '-S', '/home/chenkeyi/.ssh/cf17-20261028.sock',
            '-oBatchMode=yes', '-oProxyCommand=false', 'chenkeyi@180.163.192.17',
            'python3 -c ' + shlex.quote(code)], capture_output=True, text=True, timeout=15)
        if reply.returncode:
            return dict(status='REMOTE_STUDENT_STATUS_UNOBSERVED', returncode=reply.returncode)
        report=parse_metadata_json(reply.stdout)
        if 'registry_recovery_manifest' in report:
            item=report.pop('registry_recovery_manifest');target=ROOT/'manifests/TMAX_ORIGINAL_REGISTRY_EOF_RECOVERY_R9.json'
            if target.exists():
                if parse_metadata_json(target.read_text())!=item:raise ValueError('Immutable registry recovery plan changed')
            else:target.write_text(json.dumps(item,indent=2))
        for key,name in [('native_cf17_basic_receipts','cf-environments-ssd17-r6'),('native_cf17_recheck_receipts','cf-environments-ssd17-recheck-r7'),('native_tmax17_initial_receipts','tmax-environments-ssd17-r7')]:
            destination=ROOT/'checks'/name
            destination.mkdir(exist_ok=True)
            for item in report.pop(key,[]):
                target=destination/(item['task_id']+'.json')
                if target.exists():
                    if parse_metadata_json(target.read_text())!=item:raise ValueError('Immutable17 preparation receipt changed')
                else:target.write_text(json.dumps(item,indent=2))
        return dict(status='OBSERVED_READ_ONLY', checks=report)
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        return dict(status='REMOTE_STUDENT_STATUS_UNOBSERVED', error_type=type(error).__name__)


def main():
    trials = []
    job_scopes = {}
    job_progress = []
    configured_teacher_attempts=Counter()
    for config in sorted((ROOT/'jobs').glob('*/config.json')):
        settings=parse_metadata_json(config.read_text());job=config.parent
        names=[agent.get('name') for agent in settings.get('agents',[])]
        if not settings.get('install_only') and 'open-harness' in names:
            if settings.get('n_attempts',1)!=1 or settings.get('retry',{}).get('max_retries',0)!=0:
                raise ValueError('Unexpected legacy teacher repetition in observation')
            configured_teacher_attempts.update(Path(t['path']).name for t in settings['tasks'])
        scope=('install_only_diagnostic' if settings.get('install_only') else
            'verifier_diagnostic' if names and all(name in ('nop','oracle') for name in names) else 'teacher')
        job_scopes[job]=scope
        file=job/'result.json';result=parse_metadata_json(file.read_text()) if file.exists() else {}
        stats=result.get('stats',{})
        job_progress.append(dict(job_name=job.name,scope=scope,requested_attempts=len(settings.get('tasks',[]))*settings.get('n_attempts',1),
            finished_at=result.get('finished_at'),native_stats={k:v for k,v in stats.items() if k in
                ['n_completed_trials','n_errored_trials','n_running_trials','n_pending_trials','n_cancelled_trials']}))
    for file in sorted((ROOT / 'jobs').glob('*/*/result.json')):
        data = parse_metadata_json(file.read_text())
        job = file.parents[1]
        trials.append(dict(trial_id=data.get('id'), task_id=data.get('task_name'), result_path=str(file),
            scope=job_scopes.get(job,'UNKNOWN_NO_NATIVE_JOB_CONFIG'),
            reward=(data.get('verifier_result') or {}).get('rewards'),
            exception=(data.get('exception_info') or {}).get('exception_type')))
    stream_dispatches = []
    for file in ROOT.glob('stream/collection-r[234]/dispatches/*/dispatch.json'):
        item = parse_metadata_json(file.read_text())
        stream_dispatches.append(item)
        result = file.parents[2]/'trials'/item['trial_name']/'result.json'
        if result.exists():
            data=parse_metadata_json(result.read_text())
            trials.append(dict(trial_id=data.get('id'),task_id=item['task_id'],result_path=str(result),
                scope='teacher' if item['kind']=='teacher' else item['kind']+'_diagnostic',
                reward=(data.get('verifier_result') or {}).get('rewards'),
                exception=(data.get('exception_info') or {}).get('exception_type')))
    own_processes = []
    script_paths={str(p):p.name for p in (ROOT/'scripts').glob('*.py')}
    config_prefix=str(ROOT/'configs')+'/'
    build_prefix=str(ROOT/'build-contexts')+'/'
    for entry in Path('/proc').iterdir():
        if not entry.name.isdigit():
            continue
        try:
            if entry.stat().st_uid != os.getuid():
                continue
            arguments = (entry / 'cmdline').read_bytes().decode(errors='replace').split('\0')
            script = next((script_paths[arg] for arg in arguments if arg in script_paths), None)
            if script is None and any(arg.startswith(config_prefix) for arg in arguments):
                script = 'native_harbor:' + next(Path(arg).name for arg in arguments if arg.startswith(config_prefix))
            if script is None and any(arg.startswith(build_prefix) for arg in arguments):
                script = 'docker_image_build'
            if script is None or int(entry.name) == os.getpid():
                continue
            # Only report identity, never command arguments or environment values.
            own_processes.append(dict(pid=int(entry.name), script=script))
        except (OSError, ValueError):
            continue
    checks = {}
    for name in ['native-tmax-resident-archive-r1','capacity-held-cf-image-eviction-r1','stream-r4-data-audit-worker','collection-r4-promotion-ready','tmax-remaining-ssd17-r3','public-asset-worker-149-to17-handoff-r5','tmax-missing-receipt-recovery-r7','stream-r3-data-audit-worker','stream-r3-live-container-payloads','cf-original-resources-pool-preparation','cf-public-oci-remote149-r4','public-source-inventory', 'offline-teacher-contract', 'summary-r1-offline-teacher-contract', 'cf-image-preparation', 'cf-image-preparation-v2', 'tmax-image-preparation', 'tmax-image-preparation-v2', 'tmax-original-runtime-pool-preparation', 'tmax-preparation-v2', 'environment-preflight', 'canary-audit', 'collection-qualification', 'scoped-ssh-client2-native-install8', 'CANARY_GATE', 'cf-public-oci-native-import-proof', 'cf-public-oci-prefetch', 'cf-image-preparation-oci-r4', 'cf-image-preparation-oci-r5']:
        file = ROOT / 'checks' / (name + '.json')
        if file.exists():
            value = parse_metadata_json(file.read_text())
            checks[name] = {k: value[k] for k in ['passed', 'status', 'counts', 'pools', 'created_at', 'checked_at', 'observed_tasks', 'planned_tasks', 'stage', 'current_trial_id', 'active_trial_ids', 'max_concurrent_cpu_audits', 'current_free_bytes', 'original_free_bytes', 'failed_assets', 'unique_canary_tasks_by_pool'] if k in value}
    manifest = ROOT / 'manifests/SAMPLING_MANIFEST.json'
    pool_counts = ({k: v['selected']['unique_tasks'] for k, v in parse_metadata_json(manifest.read_text())['pools'].items()}
                   if manifest.exists() else None)
    disk = os.statvfs(ROOT)
    timer = subprocess.run(['systemctl', '--user', 'show', 'qwen35-tb21-monitor.timer', '-p', 'ActiveState',
        '-p', 'NextElapseUSecMonotonic'], capture_output=True, text=True, timeout=5)
    value = dict(checked_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        campaign=ROOT.name, read_only=True, live_processes=own_processes,
        terminal_trial_inventory_scope='Native Jobs and formal collection-r2/r3/r4 dispatches; finite zero-model environment rechecks remain in their per-Task preparation and worker reports',
        teacher_trial_inventory_scope_unchanged=True,
        finite_environment_recheck_results_preserved=True,
        native_jobs=job_progress,student_audits=student_progress(),
        selected_unique_task_counts=pool_counts, terminal_trials=len(trials),
        terminal_teacher_trials=sum(t['scope']=='teacher' for t in trials),
        terminal_diagnostic_trials=sum(t['scope'].endswith('diagnostic') for t in trials),
        terminal_reward_counts=dict(Counter(json.dumps(t['reward'], sort_keys=True) for t in trials)),
        terminal_exception_counts=dict(Counter(str(t['exception']) for t in trials)),
        terminal_results_are_not_qualified_successes=True, trials=trials,
        checks=checks, disk_available_bytes=disk.f_bavail*disk.f_frsize,
        existing_timer_state=timer.stdout.strip(),
        dispatch_restart_cancel_or_cleanup_actions=0)
    authorities=[ROOT/'checks'/('CURRENT_DISPATCH_AUTHORITY_'+rev+'.json') for rev in ['R22','R21','R20','R19','R17','R16','R15','R14','R13','R12','R11','R10','R9','R8','R7','R6']]
    authority=next((p for p in authorities if p.exists() and Path(parse_metadata_json(p.read_text())['state_path']).exists()),None)
    controller=Path(parse_metadata_json(authority.read_text())['state_path']) if authority else ROOT/'campaign-state.json'
    value['controller']=parse_metadata_json(controller.read_text()) if controller.exists() else {}
    hook=ROOT/'checks/collection-monitor-last-hook-result-r28.json'
    if hook.exists():value['last_completed_collection_monitor_hook']=parse_metadata_json(hook.read_text())
    value['controller']['actual_pid_alive']=Path('/proc/'+str(value['controller'].get('pid',0))).exists()
    if authority:
        authority_doc=parse_metadata_json(authority.read_text())
        expected=str(ROOT/'scripts'/('run_collection_stream_'+authority_doc['controller_revision']+'.py')).encode()
        try:arguments=(Path('/proc')/str(authority_doc['pid'])/'cmdline').read_bytes().split(b'\0')
        except FileNotFoundError:arguments=[]
        value['controller']['process_identity_matches_authority']=expected in arguments
        value['controller']['actual_pid_alive']=value['controller']['actual_pid_alive'] and expected in arguments
    for key,relative in [('pre_agent_setup_recheck_r162','stream/pre-agent-setup-recheck17-r162/state.json'),
                         ('canonical_data_writer_handoff_r165','checks/canonical-data-writer-handoff-r165.json'),
                         ('canonical_data_writer_handoff_wait_r165','checks/canonical-data-writer-handoff-wait-r165.json'),
                         ('data_writer_handoff_r194','checks/data-writer-handoff-r194.json'),
                         ('data_writer_handoff_wait_r194','checks/data-writer-handoff-wait-r194.json'),
                         ('cleaned_network_native_recheck_r184','stream/cleaned-network-scopes-recheck17-r184/state.json'),
                         ('cleaned_terminal_native_recheck_r190','stream/cleaned-terminal-scope-recheck17-r190/state.json'),
                         ('public_setup_diagnostics_r191','stream/public-setup-timeout-diagnostics17-r191/state.json'),
                         ('controller_r17_native_handoff','checks/controller-r17-native-handoff-progress.json'),
                         ('controller_r19_native_handoff','checks/controller-r19-native-handoff-progress.json'),
                         ('controller_r20_native_handoff','checks/controller-r20-native-handoff-progress.json'),
                         ('controller_r21_native_handoff','checks/controller-r21-native-handoff-progress.json'),
                         ('data_writer_handoff_r313','checks/data-writer-handoff-r313.json'),
                         ('data_writer_handoff_wait_r313','checks/data-writer-handoff-wait-r313.json'),
                         ('remaining_verifier_native_r317','stream/signed-debian-native-acceptance17-r317/state.json'),
                         ('remaining_verifier_native_r336','stream/signed-debian-native-acceptance17-r336/state.json'),
                         ('native_setup_recovery_r335','stream/public-cpython-native-setup-recovery17-r335/state.json'),
                         ('native_probe_recovery_r346','stream/public-cpython-native-setup-recovery17-r346/state.json'),
                         ('held_task_release_r342','checks/verifier-dependency-recheck-r342/RELEASE_APPLIED.json'),
                         ('native_ssh_socket_maintenance_r333','checks/native-ssh-stalled-socket-maintenance-r333.json'),
                         ('public_cli_prototype_r274','stream/public-cpython-native-prototype17-r274/state.json'),
                         ('public_cli_recovery_r277','stream/public-cpython-native-setup-recovery17-r277/state.json'),
                         ('public_cli_controller_acceptance_r288','checks/controller-r20-offline-acceptance-r288.json'),
                         ('data_writer_r194_superseded','checks/data-writer-handoff-r194-SUPERSEDED.json'),
                         ('data_writer_handoff_r221','checks/data-writer-handoff-r221.json'),
                         ('remaining_tmax_setup_r212','stream/remaining-tmax-setup-recheck17-r212/state.json'),
                         ('signed_debian_native_r223','stream/signed-debian-native-acceptance17-r223/state.json'),
                         ('workdir_transport_recheck_r228','stream/workdir-transport-recheck17-r228/state.json'),
                         ('cli_install_recheck_r243','stream/cli-install-timeout-recheck17-r243/state.json'),
                         ('reviewed_data_writer_acceptance_r247','checks/reviewed-data-writer-acceptance-r247.json'),
                         ('reviewed_data_writer_handoff_r248','checks/data-writer-handoff-r248.json'),
                         ('reviewed_data_writer_handoff_wait_r248','checks/data-writer-handoff-wait-r248.json')]:
        metadata=ROOT/relative
        if metadata.exists():value[key]=parse_metadata_json(metadata.read_text())
    value['teacher_slot_telemetry']=teacher_slot_telemetry(value['controller'])
    # The native drain is the current admission cause; preserve raw slot labels.
    admission_request=controller.parent/'DRAIN_REQUESTED.json'
    if admission_request.exists():
        request=parse_metadata_json(admission_request.read_text())
        value['native_teacher_admission_gate']=dict(request=request,source=str(admission_request),sha256=hashlib.sha256(admission_request.read_bytes()).hexdigest())
        if request.get('reason')=='AUTHORIZED_TEACHER_SERVICE_HTTP402_INSUFFICIENT_BALANCE':
            last=value['controller'].get('last_teacher_dispatch_at')
            if last and last>request['requested_at']:raise ValueError('Teacher admitted after the native service-failure drain')
            telemetry=value['teacher_slot_telemetry']
            telemetry['source_native_empty_slots']=telemetry['empty_slots']
            telemetry['empty_slots']=[dict(slot=i+1,reason='AUTHORIZED_TEACHER_SERVICE_HTTP402_INSUFFICIENT_BALANCE',evidence=str(admission_request)) for i in range(value['controller']['actual_teacher_trials'],8)]
    # A drained, exited controller has no live in-memory queue or setup buffer.
    drained=controller.parent/'DRAINED.json'
    if drained.exists() and not value['controller']['actual_pid_alive']:
        terminal=parse_metadata_json(drained.read_text())
        if terminal.get('status')!='DRAINED_WITH_NO_ACTIVE_TEACHERS':raise ValueError('Unknown native drain terminal state')
        telemetry=value['teacher_slot_telemetry']
        if telemetry['native_admitted_agent_phase_trials'] or telemetry['installed_waiting_for_teacher_slot']:
            raise ValueError('Drained native terminal state contradicts unfinished teacher events')
        value['native_controller_terminal']=dict(value=terminal,source=str(drained),sha256=hashlib.sha256(drained.read_bytes()).hexdigest())
        telemetry['historical_controller_buffers']=dict(resident_image_buffer=telemetry['resident_image_buffer'],setup_or_gate_waiting=telemetry['setup_or_gate_waiting'],state_checked_at=value['controller']['checked_at'])
        telemetry.update(resident_image_buffer=None,setup_or_gate_waiting=0,live_queue_buffers_present=False,
            resident_images_require_a_fresh_probe_before_readmission=True,controller_terminal_observed=True)
    recovery=ROOT/'stream/public-cpython-native-setup-recovery17-r394/state.json'
    if recovery.exists():value['finite_remaining_environment_recovery_r394']=parse_metadata_json(recovery.read_text())
    value['live_teacher_model_evidence']=live_teacher_model_evidence(value['controller'])
    if authority:
        current_manifest=parse_metadata_json(Path(parse_metadata_json(authority.read_text())['manifest']).read_text())
        current_deployment=parse_metadata_json(Path(current_manifest['deployment_config']).read_text())
        pool_decl=current_deployment.get('native_ssh_pool')
        if pool_decl:
            pool_path=Path(pool_decl['path'])
            if hashlib.sha256(pool_path.read_bytes()).hexdigest()!=pool_decl['sha256']:raise ValueError('Native SSH pool manifest changed')
            pool=parse_metadata_json(pool_path.read_text());live=[];missing=[]
            for master in pool['masters']:
                process=Path('/proc')/str(master['pid'])
                try:valid=Path(master['socket']).exists() and (process/'stat').read_text().rsplit(')',1)[1].split()[19]==master['start_ticks']
                except OSError:valid=False
                (live if valid else missing).append(master['slot'])
            value['native_ssh_connection_pool']=dict(expected=16,verified_live=len(live),missing_slots=missing,
                scope='Native OpenSSH connections only; never Teacher concurrency',automatic_reconnect_or_shared_daemon_changes=0)

    retirement_file=ROOT/'checks/legacy-resident-preparation-admission-fence-r7.json'
    retirement=parse_metadata_json(retirement_file.read_text()) if retirement_file.exists() else None
    retired=set()
    if retirement:
        base=ROOT/'stream/tmax-resident-buffer-preflight-r1'
        if retirement['directory']!=str(base/'dispatches') or hashlib.sha256((base/'PLAN.json').read_bytes()).hexdigest()!=retirement['source_plan_sha256']:
            raise ValueError('Legacy preparation retirement identity changed')
        retired=set(retirement['retired_unstarted_task_ids'])
        value['legacy_preparation_retirement']=dict(retirement,old_process_alive=Path('/proc/'+str(retirement['old_pid'])).exists())
    def administrative_retirement(outcome):
        return bool(retirement and outcome.get('task_id') in retired and outcome.get('error_type')=='PermissionError'
            and retirement['directory']+'/' in outcome.get('reason',''))
    direct_fence_file=ROOT/'checks/direct17-r13-native-admission-fence-r14.json'
    direct_fence=parse_metadata_json(direct_fence_file.read_text()) if direct_fence_file.exists() else None
    direct_wiring_tasks=set()
    if direct_fence:
        for entry in direct_fence['pre_queue_rejections']:
            config=Path(entry['config'])
            if hashlib.sha256(config.read_bytes()).hexdigest()!=entry['config_sha256']:raise ValueError('Original pre-queue rejection configuration changed')
            direct_wiring_tasks.add(Path(parse_metadata_json(config.read_text())['task']['path']).name)
        value['direct17_preparation_admission_correction']=direct_fence
    preparation={}
    cold_fence_file=ROOT/'checks/private17-cold-build-directory-fence-r20.json'
    cold_fence=parse_metadata_json(cold_fence_file.read_text()) if cold_fence_file.exists() else None
    deferred_cold_builds=set(cold_fence['deferred_unbuilt_task_ids']) if cold_fence else set()
    if cold_fence:value['private17_cold_build_admission_fence']=cold_fence
    for name,directory in [('original-cf-native-r5','environment-preflight-r5'),('tmax-source-reserve-r5','tmax-initial-reserve-acceptance-r5'),('original-tmax-network-recovery-r6','tmax-original-network-recovery-r6'),('original-tmax-mirror403-recovery-r7','tmax-original-infra-recovery-r7'),('resident-tmax-buffer-r1','tmax-resident-buffer-preflight-r1'),('private-sidecar-source-reserve-r8','tmax-private-sidecar-reserve-acceptance-r8'),('original-registry-recovery-r9','tmax-original-registry-acceptance-r9'),('original-network-recovery-r10','private17-original-network-acceptance-r10'),('unstarted-original-context-direct17-r13','direct17-native-source-r13'),('unstarted-original-context-native17-r14','direct17-native-source-r14'),('unstarted-original-context-private-engine17-r17','direct17-native-source-r17'),('finite-native-transport-recheck17-r20','native-transport-recheck17-r20'),('finite-original-verifier-timeout-recheck17-r24','native-verifier-timeout-recheck17-r24'),('finite-exact-original-archive-recheck-r29','native-exact-archive-recheck17-r29'),('finite-native-setup-recheck-r32','native-setup-recheck17-r32'),('finite-arrived-exact-archive-recheck-r34','native-exact-archive-recheck17-r34'),('historical-attempted-original-image-retention-r35','historical-attempted-archive-delta-r35'),('public-verifier-dependency-native-candidates-r37','cf-public-dependency-native-candidates-r37'),('finite-arrived-exact-archive-recheck-r43','native-exact-archive-recheck17-r43'),('original-unaccepted-archive-native-r56','unaccepted-original-archive-native17-r56'),('original-initial-failure-context-native-r58','original-initial-failure-build17-r58'),('explicit-public-dependency-native-r63','public-dependency-native17-r63'),('public-pytest-image-native-r69','public-pytest-image-native17-r69'),('original-runtime-process-native-r71','original-runtime-process-native17-r71'),('public-font-image-native-r74','public-font-image-native17-r74'),('original-report-startup-native-r78','original-report-startup-native17-r78'),('existing-original-archive-variant-r94','existing-original-archive-variant17-r94'),('original-process-format-native-r106','original-process-format-native17-r106'),('original-process-format-native-r109','original-process-format-native17-r109')]:
        base=ROOT/'stream'/directory
        file=base/'state.json'
        item=parse_metadata_json(file.read_text()) if file.exists() else {}
        if (base/'PLAN.json').exists():
            plan_raw=(base/'PLAN.json').read_bytes();plan=parse_metadata_json(plan_raw)
            item['plan_sha256']=hashlib.sha256(plan_raw).hexdigest()
            item['planned_tasks']=len(plan['tasks']) if 'tasks' in plan else 1
            outcome_directory='candidate-outcomes' if directory in ['cf-public-dependency-native-candidates-r37','public-pytest-image-native17-r69','public-font-image-native17-r74'] else 'environment-outcomes'
            observed=item.get('records',[]) if directory=='historical-attempted-archive-delta-r35' else [parse_metadata_json(p.read_text()) for p in (base/outcome_directory).glob('*.json')]
            item.update(observed_tasks=len(observed),counts=dict(Counter(x['status'] for x in observed)),
                model_calls=0,teacher_dispatches=0)
            if directory=='tmax-resident-buffer-preflight-r1' and retirement:
                item['raw_historical_counts']=item['counts']
                item['counts']=dict(Counter('ADMINISTRATIVE_PREPARATION_RETIREMENT' if administrative_retirement(x) else x['status'] for x in observed))
            if directory=='direct17-native-source-r13' and direct_fence:
                item['raw_historical_counts']=item['counts']
                classified=[]
                for x in observed:
                    wiring=x['task_id'] in direct_wiring_tasks and x.get('error_type')=='AttributeError' and x.get('reason')=="'str' object has no attribute 'expanduser'"
                    fenced=x.get('error_type')=='PermissionError' and direct_fence['directory']+'/' in x.get('reason','')
                    classified.append('PREPARATION_PATH_WIRING_FAILURE_NO_NATIVE_TRIAL' if wiring else 'ADMINISTRATIVE_NATIVE_ADMISSION_FENCE' if fenced else x['status'])
                item['counts']=dict(Counter(classified))
            if directory in ['direct17-native-source-r13','direct17-native-source-r14'] and cold_fence:
                item.setdefault('raw_historical_counts',dict(Counter(x['status'] for x in observed)))
                administrative={x['task_id'] for x in observed if x['task_id'] in deferred_cold_builds and x.get('error_type')=='KeyError' and x.get('reason')=="'status'" and x.get('native_build_returncode')==1}
                item['administrative_cold_build_handoff_task_ids']=sorted(administrative)
                if administrative:
                    previous=item['counts']
                    corrected=Counter(previous)
                    corrected['ENV_FAILED']-=len(administrative)
                    corrected['ADMINISTRATIVE_COLD_BUILD_HANDOFF']=len(administrative)
                    item['counts']={k:v for k,v in corrected.items() if v}
            if 'pid' in item:
                proc=Path('/proc')/str(item['pid']);item['actual_pid_alive']=proc.exists()
                expected_workers={
                    'direct17-native-source-r17':'prepare_unstarted_direct17_r17.py',
                    'native-transport-recheck17-r20':'recheck_native_transport_failures17_r20.py',
                    'native-verifier-timeout-recheck17-r24':'recheck_native_verifier_timeouts17_r24.py',
                    'native-exact-archive-recheck17-r29':'recheck_exact_original_archives17_r29.py',
                    'native-setup-recheck17-r32':'recheck_native_setup17_r32.py',
                    'native-exact-archive-recheck17-r34':'recheck_exact_original_archives17_r34.py',
                    'native-exact-archive-recheck17-r43':'recheck_exact_original_archives17_r43.py',
        'unaccepted-original-archive-native17-r56':'accept_unaccepted_original_archives17_r56.py',
        'original-initial-failure-build17-r58':'prepare_original_initial_failures17_r58.py',
        'public-dependency-native17-r63':'accept_public_dependencies17_r63.py',
        'original-runtime-process-native17-r71':'accept_original_runtime_processes17_r71.py',
        'original-report-startup-native17-r78':'accept_original_report_startup17_r78.py',
        'existing-original-archive-variant17-r94':'accept_existing_original_archive_variant17_r94.py',
        'original-process-format-native17-r106':'accept_original_process_format17_r106.py',
        'original-process-format-native17-r109':'accept_original_process_format17_r109.py',
                    'historical-attempted-archive-delta-r35':'archive_historical_attempted_delta149_r35.py',
                    'cf-public-dependency-native-candidates-r37':'accept_cf_public_dependency_candidates149_r37.py',
                    'public-pytest-image-native17-r69':'accept_public_pytest_image17_r69.py',
                    'public-font-image-native17-r74':'accept_original_public_image_font17_r74.py',
                }
                if directory in expected_workers:
                    try:arguments=(proc/'cmdline').read_bytes().split(b'\0')
                    except FileNotFoundError:arguments=[]
                    item['actual_pid_matches_registered_source']=str(ROOT/'scripts'/expected_workers[directory]).encode() in arguments
                    item['actual_pid_alive']=item['actual_pid_alive'] and item['actual_pid_matches_registered_source']
            terminal=base/'TERMINAL.json'
            if terminal.exists():item['terminal']=parse_metadata_json(terminal.read_text())
            preparation[name]=item
    value['independent_native_environment_preparation']=preparation
    seed_file=ROOT/'checks/protocol-cache-r23-seed/STARTED.json'
    if seed_file.exists():
        seed=parse_metadata_json(seed_file.read_text())
        expected=str(ROOT/'scripts/audit_native_canary_protocol_r23.py').encode()
        pending=[seed['pid']];actual=[]
        for _ in range(3):
            descendants=[]
            for pid in pending:
                proc=Path('/proc')/str(pid)
                try:
                    args=(proc/'cmdline').read_bytes().split(b'\0')
                    if expected in args and b'--cache-seed' in args:actual.append(pid)
                    descendants.extend(map(int,(proc/'task'/str(pid)/'children').read_text().split()))
                except FileNotFoundError:continue
            pending=descendants
        proofs=list((ROOT/'derived/native-protocol-cache-r23').glob('*/*.json'))
        report=seed_file.parent/'stream-collection-r4-live-protocol.json'
        value['protocol_cache_preparation']=dict(seed,actual_protocol_python_pids=actual,
            immutable_terminal_row_proof_count=len(proofs),
            last_cached_row_at=datetime.datetime.fromtimestamp(max(p.stat().st_mtime for p in proofs),datetime.timezone.utc).isoformat() if proofs else None,
            full_scope_report_present=report.exists(),
            canonical_protocol_source_sha256=hashlib.sha256((ROOT/'scripts/audit_native_canary_protocol.py').read_bytes()).hexdigest(),
            stage='SEED_RUNNING' if actual else 'SEED_COMPLETE_PARITY_PENDING' if report.exists() else 'SEED_TERMINAL_WITHOUT_COMPLETE_REPORT')
        activation=ROOT/'checks/protocol-cache-r23-activation.json'
        if activation.exists():
            promoted=parse_metadata_json(activation.read_text())
            if value['protocol_cache_preparation']['canonical_protocol_source_sha256']!=promoted['canonical_source_sha256']:
                raise ValueError('Activated protocol reader source changed')
            current=ROOT/'checks/stream-collection-r4-live-protocol.json'
            production=protocol_report_metadata(current)
            reused=production.get('terminal_protocol_cache')
            value['protocol_cache_preparation'].update(activation=str(activation),activation_sha256=hashlib.sha256(activation.read_bytes()).hexdigest(),
                production_report_checked_at=production.get('checked_at'),production_cache=reused,
                stage='PRODUCTION_CACHE_REUSE_CONFIRMED' if reused else 'CANONICAL_READER_ACTIVE_PRODUCTION_REPORT_PENDING')
    partial_audit=ROOT/'checks/partial-primary-target-audit-r136/PARTIAL_DATA_TARGET_AUDIT_R136.json'
    if partial_audit.exists():
        summary=parse_metadata_json(partial_audit.read_text())
        value['partial_primary_target_cache_audit']=dict(summary,evidence=str(partial_audit),evidence_sha256=hashlib.sha256(partial_audit.read_bytes()).hexdigest())
    builder_acceptance=ROOT/'checks/private17-buildkit-r16-acceptance.json'
    builder_handoff=ROOT/'checks/direct17-build-preparation-handoff-r17.json'
    if builder_acceptance.exists():
        accepted=parse_metadata_json(builder_acceptance.read_text())
        value['private17_build_service']=dict(accepted=accepted['passed'],engine_id=accepted['builder_engine_id'],
            socket=accepted['deployment']['socket'],rootless_state=accepted['deployment']['rootless_state'],
            log_root=accepted['deployment']['logs_root'],native_run_export_load_run_passed=accepted['native_run_export_load_and_run_passed'],
            acceptance=str(builder_acceptance),acceptance_sha256=hashlib.sha256(builder_acceptance.read_bytes()).hexdigest(),
            benchmark_preparation_switched=builder_handoff.exists())
    if builder_handoff.exists():
        transition=parse_metadata_json(builder_handoff.read_text())
        if transition['builder_acceptance_sha256']!=hashlib.sha256(builder_acceptance.read_bytes()).hexdigest():raise ValueError('Private builder handoff acceptance changed')
        value['private17_build_preparation_handoff']=transition
        for key in ['unstarted-original-context-direct17-r13','unstarted-original-context-native17-r14']:
            if key in preparation:
                item=preparation[key]
                if item.get('pid') in transition['retired_preparer_pids'] and not item.get('actual_pid_alive'):
                    item['historical_last_stage']=item.get('stage')
                    item.update(status='RETIRED_AFTER_CURRENT_NATIVE_WORK_FINISHED',stage='RETIRED_PRIVATE_ENGINE17_PREPARATION_HANDOFF')
    transfer_root=ROOT/'sources/native-cold-image-transfers-r1'
    value['native_image_transfers']=[]
    for p in transfer_root.glob('*'):
        try:info=p.stat()
        except FileNotFoundError:continue  # A completed transfer can be released during observation.
        if info.st_size>1024**2:
            value['native_image_transfers'].append(dict(name=p.name,bytes=info.st_size,
                modified_at=datetime.datetime.fromtimestamp(info.st_mtime,datetime.timezone.utc).isoformat()))
    value['stream_dispatch_counts']=dict(Counter(x['kind'] for x in stream_dispatches))
    value['host_cpu_and_memory']=dict(cpu_count=os.cpu_count(),load_average=os.getloadavg(),
        memory_kib={line.split(':')[0]:int(line.split()[1]) for line in Path('/proc/meminfo').read_text().splitlines() if line.split(':')[0] in ['MemTotal','MemAvailable']})
    # The data writer maintains the complete raw per-call ledgers. Health
    # monitoring records their identities; it does not repeat that full audit.
    ledger_paths=sorted((ROOT/'indexes').glob('*-CALL_COST_TOKEN_LEDGER.jsonl'))
    native_ledger=ROOT/'indexes/NATIVE_TRIAL_COST_TOKEN_LEDGER.jsonl'
    value['api_usage_accounting']=dict(
        scope='Health observation only. Complete per-call token/cost accounting remains in the continuously maintained data ledgers and corpus audit.',
        call_ledgers=[dict(path=str(path),bytes=path.stat().st_size,
            modified_at_ns=path.stat().st_mtime_ns,integrity_sha256_deferred_to_full_data_audit=True) for path in ledger_paths],
        native_trial_ledger=dict(path=str(native_ledger),bytes=native_ledger.stat().st_size,
            sha256=hashlib.sha256(native_ledger.read_bytes()).hexdigest()),
        last_full_raw_call_tally=parse_metadata_json((ROOT/'checks/monitor-last-full-call-usage-tally-r48.json').read_text()),
        last_tally_is_historical_not_current=True,
        live_calls_not_yet_exported='Pending terminal immutable export; not assumed zero cost',
        billing='Native descriptor estimates and raw usage retained; provider invoiced charge unavailable',
        monetary_hard_cap='No separate USD cap verified; user1000-task/2000-attempt cap enforced')
    selected=[]
    for name in ['CALIBFORGE_500_TASKS.jsonl','TMAX_RUNTIME_CANDIDATES_V2.jsonl']:
        selected.extend(map(parse_metadata_json,(ROOT/'manifests'/name).open()))
    if (ROOT/'stream/collection-r4/CAMPAIGN.json').exists():
        configured_teacher_attempts.update(x['task_id'] for x in stream_dispatches if x['kind']=='teacher')
        selected=observed_selection(configured_teacher_attempts)
    runtime_ready={};runtime_ready_files={}
    runtime_root=controller.parent if authority else ROOT/'stream/collection-r4/deployment-r7b'
    runtime_roots=list(dict.fromkeys([ROOT/'stream/collection-r4/deployment-r7b',runtime_root]))
    if authority:
        authority_doc=parse_metadata_json(authority.read_text());manifest_path=Path(authority_doc['manifest'])
        manifest_raw=manifest_path.read_bytes()
        if hashlib.sha256(manifest_raw).hexdigest()!=authority_doc['manifest_sha256']:
            raise ValueError('Current authority Campaign manifest changed')
        declared=parse_metadata_json(manifest_raw)['readiness_roots']
        runtime_roots=list(dict.fromkeys(Path(path) for path in declared))
    for p in [p for root in runtime_roots for p in [*sorted((root/'environment-outcomes').glob('*.json')),*sorted((root/'ready-revisions').glob('*/*.json'))]]:
        x=parse_metadata_json(p.read_text())
        if x['status']=='ENV_READY' and x.get('engine_id')=='59c8ba22-0aa4-4aed-bc43-4e1b5989fa22':
            runtime_ready[x['task_id']]=x;runtime_ready_files[x['task_id']]=p
    from collection_current_setup_blocks_r293 import current_setup_blocks
    setup_blocks=current_setup_blocks(ROOT,runtime_ready)
    from collection_administrative_ready_r427 import reconcile
    setup_blocks, reconciled = reconcile(ROOT,runtime_ready,setup_blocks)
    value['administrative_admission_environment_reconciliation']=reconciled
    value['runtime17_historical_native_ready_by_pool']=dict(Counter(x['pool'] for x in runtime_ready.values()))
    value['runtime17_native_ready_by_pool']=dict(Counter(x['pool'] for ident,x in runtime_ready.items() if ident not in setup_blocks))
    value['runtime17_current_setup_blocks']=setup_blocks
    finite_failures=finite_environment_failures(ROOT)
    # The health report uses a directory-entry snapshot, as does Ready above.
    # Avoid repeating one nonexistent-file stat per Task and historical root.
    failure_files_by_task={}
    for root in runtime_roots:
        for path in (root/'environment-failures').glob('*.json'):
            failure_files_by_task.setdefault(path.stem,[]).append(path)
    # One directory-entry snapshot per observation. Immutable proof contents
    # and declared hashes are still read/checked whenever a file is present.
    basic_folders=['cf-reserve-environments-r1','cf-environments-ssd17-recheck-r7','cf-environments-oci-r5','cf-environments-ssd17-r6',
        'tmax-environments-preregistered-reserve-r3','tmax-environments-public-input-review-r6','tmax-environments-collision-recheck-r5','tmax-environments-runtime-r4','tmax-environments-ssd17-r7']
    basic_entries={name:{path.name for path in (ROOT/'checks'/name).glob('*.json')} for name in basic_folders}
    review_folders=['native-environment-reviews-r10','cf-environment-boundary-reviews-r8','native-environment-review-corrections-r11','task-source-boundary-reviews-r7']
    review_entries={name:{path.stem for path in (ROOT/'checks'/name).glob('*.json')} for name in review_folders}
    failure_snapshot={str(path) for paths in failure_files_by_task.values() for path in paths}
    failure_snapshot.update(str(item[0]) for item in finite_failures.values())
    environment=[]
    for row in selected:
        ident=row['task_id']
        failure_paths=failure_files_by_task.get(ident,[]).copy()
        if ident in finite_failures:
            failure_paths.append(finite_failures[ident][0])
        runtime_failure=max(failure_paths,
            key=lambda path:(path.stat().st_mtime_ns,str(path)),
            default=runtime_root/'environment-failures'/(ident+'.json'))
        if ident in runtime_ready_files:
            native,native_doc=runtime_ready_files[ident],runtime_ready[ident]
        else:
            natives=[ROOT/'stream/collection-r4/deployment-r7b/environment-outcomes'/(ident+'.json'),ROOT/'stream/collection-r4/deployment-r6c/environment-outcomes'/(ident+'.json'),ROOT/'stream/collection-r4/deployment-r6b/environment-outcomes'/(ident+'.json'),ROOT/'stream/collection-r4/deployment-r6/environment-outcomes'/(ident+'.json')]+[ROOT/'stream'/scope/'environment-outcomes'/(ident+'.json') for scope in ['collection-r4','tmax-original-registry-acceptance-r9','tmax-resident-buffer-preflight-r1','private17-native-acceptance-r8','private17-native-acceptance-r7','private17-native-acceptance-r4','private17-native-acceptance-r3','collection-r3','environment-preflight-r5','tmax-original-network-recovery-r6','tmax-original-infra-recovery-r7','collection-r2']]
            natives.append(ROOT/'checks/native-reserve-acceptance-r4'/(ident+'.json'))
            natives.insert(0,runtime_failure)
            native,native_doc=first_environment_outcome(natives)
        item=dict(pool=row['pool'],task_id=ident,slot_id=row.get('slot_id',ident),split=row['split'],family_id=row['family_id'],
            target_runtime_node='17',runtime17_current_deployment_status='ENV_READY' if ident in runtime_ready else 'ENV_FAILED' if str(runtime_failure) in failure_snapshot else 'ENV_CHECK_PENDING',
            status='ENV_CHECK_PENDING',basic_preparation='NOT_OBSERVED',reason='Queued; not a final preparation outcome',evidence='')
        names=['cf-reserve-environments-r1','cf-environments-ssd17-recheck-r7','cf-environments-oci-r5','cf-environments-ssd17-r6'] if row['pool']=='calibforge' else ['tmax-environments-preregistered-reserve-r3','tmax-environments-public-input-review-r6','tmax-environments-collision-recheck-r5','tmax-environments-runtime-r4','tmax-environments-ssd17-r7']
        for name in names:
            file=ROOT/'checks'/name/(ident+'.json')
            if file.name not in basic_entries[name]:continue
            x=parse_metadata_json(file.read_text());item.update(basic_preparation=x['status'],evidence=str(file))
            if x['status']=='NATIVE_CLI_NOP_ACCEPTANCE_IN_PROGRESS':
                saved=Path(x['saved_capacity_marker'])
                if hashlib.sha256(saved.read_bytes()).hexdigest()!=x['saved_capacity_marker_sha256']:raise ValueError('Saved capacity marker changed')
                item.update(status='ENV_CHECK_PENDING',reason='Native CLI installation and official NOP verifier checks in progress; no teacher request');break
            if x['status']=='IMAGE_BASIC_PASSED_CAPACITY_HOLD':
                historical=Path(x['original_evidence'])
                if hashlib.sha256(historical.read_bytes()).hexdigest()!=x['original_evidence_sha256']:raise ValueError('Original preparation bytes under capacity hold changed')
                item.update(status='ENV_CHECK_PENDING',reason=x['capacity_hold_reason']);break
            if x['status'] in ['IMAGE_IDENTITY_AND_BASIC_SETUP_PASSED','IMAGE_AND_ORIGINAL_INITIAL_STATE_PASSED_FINAL_VERIFIER_PENDING']:
                item.update(status='ENV_CHECK_PENDING',reason='Basic checks passed; native CLI/Verifier acceptance pending');break
            item.update(status='ENV_FAILED',reason=x.get('error') or x.get('initial_state_stderr') or x['status'])
        if native_doc is not None:
            x=native_doc;item.update(status=x['status'],reason=x.get('reason','Native CLI install and original NOP Verifier completed'),evidence=str(native))
            if native.parent==ROOT/'stream/tmax-resident-buffer-preflight-r1/environment-outcomes' and administrative_retirement(x):
                item.update(status='ENV_CHECK_PENDING',reason='Old zero-model preparation administratively retired; current17 preparation pending; historical failure retained')
        review=ROOT/'checks/native-environment-reviews-r10'/(ident+'.json')
        if ident in review_entries['native-environment-reviews-r10']:
            x=parse_metadata_json(review.read_text())
            artifacts=[dict(path=x['prior_outcome'],sha256=x['prior_outcome_sha256']),*x.get('original_verifier_logs',[])]
            if 'native_results' in x:
                artifacts.extend(dict(path=v['trial']+'/result.json',sha256=v['result_sha256']) for v in x['native_results'].values())
            else:
                # Package-only reviews bind the completed install/NOP Results
                # in their immutable current17 Ready receipt.
                accepted=runtime_ready[ident]
                artifacts.extend(dict(path=accepted['native_'+kind+'_trial']+'/result.json',sha256=accepted[kind+'_result_sha256']) for kind in ['install','nop'])
            if any(hashlib.sha256(Path(v['path']).read_bytes()).hexdigest()!=v['sha256'] for v in artifacts):raise ValueError('Native environment review source changed')
            item.update(status='ENV_READY',reason=' '.join(filter(None,[x['review_reason'],x.get('controller_admission')])),evidence=str(review))
        boundary=ROOT/'checks/cf-environment-boundary-reviews-r8'/(ident+'.json')
        if ident in review_entries['cf-environment-boundary-reviews-r8']:
            x=parse_metadata_json(boundary.read_text())
            if hashlib.sha256(Path(x['runtime_inventory_proof']).read_bytes()).hexdigest()!=x['runtime_inventory_proof_sha256']:raise ValueError('Original image boundary proof changed')
            item.update(status=x['status'],reason=x['reason'],evidence=str(boundary))
        correction=ROOT/'checks/native-environment-review-corrections-r11'/(ident+'.json')
        if ident in review_entries['native-environment-review-corrections-r11']:
            x=parse_metadata_json(correction.read_text())
            for path,key in [('superseded_review','superseded_review_sha256'),('original_verifier_script','original_verifier_script_sha256'),('original_dockerfile','original_dockerfile_sha256')]:
                if hashlib.sha256(Path(x[path]).read_bytes()).hexdigest()!=x[key]:raise ValueError('Environment review correction evidence changed')
            item.update(status=x['status'],reason=x['reason'],evidence=str(correction))
        source_boundary=ROOT/'checks/task-source-boundary-reviews-r7'/(ident+'.json')
        if ident in review_entries['task-source-boundary-reviews-r7']:
            x=parse_metadata_json(source_boundary.read_text())
            for key in ['original_definition','original_instruction','original_verifier','runtime_inventory_proof']:
                if key in x and hashlib.sha256(Path(x[key]).read_bytes()).hexdigest()!=x[key+'_sha256']:
                    raise ValueError('Trusted source-boundary evidence changed')
            if x['status']=='ENV_BLOCKED':
                item.update(status='ENV_BLOCKED',reason=x['reason'],evidence=str(source_boundary))
        item['runtime17_current_reason']=setup_blocks.get(ident,{}).get('reason','')
        item['runtime17_current_evidence']=setup_blocks.get(ident,{}).get('evidence','')
        if ident in setup_blocks:item['runtime17_current_deployment_status']='ENV_BLOCKED'
        environment.append(item)
    text=io.StringIO();writer=csv.DictWriter(text,fieldnames=list(environment[0]));writer.writeheader();writer.writerows(environment)
    (ROOT/'ENVIRONMENT_1000_STATUS.csv').write_text(text.getvalue())
    value['environment_status_by_pool']={pool:dict(Counter(x['status'] for x in environment if x['pool']==pool)) for pool in ['calibforge','tmax']}
    value['runtime17_environment_status_by_pool']={pool:dict(Counter(x['runtime17_current_deployment_status'] for x in environment if x['pool']==pool)) for pool in ['calibforge','tmax']}
    value['all1000_environment_checks_terminal']=all(x['status']!='ENV_CHECK_PENDING' for x in environment)
    metrics=dict(checked_at=value['checked_at'],terminal_teacher_trials=value['terminal_teacher_trials'],stream_teacher_dispatches=sum(x['kind']=='teacher' for x in stream_dispatches),
        basic_receipts=sum(x['basic_preparation']!='NOT_OBSERVED' for x in environment),env_ready=sum(x['status']=='ENV_READY' for x in environment),
        disk_available_bytes=value['disk_available_bytes'])
    metric_file=ROOT/'checks/collection-progress-metrics.jsonl'
    prior=[parse_metadata_json(line) for line in metric_file.read_text().splitlines()] if metric_file.exists() else []
    cutoff=datetime.datetime.now(datetime.timezone.utc)-datetime.timedelta(minutes=20)
    baseline=next((x for x in reversed(prior) if datetime.datetime.fromisoformat(x['checked_at'])<=cutoff),None)
    value['twenty_minute_delta']={key:metrics[key]-baseline[key] for key in metrics if key!='checked_at'} if baseline else {'status':'NO_20_MINUTE_BASELINE_YET'}
    if baseline:
        value['twenty_minute_delta'].update(baseline_checked_at=baseline['checked_at'],
            observed_interval_seconds=(datetime.datetime.fromisoformat(metrics['checked_at'])-datetime.datetime.fromisoformat(baseline['checked_at'])).total_seconds())
    with metric_file.open('a') as stream:stream.write(json.dumps(metrics)+'\n')
    logger = getLogger('cf-tmax-collection-observer'); logger.setLevel('INFO')
    handler = RotatingFileHandler(ROOT/'logs/collection-monitor.jsonl', maxBytes=8*1024**2, backupCount=4)
    handler.setFormatter(Formatter('%(message)s')); logger.addHandler(handler)
    logger.info(json.dumps(value)); logger.removeHandler(handler); handler.close()
    target = ROOT / 'progress.json'; temporary = target.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, indent=2)); os.replace(temporary, target)
    from collection_reports_r325 import render
    render(ROOT,value,environment)
    print(json.dumps({k: value[k] for k in ['checked_at', 'terminal_trials', 'live_processes']}))


if __name__ == '__main__':
    main()
