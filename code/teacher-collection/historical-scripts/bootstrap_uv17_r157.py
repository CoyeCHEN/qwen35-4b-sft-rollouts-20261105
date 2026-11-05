"""Fetch a public uv wheel on campaign SSD, verifying official PyPI identity."""
import hashlib
import json
from html.parser import HTMLParser
from pathlib import Path
import urllib.parse
import urllib.request
import zipfile

D = Path('/ssd/chenkeyi/qwen35-new-cf500-tmax500-20261029/controller17-r1/bootstrap')
metadata_url = 'https://pypi.org/pypi/uv/0.9.7/json'
mirror_index = 'https://mirrors.tuna.tsinghua.edu.cn/pypi/web/simple/uv/'
with urllib.request.urlopen(metadata_url, timeout=30) as response:
    info = json.load(response)
entry, = [x for x in info['urls'] if 'manylinux' in x['filename'] and 'x86_64' in x['filename'] and x['filename'].endswith('.whl')]

class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.urls = []
    def handle_starttag(self, tag, attrs):
        if tag == 'a':
            self.urls += [value for key, value in attrs if key == 'href']

with urllib.request.urlopen(mirror_index, timeout=30) as response:
    parser = Links()
    parser.feed(response.read().decode())
url, = [urllib.parse.urljoin(mirror_index, x) for x in parser.urls if urllib.parse.unquote(urllib.parse.urlparse(x).path).endswith('/' + entry['filename'])]
path = D / entry['filename']
temporary = D / (entry['filename'] + '.r157.partial')
if not path.exists():
    with urllib.request.urlopen(url, timeout=60) as response, temporary.open('wb') as stream:
        while chunk := response.read(1024 * 1024):
            stream.write(chunk)
    temporary.replace(path)
digest = hashlib.sha256(path.read_bytes()).hexdigest()
if digest != entry['digests']['sha256']:
    raise ValueError('Mirror bytes differ from official PyPI SHA256')
with zipfile.ZipFile(path) as archive:
    name, = [x for x in archive.namelist() if x.endswith('/uv') and not x.endswith('/')]
    blob = archive.read(name)
binary = D / 'uv'
if binary.exists() and binary.read_bytes() != blob:
    raise ValueError('Existing uv executable differs')
binary.write_bytes(blob)
binary.chmod(0o700)
value = dict(version='0.9.7', metadata_url=metadata_url, upstream_wheel_url=entry['url'], download_url=url,
    wheel_sha256=digest, executable=str(binary), executable_sha256=hashlib.sha256(blob).hexdigest(),
    system_environment_modified=False, model_provider_changed=False, model_calls=0)
with (D / 'UV_IDENTITY_R157.json').open('x') as stream:
    json.dump(value, stream, indent=2)
print(json.dumps(value))
