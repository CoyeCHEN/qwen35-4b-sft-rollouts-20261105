"""Seed the existing authorized key through stdin into the private tmux environment."""
import hashlib
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys

ROOT=Path('/home/chenkeyi/.local/share/harbor-rsi/qwen35-new-cf500-tmax500-20261029')
incoming=json.load(sys.stdin)
source=ROOT/'scripts/run_collection_campaign.py'
assert hashlib.sha256(source.read_bytes()).hexdigest()==incoming['source_sha256']
assert incoming['DEEPSEEK_API_KEY']
socket='cf-tmax-teacher-20261029'
live=subprocess.run(['tmux','-L',socket,'list-sessions'],capture_output=True,text=True,timeout=10)
assert live.returncode!=0,'Inspect the existing private controller instead of starting another'
environment={k:os.environ[k] for k in ['HOME','PATH','LANG','LC_ALL','TERM','XDG_RUNTIME_DIR'] if k in os.environ}
environment.update(DEEPSEEK_API_KEY=incoming['DEEPSEEK_API_KEY'],PYTHONUNBUFFERED='1')
command='umask 077; exec '+shlex.join([
    '/home/chenkeyi/.local/share/harbor-rsi/qwen35-m1-m2-tb21-20261026/venv/bin/python',str(source)])+' > '+shlex.quote(str(ROOT/'logs/campaign-controller-original-directory-r4.log'))+' 2>&1'
subprocess.run(['tmux','-L',socket,'new-session','-d','-s','campaign-original-environment-r4',command],env=environment,check=True,timeout=20)
subprocess.run(['tmux','-L',socket,'set-option','-s','exit-empty','off'],check=True,timeout=10)
print(json.dumps(dict(status='PRIVATE_CONTROLLER_REARMED_WAITING_FOR_EVIDENCE',source_sha256=incoming['source_sha256'],credential_transport='Encrypted SSH stdin to process/private tmux environment only',teacher_dispatches=0)))
