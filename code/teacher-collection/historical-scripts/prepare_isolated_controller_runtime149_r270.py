"""Install the accepted provider in a separate controller venv; no live mutation."""
import datetime
import hashlib
import json
import os
from pathlib import Path
import shlex
import subprocess

R = Path('/home/chenkeyi/.local/share/harbor-rsi/qwen35-new-cf500-tmax500-20261029')
BASE = Path('/home/chenkeyi/.local/share/harbor-rsi/qwen35-m1-m2-tb21-20261026/venv')
OLD_PROVIDER = Path('/home/chenkeyi/.local/share/harbor-rsi/tb21-teacher-max-20261023/venv/lib/python3.12/site-packages/harbor_remote_docker')
ROOT = R / 'controller-runtime-r270'
VENV = ROOT / 'venv'
WHEEL = 'harbor_remote_docker-0.1.0+rsi.poststart.20261101-py3-none-any.whl'
WHEEL_SHA = '4a38141ac6df1df636844597dc5659efea1209ee523bf92362f972cc734d85ff'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    ROOT.mkdir(exist_ok=False)
    deployment = json.loads((R / 'configs/campaign-deployment17-r19.json').read_text())
    before = {p.name: sha(p) for p in OLD_PROVIDER.glob('*.py')}
    source = deployment['runtime']['ssd_root'] + '/provider-public-cache-r268/dist/' + WHEEL
    incoming = ROOT / (WHEEL + '.incoming')
    with incoming.open('xb') as stream:
        subprocess.run([*deployment['ssh'], deployment['host'], shlex.join(['cat', source])], stdout=stream, check=True, timeout=60)
    if sha(incoming) != WHEEL_SHA:
        raise ValueError('Accepted provider wheel SHA differs')
    wheel = ROOT / WHEEL
    incoming.replace(wheel)
    subprocess.run(['cp', '-a', '--reflink=auto', str(BASE), str(VENV)], check=True, timeout=300)
    pth = VENV / 'lib/python3.12/site-packages/frozen-harbor-runtime.pth'
    disabled = pth.with_suffix('.disabled')
    pth.rename(disabled)
    env = dict(os.environ)
    for key in ['DEEPSEEK_API_KEY', 'OPENAI_API_KEY', 'GH_TOKEN']:
        env.pop(key, None)
    try:
        with (ROOT / 'INSTALL.log').open('x') as log:
            subprocess.run(['/home/chenkeyi/.local/share/harbor-rsi/pr-delivery-20261021/uv', 'pip', 'install', '--python', str(VENV / 'bin/python'), '--no-deps', str(wheel)], env=env, stdout=log, stderr=subprocess.STDOUT, check=True, timeout=120)
    finally:
        disabled.rename(pth)
    code = "import harbor,harbor_remote_docker,sys,json,importlib.metadata as m;print(json.dumps(dict(prefix=sys.prefix,harbor=harbor.__file__,provider=harbor_remote_docker.__file__,version=m.version('harbor-remote-docker'))))"
    proof = json.loads(subprocess.run([str(VENV / 'bin/python'), '-c', code], env=env, capture_output=True, text=True, check=True, timeout=30).stdout)
    if proof['prefix'] != str(VENV) or not proof['provider'].startswith(str(VENV) + '/'):
        raise ValueError('Candidate provider escaped the isolated runtime')
    after = {p.name: sha(p) for p in OLD_PROVIDER.glob('*.py')}
    if before != after:
        raise ValueError('Original provider source changed')
    candidate = VENV / 'lib/python3.12/site-packages/harbor_remote_docker'
    out = dict(checked_at=datetime.datetime.now(datetime.timezone.utc).isoformat(), passed=True, interpreter=str(VENV / 'bin/python'), runtime=proof, accepted_wheel=str(wheel), wheel_sha256=WHEEL_SHA, original_provider_before=before, original_provider_after=after, candidate_provider={p.name: sha(p) for p in candidate.glob('*.py')}, original_controller_environment_mutated=False, teacher_or_verifier_signals=0, model_calls=0, dispatch_authority_granted=False)
    (ROOT / 'ACCEPTANCE.json').write_text(json.dumps(out, indent=2))
    print(json.dumps(out))


if __name__ == '__main__':
    main()
