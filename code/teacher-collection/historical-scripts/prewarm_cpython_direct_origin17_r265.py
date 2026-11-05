"""One finite public download on17; explicit DNS data, normal TLS and native uv."""
import pathlib,json,subprocess,os,hashlib,datetime,http.server,threading,functools,traceback
s=pathlib.Path('/ssd/chenkeyi/qwen35-new-cf500-tmax500-20261029')
d=s/'staging-private-engine17-r1/public-python-origin-cache-r265';d.mkdir(exist_ok=False)
uv=s/'public-python-diagnostic-r262/uv'
assert hashlib.sha256(uv.read_bytes()).hexdigest()=='3e801df892439f5cde65d8b51ea69b69abff199ef37cc3cae4481be15d592df0'
filename='cpython-3.12.12+20260211-x86_64-unknown-linux-gnu-install_only_stripped.tar.gz'
mirror=d/'mirror';date=mirror/'20260211';date.mkdir(parents=True)
for name in ['python','cache','tmp']:(d/name).mkdir()
def save(stage,**kw):
 kw.update(stage=stage,pid=os.getpid(),checked_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),model_calls=0,teacher_configuration_changes=0,system_dns_changes=0,shared_services_changed=0)
 p=d/'state.pending';p.write_text(json.dumps(kw,indent=2));p.replace(d/'state.json')
url='https://releases.astral.sh/github/python-build-standalone/releases/download/20260211/'+filename.replace('+','%2B')
save('ORIGINAL_CPYTHON_HTTPS_DOWNLOAD_WITH_EXPLICIT_RESOLUTION',origin=url,resolved_ip='104.26.12.77',tls_hostname_validation=True)
try:
 with (d/'curl-download.log').open('x') as log:
  subprocess.run(['curl','--noproxy','*','--fail','--location','--connect-timeout','5','--max-time','150','--resolve','releases.astral.sh:443:104.26.12.77','--silent','--show-error','--output',str(date/filename),url],stdout=log,stderr=subprocess.STDOUT,check=True,timeout=160)
 archive=date/filename;assert archive.stat().st_size==33887801
 archive_sha=hashlib.sha256(archive.read_bytes()).hexdigest()
 class Handler(http.server.SimpleHTTPRequestHandler):
  def log_message(self,fmt,*args):
   with (d/'local-mirror-access.log').open('a') as f:f.write((fmt%args)+'\n')
 server=http.server.ThreadingHTTPServer(('127.0.0.1',0),functools.partial(Handler,directory=str(mirror)))
 thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
 env=dict(os.environ,UV_PYTHON_INSTALL_DIR=str(d/'python'),UV_CACHE_DIR=str(d/'cache'),TMPDIR=str(d/'tmp'),NO_PROXY='127.0.0.1,localhost')
 for key in ['HTTP_PROXY','HTTPS_PROXY','ALL_PROXY','http_proxy','https_proxy','all_proxy','DEEPSEEK_API_KEY','OPENAI_API_KEY','GH_TOKEN']:env.pop(key,None)
 save('NATIVE_UV_VALIDATING_ORIGINAL_ARCHIVE_FROM_LOOPBACK',origin=url,original_archive_sha256=archive_sha,original_archive_bytes=archive.stat().st_size)
 try:
  with (d/'uv-install.log').open('x') as log:
   subprocess.run([str(uv),'-v','python','install','3.12.12','--install-dir',str(d/'python'),'--no-bin','--mirror','http://127.0.0.1:'+str(server.server_port)],env=env,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=180)
 finally:server.shutdown();server.server_close();thread.join(timeout=2)
 python,=list((d/'python').glob('cpython-3.12.12-*/bin/python3.12'))
 result=subprocess.run([str(python),'--version'],capture_output=True,text=True,check=True,timeout=10)
 assert result.stdout.strip()=='Python 3.12.12'
 save('PUBLIC_CPYTHON_ORIGINAL_CACHE_COMPLETE',passed=True,origin=url,python=str(python),version=result.stdout.strip(),archive=str(archive),original_archive_sha256=archive_sha,original_archive_bytes=archive.stat().st_size,python_binary_sha256=hashlib.sha256(python.read_bytes()).hexdigest(),native_uv_version='0.13.0',source_uv_sha256=hashlib.sha256(uv.read_bytes()).hexdigest())
except Exception as error:
 (d/'failure.txt').write_text(traceback.format_exc())
 save('PUBLIC_CPYTHON_CACHE_FAILED',passed=False,error_type=type(error).__name__,error=str(error)[-600:])
 raise
