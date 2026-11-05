"""Offline lifecycle fixtures, importable on every host platform.

LocalEnvironment executes Linux shell fixtures and is used only by Linux tests.
FakeAgent also supports mocked environments in portable Trial contract tests.
"""

import asyncio
import os
import shutil
from types import SimpleNamespace

from harbor.agents.installed.base import BaseInstalledAgent


class LocalEnvironment:
    default_user = None

    def __init__(self, cwd):
        self.cwd = cwd
        self.agent_runtime_dir = cwd
        self.calls = []

    async def upload_file(self, source_path, target_path):
        shutil.copyfile(source_path, target_path)

    async def exec(self, command, user=None, env=None, cwd=None, timeout_sec=None):
        self.calls.append({"command": command, "user": user, "cwd": cwd, "env": env})
        process = await asyncio.create_subprocess_exec(
            "bash",
            "-c",
            command,
            cwd=cwd or self.cwd,
            env={**os.environ, **(env or {})},
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        out, err = await process.communicate()
        return SimpleNamespace(
            stdout=out.decode(), stderr=err.decode(), return_code=process.returncode
        )


class FakeAgent(BaseInstalledAgent):
    @staticmethod
    def name():
        return "lifecycle-test"

    async def install(self, environment):
        pass

    async def run(self, instruction, environment, context):
        await self.exec_as_agent(environment, instruction)
