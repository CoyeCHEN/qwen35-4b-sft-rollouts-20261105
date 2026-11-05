"""Freeze public pytest dependencies for the original Python3.10 interpreter.

No Task, official test, image, model or global Python installation is changed.
"""
import datetime
import hashlib
import json
import os
from pathlib import Path
import subprocess
import urllib.request
import zipfile

S = Path('/ssd/chenkeyi/qwen35-new-cf500-tmax500-20261029/verifier-public-python-r59')


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def main():
    S.mkdir(exist_ok=False)
    wheels = S / 'wheels'
    target = S / 'python310-site-packages'
    wheels.mkdir()
    target.mkdir()
    env = dict(os.environ)
    for name in ['DEEPSEEK_API_KEY', 'OPENAI_API_KEY', 'GH_TOKEN']:
        env.pop(name, None)
    env.update(PYTHONDONTWRITEBYTECODE='1', PIP_INDEX_URL='https://pypi.tuna.tsinghua.edu.cn/simple')
    python = '/usr/bin/python3'
    version = subprocess.run([python, '-c', 'import sys;assert sys.version_info[:2]==(3,10);print(sys.version)'],
        check=True, capture_output=True, text=True).stdout.strip()
    with (S / 'public-download.log').open('x') as log:
        subprocess.run([python, '-m', 'pip', 'download', '--only-binary=:all:', '--dest', str(wheels),
            'pytest==8.4.1'], env=env, stdout=log, stderr=subprocess.STDOUT, check=True, timeout=300)
    records = []
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({'https':'http://127.0.0.1:7890'}))
    for wheel in sorted(wheels.glob('*.whl')):
        with zipfile.ZipFile(wheel) as stream:
            metadata = [name for name in stream.namelist() if name.endswith('.dist-info/METADATA')]
            if len(metadata) != 1:
                raise ValueError('Unexpected public wheel metadata')
            fields = stream.read(metadata[0]).decode().splitlines()
            name = next(line.split(': ', 1)[1] for line in fields if line.startswith('Name: '))
            package_version = next(line.split(': ', 1)[1] for line in fields if line.startswith('Version: '))
        url = 'https://pypi.org/pypi/' + name + '/' + package_version + '/json'
        with opener.open(url, timeout=45) as response:
            upstream_raw = response.read()
        upstream = json.loads(upstream_raw)
        matched = [item for item in upstream['urls'] if item['filename'] == wheel.name and item['digests']['sha256'] == sha(wheel)]
        if len(matched) != 1:
            raise ValueError('Public wheel differs from official PyPI digest')
        (S / (wheel.name + '.pypi.json')).write_bytes(upstream_raw)
        records.append(dict(name=name, version=package_version, filename=wheel.name,
            sha256=sha(wheel), official_url=matched[0]['url'], official_metadata_url=url,
            official_metadata_sha256=hashlib.sha256(upstream_raw).hexdigest()))
    with (S / 'public-install.log').open('x') as log:
        subprocess.run([python, '-m', 'pip', 'install', '--no-index', '--no-deps', '--no-compile',
            '--target', str(target), *map(str, sorted(wheels.glob('*.whl')))],
            env=env, stdout=log, stderr=subprocess.STDOUT, check=True, timeout=120)
    check_env = dict(env, PYTHONPATH=str(target))
    verified = subprocess.run([python, '-m', 'pytest', '--version'], env=check_env,
        check=True, capture_output=True, text=True, timeout=30).stdout.strip()
    if verified != 'pytest 8.4.1':
        raise ValueError('Original interpreter cannot load the pinned public test runner')
    files = [dict(path=str(path.relative_to(target)), bytes=path.stat().st_size, sha256=sha(path))
        for path in sorted(target.rglob('*')) if path.is_file()]
    result = dict(status='PUBLIC_PYTEST_CACHE_FROZEN_NATIVE_ACCEPTANCE_PENDING',
        checked_at=datetime.datetime.now(datetime.timezone.utc).isoformat(), original_python=version,
        target=str(target), packages=records, files=files, native_version_probe=verified,
        source_sha256=sha(Path(__file__)), model_calls=0, official_task_or_test_changes=0,
        global_python_or_image_changes=0, teacher_ready_published=False)
    with (S / 'PUBLIC_PYTEST_CACHE.json').open('x') as stream:
        json.dump(result, stream, indent=2)
    print(json.dumps(dict(status=result['status'], packages=len(records), files=len(files), pytest=verified)))


if __name__ == '__main__':
    main()
