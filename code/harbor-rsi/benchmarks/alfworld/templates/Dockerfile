# ALFWorld task environment.
#
# Single stage on purpose: E2B's template builder rejects multi-stage
# Dockerfiles, and each ENV must be its own line because its parser collapses
# line continuations into the first value.
#
# jericho and fast_downward_textworld ship as sdists only, so a toolchain is
# required at build time and purged afterwards.
FROM python:3.11-slim

ENV PIP_NO_CACHE_DIR=1
ENV PIP_INDEX_URL=https://pypi.org/simple
ENV PIP_CONFIG_FILE=/dev/null
ENV DEBIAN_FRONTEND=noninteractive
ENV ALFWORLD_AGENT_SOCKET=/run/alfworld/agent.sock

RUN apt-get update \
 && apt-get install -y --no-install-recommends build-essential cmake ca-certificates procps \
 && python3 -m venv /opt/alfworld-venv \
 && /opt/alfworld-venv/bin/pip install --no-cache-dir "alfworld==0.4.2" "pyyaml>=6" \
 && /opt/alfworld-venv/bin/python -c "import textworld, alfworld" \
 && apt-get purge -y build-essential cmake \
 && apt-get autoremove -y \
 && rm -rf /var/lib/apt/lists/*

# The agent runs as this user. It is deliberately not in the sudo group: the
# platform's own default user has NOPASSWD sudo, which would let the agent read
# every hidden asset and bypass the observation boundary entirely.
RUN useradd --create-home --shell /bin/bash --uid 2000 alfagent

# Hidden benchmark assets: game file, PDDL, traj_data, daemon config and log.
# Root-owned and unreadable to the agent user.
RUN mkdir -p /opt/alfworld-private
COPY private/ /opt/alfworld-private/
RUN chown -R root:root /opt/alfworld-private \
 && chmod 700 /opt/alfworld-private \
 && chmod -R go-rwx /opt/alfworld-private

# Agent-facing CLI: observe and act, nothing else.
COPY play.py /usr/local/bin/play.py
RUN chown root:root /usr/local/bin/play.py && chmod 755 /usr/local/bin/play.py

COPY healthcheck.sh /opt/alfworld-private/healthcheck.sh
RUN chmod 700 /opt/alfworld-private/healthcheck.sh

RUN mkdir -p /run/alfworld && chmod 755 /run/alfworld

RUN mkdir -p /home/alfagent/work && chown alfagent:alfagent /home/alfagent/work
WORKDIR /home/alfagent/work
