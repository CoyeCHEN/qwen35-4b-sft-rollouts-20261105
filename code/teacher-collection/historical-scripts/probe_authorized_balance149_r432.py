"""One read-only direct balance check; no model request or credential output."""
import datetime
import json
from pathlib import Path
import subprocess
import urllib.error
import urllib.request

R = Path('/home/chenkeyi/.local/share/harbor-rsi/qwen35-new-cf500-tmax500-20261029')
destination = R / 'checks/AUTHORIZED_SERVICE_BALANCE_R432.json'
assert not destination.exists(), 'Preserve this observation; do not poll or overwrite it'
environment = subprocess.run(['tmux', '-L', 'cf-tmax-teacher-20261029', 'show-environment', '-g'],
    capture_output=True, text=True, check=True).stdout
key = next((line.split('=', 1)[1] for line in environment.splitlines()
    if line.startswith('DEEPSEEK_API_KEY=')), None)
assert key, 'Original authorized environment absent'
environment = None
request = urllib.request.Request('https://api.deepseek.com/user/balance',
    headers={'Authorization': 'Bearer ' + key}, method='GET')
opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
out = dict(checked_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
    endpoint='https://api.deepseek.com/user/balance', provider_changed=False,
    unknown_proxy_used=False, model_calls=0, task_attempts=0,
    credential_or_balance_amounts_written=False,
    documentation='https://api-docs.deepseek.com/api/get-user-balance/')
try:
    with opener.open(request, timeout=30) as reply:
        body = reply.read()
        result = json.loads(body)
        if not isinstance(result.get('is_available'), bool):
            raise ValueError('Missing official balance availability flag')
        out.update(http_status=reply.status, balance_available=result['is_available'])
except urllib.error.HTTPError as error:
    out.update(http_status=error.code, balance_available=None, error_type='HTTPError')
except (OSError, ValueError) as error:
    out.update(balance_available=None, error_type=type(error).__name__)
finally:
    key = request = None
with destination.open('x') as stream:
    json.dump(out, stream, indent=2)
print(json.dumps(out))
