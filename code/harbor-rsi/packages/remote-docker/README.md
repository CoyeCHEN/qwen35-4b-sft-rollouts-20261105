# Harbor Remote Docker Provider

This package is an opt-in `BaseEnvironment` provider. It is loaded with
`environment.import_path` and does not change Harbor's Docker, Trial, Job, or
Verifier code.

```toml
[environment]
import_path = "harbor_remote_docker:RemoteDockerEnvironment"

[environment.kwargs]
endpoint = "ssh://user@docker-host"
staging_root = "/var/tmp/harbor-rsi"
project_namespace = "harbor"
```

The endpoint, SSH configuration, staging root, and Docker client settings are
provided by the invoking environment. Credentials are read by the SSH and
Docker clients; this package never accepts or stores a password or API key.

Remote bind inputs are copied into a private, identity-marked staging tree and
verified with SHA-256. Host-sensitive Compose features such as privileged
containers, host networking, devices, external volumes/networks, GPU/device
reservations, and Docker socket mounts are rejected before startup. A lost SSH
connection is recorded as an infrastructure failure; commands are not replayed
when the remote side may have changed state.

The provider advertises `mounted=false`, so Harbor uses its standard download
and artifact paths. Remote resources are deleted only after project, container,
network, volume, and staging identity checks. Cleanup failures leave evidence
for an explicit operator retry and never invoke global Docker pruning.

Local archive creation, hashing, extraction, and publication run outside the
event loop. Cancellation waits for an in-flight filesystem operation to finish
before removing its temporary files; repeated cancellation does not abandon a
writer. Filesystem errors still propagate, and transfers are not retried.

Transfer destination checks, directory preparation, and tar commands execute
from `/`, so deleting the image's working directory does not prevent artifact
collection. Agent and Verifier execution keep their existing working-directory
semantics. Transfers do not recreate a missing task directory or change scores.

Cleanup records the start, completion, duration, and resource identity of each
existing removal phase. An interrupted phase remains `UNKNOWN`; these events do
not replace the final resource-absence check or change the cleanup deadline.
