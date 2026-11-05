"""Recovery environment for the two Terminal-Bench qemu tasks.

The original Debian templates cannot be provisioned by the current E2B image
builder because its pre-Dockerfile provisioning still reaches expired
Bullseye security metadata.  These aliases point at the Ubuntu-based rebuilt
templates and leave the normal resumable E2B lifecycle unchanged.
"""

import os
from typing import override

from harbor.environments.e2b_resumable import ResumableE2BEnvironment


ALIASES = {
    "qemu-alpine-ssh": "tb21-qemu-alpine-ubuntu-20260923",
    "qemu-startup": "tb21-qemu-startup-ubuntu-20260923",
}

ALIAS_ENV_VARS = {
    "qemu-alpine-ssh": "TB_QEMU_ALPINE_TEMPLATE",
    "qemu-startup": "TB_QEMU_STARTUP_TEMPLATE",
}

# Check prerequisites only. The agent must still boot/configure the guest;
# the original verifier checks SSH 2222 / telnet 6665 after the agent phase.
PROBE_COMMAND = (
    "set -eu; "
    "command -v qemu-system-x86_64 >/dev/null || "
    "command -v qemu-system-x86 >/dev/null; "
    'for tool in qemu-img expect telnet; do command -v "$tool" >/dev/null; done; '
    "test -s /app/alpine.iso; "
    "(qemu-system-x86_64 --version 2>/dev/null || qemu-system-x86 --version); "
    "qemu-img --version"
)


def recovery_alias(task_name):
    if task_name not in ALIASES:
        return None
    alias = os.environ.get(ALIAS_ENV_VARS[task_name], ALIASES[task_name]).strip()
    if not alias or any(char.isspace() for char in alias):
        raise ValueError(
            f"{ALIAS_ENV_VARS[task_name]} must contain a nonempty E2B alias"
        )
    return alias


class QemuRecoveryE2BEnvironment(ResumableE2BEnvironment):
    """Use the rebuilt per-task E2B template aliases for qemu recovery."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._original_template_name = self._template_name
        self._recovery_alias = recovery_alias(self.environment_name)
        if self._recovery_alias is not None:
            self._template_name = self._recovery_alias

    @override
    async def _create_template(self):
        if self._recovery_alias is not None:
            raise RuntimeError(
                f"QEMU recovery template {self._template_name!r} is unavailable. "
                "Build/probe a new alias as documented in docs/rsi/environments.md; "
                "refusing to build the original image under a recovery alias."
            )
        await super()._create_template()

    @override
    async def start(self, force_build=False):
        if self._recovery_alias is not None:
            if force_build:
                raise ValueError(
                    "QEMU recovery forbids force_build; use a new alias explicitly"
                )
            self._record(
                "template_override",
                task=self.environment_name,
                original_template=self._original_template_name,
                recovery_template=self._template_name,
                original_image=self.task_env_config.docker_image,
            )
        await super().start(force_build=force_build)
        if self._recovery_alias is not None:
            result = await self.exec(PROBE_COMMAND, timeout_sec=30)
            self._record(
                "template_probe",
                template=self._template_name,
                return_code=result.return_code,
                stdout=result.stdout,
                stderr=result.stderr,
            )
            if result.return_code != 0:
                raise RuntimeError(
                    f"QEMU prerequisites missing in {self._template_name!r}"
                )
