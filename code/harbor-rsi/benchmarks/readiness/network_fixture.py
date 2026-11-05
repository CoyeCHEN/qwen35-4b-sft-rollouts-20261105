"""Read-only egress proof in the actual native Task sandbox; never call an Actor."""

import json
import shlex
from typing import override
from urllib.parse import urlsplit

from pydantic import Field, field_validator

from benchmarks.readiness.installed_fixture import InstallOnlyFixture
from harbor.agents.installed.open_harness import OpenHarnessOptions
from harbor.environments.base import BaseEnvironment
from harbor.models.agent.context import AgentContext


def probe_program(urls: list[str]) -> str:
    if not 1 <= len(urls) <= 8:
        raise ValueError("Declare between one and eight read-only endpoints")
    for url in urls:
        parsed = urlsplit(url)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
            or parsed.port not in {None, 443}
        ):
            raise ValueError("Probe URLs must be literal HTTPS without credentials")
    return (
        "import json,urllib.request\n"
        "rows=[]\n"
        f"for url in {urls!r}:\n"
        " row={'requested_url':url}\n"
        " try:\n"
        "  with urllib.request.urlopen(urllib.request.Request(url,method='HEAD'),timeout=5) as response:\n"
        "   row['status']=response.status\n"
        " except Exception as error:row['exception']=type(error).__name__\n"
        " rows.append(row)\n"
        "print(json.dumps(rows))\n"
    )


class EgressOptions(OpenHarnessOptions):
    probe_urls: list[str] = Field(min_length=1, max_length=8)

    @field_validator("probe_urls")
    @classmethod
    def validate_probe_urls(cls, urls: list[str]) -> list[str]:
        probe_program(urls)
        return urls


class EgressFixture(InstallOnlyFixture):
    """Install the frozen CLI and check declared metadata endpoints via HEAD."""

    options_model = EgressOptions
    options: EgressOptions

    @override
    async def run(
        self,
        instruction: str,
        environment: BaseEnvironment,
        context: AgentContext,
    ) -> None:
        await super().run(instruction, environment, context)
        urls = self.options.probe_urls
        program = probe_program(urls)
        result = await self.exec_as_agent(
            environment,
            f"{shlex.quote(self._remote_venv + '/bin/python')} -c {shlex.quote(program)}",
            timeout_sec=7 * len(urls) + 5,
        )
        rows = json.loads(result.stdout or "[]") if not result.return_code else []
        if context.metadata is None:
            context.metadata = {}
        context.metadata["read_only_egress"] = rows
        if len(rows) != len(urls) or any(row.get("status") != 200 for row in rows):
            raise RuntimeError("Required read-only endpoint check failed")
