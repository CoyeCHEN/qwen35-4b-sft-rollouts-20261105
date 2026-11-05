"""Install exact resolved Harbor/plugin bytes in a new SSD-only controller venv."""
import datetime
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tarfile

S = Path('/ssd/chenkeyi/qwen35-new-cf500-tmax500-20261029/controller17-r1')
archive = S / 'bootstrap/controller17-runtime-source-r156.tar.gz'
expected = 'b7f7763a656911d5d2c8bf8521f13f0869ec4b81c42c05c282981677dda76856'
assert hashlib.sha256(archive.read_bytes()).hexdigest() == expected
source = S / 'installed-source-r160'
source.mkdir(exist_ok=False)
with tarfile.open(archive) as tar:
    for member in tar:
        path = Path(member.name)
        if not member.isfile() or path.is_absolute() or '..' in path.parts:
            raise ValueError('Unexpected runtime source archive member')
        target = source / path
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open('xb') as stream:
            stream.write(tar.extractfile(member).read())
manifest = json.loads((source / 'SOURCE_MANIFEST_R156.json').read_text())
for entry in manifest['files']:
    assert hashlib.sha256((source / entry['path']).read_bytes()).hexdigest() == entry['sha256']
env = dict(os.environ, UV_CACHE_DIR=str(S / 'uv-cache'), UV_PYTHON_INSTALL_DIR=str(S / 'python'),
    UV_NO_PROGRESS='1', UV_CONCURRENT_DOWNLOADS='4', TMPDIR=str(S / 'tmp'),
    XDG_CACHE_HOME=str(S / 'runtime-cache'), PIP_CACHE_DIR=str(S / 'pip-cache'))
for name in ['DEEPSEEK_API_KEY', 'OPENAI_API_KEY', 'GH_TOKEN', 'HTTPS_PROXY', 'HTTP_PROXY', 'ALL_PROXY']:
    env.pop(name, None)
uv = str(S / 'bootstrap/uv')
python = S / 'python/cpython-3.12.3-linux-x86_64-gnu/bin/python3.12'
venv = S / 'venv-r160'
with (S / 'bootstrap/runtime-install-r160.log').open('x') as log:
    def run(args):
        subprocess.run(args, env=env, stdout=log, stderr=subprocess.STDOUT, check=True, timeout=1800)
    run([uv, 'venv', '--python', str(python), str(venv)])
    py = str(venv / 'bin/python')
    run([uv, 'pip', 'install', '--python', py, '--no-deps', '-r', str(source / 'requirements-exact.txt'),
         '--index-url', 'https://mirrors.tuna.tsinghua.edu.cn/pypi/web/simple'])
    wheels = S / 'runtime-wheels-r160'
    wheels.mkdir(exist_ok=False)
    identities = []
    for module in manifest['modules']:
        run([py, '-m', 'wheel', 'pack', str(source / module['bundle_root']), '--dest-dir', str(wheels)])
        files = list(wheels.glob(module['bundle_root'] + '-*.whl'))
        wheel, = files
        identities.append(dict(path=str(wheel), sha256=hashlib.sha256(wheel.read_bytes()).hexdigest()))
        run([uv, 'pip', 'install', '--python', py, '--no-deps', str(wheel)])
    run([uv, 'pip', 'check', '--python', py])
    run([py, '-c', 'from harbor.trial.queue import TrialQueue; from harbor.trial.hooks import TrialEvent; '
         'from harbor.agents.installed.open_harness import OpenHarnessAgent; import harbor_remote_docker; '
         'import importlib.metadata as m; print(m.version("harbor"),m.version("harbor-remote-docker"))'])
value = dict(checked_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
    source_archive_sha256=expected, verified_original_code_and_metadata_files=len(manifest['files']),
    source_code_changed=False, python=str(python), venv=str(venv), repacked_wheels=identities,
    exact_dependencies_sha256=hashlib.sha256((source / 'requirements-exact.txt').read_bytes()).hexdigest(),
    system_environment_modified=False, shared_daemon_modified=False, model_calls=0,
    dispatch_authority_granted=False, controller_started=False)
with (S / 'bootstrap/RUNTIME_INSTALL_ACCEPTANCE_R160.json').open('x') as stream:
    json.dump(value, stream, indent=2)
print(json.dumps(value))
