"""Native installed-agent smoke that installs the real wheel without model calls."""

import shlex
from typing import override

from harbor.agents.installed.open_harness import OpenHarnessAgent
from harbor.environments.base import BaseEnvironment
from harbor.models.agent.context import AgentContext


class InstallOnlyFixture(OpenHarnessAgent):
    @override
    async def run(
        self,
        instruction: str,
        environment: BaseEnvironment,
        context: AgentContext,
    ) -> None:
        result = await self.exec_as_agent(
            environment,
            f"test -x {shlex.quote(self._remote_cli)} && "
            f"{shlex.quote(self._remote_venv + '/bin/python')} -c "
            "'import importlib.metadata as m; "
            'd=m.distribution("open-harness-ai"); '
            'assert any(e.name=="open-harness" and e.value=="cli:main" '
            "for e in d.entry_points); print(d.version)'",
            timeout_sec=20,
        )
        if result.return_code:
            raise RuntimeError(f"Installed CLI contract probe failed: {result.stderr}")
        context.metadata = {
            "model_called": False,
            "installed_cli_contract": "open-harness = cli:main",
            "version_output": (result.stdout or "").strip(),
        }


class FixedSubmissionFixture(InstallOnlyFixture):
    """Submit a generic text artifact so a native Judge can exercise its API.

    This fixture contains no task solution and never calls an agent model.
    Judge calls remain real, separately authorized and observable.
    """

    @override
    async def run(
        self,
        instruction: str,
        environment: BaseEnvironment,
        context: AgentContext,
    ) -> None:
        await super().run(instruction, environment, context)
        result = await self.exec_as_agent(
            environment,
            "mkdir -p output && printf '%s\\n' "
            "'Readiness fixture: no task-specific answer.' > output/readiness.txt",
            timeout_sec=20,
        )
        if result.return_code:
            raise RuntimeError(f"Fixed artifact creation failed: {result.stderr}")
        if context.metadata is None:
            context.metadata = {}
        context.metadata["submission_fixture"] = "generic-text-without-task-solution"
