#!/usr/bin/python3
"""Native SSH transport only; independent command connections to the same17 Engine."""
import os
import sys

R='/home/chenkeyi/.local/share/harbor-rsi/qwen35-new-cf500-tmax500-20261029'
args=sys.argv[1:]
is17=any(x in ('180.163.192.17','chenkeyi@180.163.192.17') for x in args)
if is17:
    if args[-3:]==['docker','system','dial-stdio']:
        args[-3:]=['docker','--host','unix:///ssd/chenkeyi/qwen35-new-cf500-tmax500-20261029/engine17-r1/socket/docker.sock','system','dial-stdio']
    elif args and args[-1]=='docker system dial-stdio':
        args[-1]='docker --host unix:///ssd/chenkeyi/qwen35-new-cf500-tmax500-20261029/engine17-r1/socket/docker.sock system dial-stdio'
    if '-S' in args:
        # Existing explicit read-only/archive clients keep their established
        # master. New native Docker/Harbor commands use the dedicated identity.
        command=['/usr/bin/ssh','-F',R+'/ssh/client-v2.conf',*args]
    else:
        command=['/usr/bin/ssh','-F',R+'/ssh/client-v2.conf',
            '-o','ProxyCommand=none','-o','ProxyJump=none',
            '-o','ControlMaster=auto','-o','ControlPersist=30',
            '-o','ControlPath=/home/chenkeyi/.ssh/cftmx17-%C-'+str(os.getppid()),
            '-o','BatchMode=yes','-o','IdentitiesOnly=yes',
            '-o','IdentityAgent='+R+'/ssh/campaign17-agent-r6/agent.sock',
            '-i',R+'/ssh/campaign17-agent-r6/identity.pub',*args]
else:
    command=['/usr/bin/ssh','-o','ControlPath=/home/chenkeyi/.ssh/cftmx2-%C-'+str(os.getppid()),'-F',R+'/ssh/client-v2.conf',*args]
os.execv(command[0],command)
