# Optional public Agent bootstrap layer, independent of the task's Python runtime.
# This recipe targets the observed Debian/Python 3.13 private CLI runtime.
ARG BASE_IMAGE
FROM ${BASE_IMAGE}
RUN apt-get update \
 && apt-get install -y --no-install-recommends coreutils ripgrep fd-find python3.13-venv \
 && rm -rf /var/lib/apt/lists/* \
 && python3.13 -c 'import ensurepip'
