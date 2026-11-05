"""Read-only owned serving evidence used by the existing unique native advance."""
import importlib,json,urllib.request
from pathlib import Path

def get(port,path):
 opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
 with opener.open('http://127.0.0.1:'+str(port)+path,timeout=5)as response:return json.load(response)

def ancestors(pid):
 result=[]
 while pid>1 and pid not in result:
  result.append(pid);path=Path('/proc')/str(pid)/'stat';pid=int(path.read_text().rsplit(')',1)[1].split()[1])
 return result

def leases():
 return importlib.import_module('read-priority32-gpu-leases149-r7').observe_from_node18()
