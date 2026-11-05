"""Compare both parsers on every actual input of the unchanged monitor flow."""
import ast
import contextlib
import datetime
import hashlib
import io
import json
from pathlib import Path
import resource
import signal
import time

import observe_collection_native_json_r386 as candidate

R=candidate.ROOT
D=R/'checks/monitor-json-equivalence-r391'


def main():
 D.mkdir(exist_ok=False)
 old=R/'scripts/observe_collection_native_handoff_r348.py'
 new=Path(candidate.__file__)
 # Reversing only the reviewed decoder and owned CPU-driver metadata change
 # must restore every original main-flow statement, including every check.
 tree=ast.parse(new.read_text())
 tree.body=[node for node in tree.body if not (isinstance(node,ast.ImportFrom) and node.module=='pydantic_core') and not (isinstance(node,ast.FunctionDef) and node.name=='parse_metadata_json')]
 class Restore(ast.NodeTransformer):
  def visit_Name(self,node):
   if node.id=='parse_metadata_json':return ast.copy_location(ast.Attribute(value=ast.Name(id='json',ctx=ast.Load()),attr='loads',ctx=ast.Load()),node)
   return node
 tree=Restore().visit(tree)
 expected=ast.parse(old.read_text())
 # Embedded remote code differs only by recognizing the two canonical drivers.
 for node in ast.walk(tree):
  if isinstance(node,ast.Constant) and isinstance(node.value,str) and 'audit_stream_nfc_canonical17_r366.py' in node.value:
   node.value=node.value.replace('if any(str(r/"scripts"/name) in args for name in ["audit_stream_data_17.py","audit_stream_canonical17_r163.py","audit_stream_nfc_canonical17_r366.py"]):target_processes.append(dict(pid=int(p.name),trial_id=args[-1]))','if any(str(r/"scripts"/name) in args for name in ["audit_stream_data_17.py","audit_stream_canonical17_r163.py"]):target_processes.append(dict(pid=int(p.name),trial_id=args[-1]))')
 assert ast.dump(tree,include_attributes=False)==ast.dump(expected,include_attributes=False)
 count=0;total_bytes=0;parse=candidate.parse_metadata_json
 def compare(payload):
  nonlocal count,total_bytes
  baseline=json.loads(payload);actual=parse(payload)
  assert json.dumps(actual,sort_keys=True,ensure_ascii=True)==json.dumps(baseline,sort_keys=True,ensure_ascii=True), 'Native JSON parser changed a monitor input value'
  count+=1;total_bytes+=len(payload);return actual
 candidate.parse_metadata_json=compare
 started=time.monotonic();cpu=time.process_time()
 def save(code,complete):
  value=dict(passed=complete and code==0,checked_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
   source_sha256=hashlib.sha256(new.read_bytes()).hexdigest(),original_source_sha256=hashlib.sha256(old.read_bytes()).hexdigest(),
   all_original_monitor_main_flow_ast_preserved=True,actual_input_documents_compared=count,actual_input_bytes_compared=total_bytes,
   all_values_and_number_types_canonical_json_equal=True,exit_code=code,wall_seconds=time.monotonic()-started,
   self_cpu_seconds=time.process_time()-cpu,max_rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024,
   teacher_dispatches=0,task_or_data_index_changes=0,resource_acceptance_of_uninstrumented_candidate_still_required=True, instrumented_parity_test_cpu_quota="100% one CPU; deployed monitor stays10%")
  with (D/'result.json').open('x') as stream:json.dump(value,stream,indent=2)
 def stop(signum,frame):save(124,False);raise SystemExit(124)
 signal.signal(signal.SIGTERM,stop)
 with contextlib.redirect_stdout(io.StringIO()):candidate.main()
 save(0,True)


if __name__=='__main__':main()
