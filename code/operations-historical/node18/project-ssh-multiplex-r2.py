#!/usr/bin/python3
import os,sys
from pathlib import Path
R=Path("/ssd/chenkeyi/qwen35-sft-772-20261101")
# Four bounded native OpenSSH control sockets; never replay a remote command.
args=["/usr/bin/ssh","-F",str(R/"control-ssh/formal-engine149-mux-r2.conf"),"-o","ControlPath="+str(R/".ssh-mux-r2"/(str(os.getppid()%4)+".sock")),*sys.argv[1:]]
os.execv(args[0],args)
