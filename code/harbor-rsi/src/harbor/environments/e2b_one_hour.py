"""Opt-in Harbor E2B environment for accounts limited to one-hour sandboxes.

Harbor 0.23.0 requests a 24-hour E2B sandbox unconditionally.  Some E2B
accounts allow only one hour, so this environment keeps Harbor's normal E2B
implementation and changes only the sandbox lifetime when explicitly selected.
"""

from __future__ import annotations

from typing import override
from e2b import AsyncSandbox

from harbor.environments.e2b import (
    retry,
    stop_after_attempt,
    wait_exponential,
)
from harbor.models.task.config import NetworkMode

from .e2b_reconnect import ReconnectingE2BEnvironment


class OneHourE2BEnvironment(ReconnectingE2BEnvironment):
    """Harbor E2B environment with the account-compatible one-hour timeout."""

    SANDBOX_TIMEOUT_SECONDS = 3_600

    @retry(
        stop=stop_after_attempt(2),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        reraise=True,
    )
    @override
    async def _create_sandbox(self):
        metadata = {
            "environment_name": self.environment_name,
            "session_id": self.session_id,
        }

        self._sandbox = await AsyncSandbox.create(
            template=self._template_name,
            metadata=metadata,
            envs=self._startup_env(),
            timeout=self.SANDBOX_TIMEOUT_SECONDS,
            allow_internet_access=(
                self.network_policy.network_mode != NetworkMode.NO_NETWORK
            ),
            network=self._sandbox_create_network_options(),
        )
