"""Native Harbor contracts using a real, offline CLI wheel and local transports.

These transports only execute trusted test fixtures; they are not sandboxes.
"""

import asyncio
import hashlib
import json
import os
import re
import shutil
import signal
import sys
import tempfile
import zipfile
from pathlib import Path

import pytest

from harbor.environments.base import BaseEnvironment, ExecResult
from harbor.environments.capabilities import EnvironmentCapabilities
from harbor.job import Job
from harbor.models.job.config import JobConfig
from harbor.models.trial.config import (
    AgentConfig,
    EnvironmentConfig,
    TaskConfig,
    TrialConfig,
    VerifierConfig,
)
from harbor.models.trial.result import TrialResult
from harbor.publisher.packager import Packager
from tests.unit.test_trial_cleanup import MountedEnvironment

pytestmark = pytest.mark.skipif(
    sys.platform != "linux",
    reason="Local transport runs Linux shell and process fixtures",
)


class FixtureTransport:
    instances = []

    def __init__(self, *args, fail_start=False, fail_stop=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.root = self.trial_paths.trial_dir / "fixture-root"
        self.fail_start, self.fail_stop = fail_start, fail_stop
        self.stopped = False
        self.calls = []
        self.instances.append(self)

    def path(self, path):
        value = str(path)
        if value.startswith(str(self.root)):
            return Path(value)
        return self.root / value.lstrip("/")

    def translate(self, command):
        return re.sub(
            r"/(?:tmp/harbor-[^\s'\";<>]+|logs(?:/[^\s'\";<>]*)?|tests(?:/[^\s'\";<>]*)?|installed-agent)",
            lambda match: str(self.path(match[0])),
            command,
        )

    async def start(self, force_build):
        self.calls.append("start")
        if self.fail_start:
            raise RuntimeError("injected provider start failure")
        (self.root / "work").mkdir(parents=True)
        bin_dir = self.root / "bin"
        bin_dir.mkdir(parents=True, exist_ok=True)
        python_link = bin_dir / "python3.12"
        if not python_link.exists():
            python_link.symlink_to(sys.executable)
        shutil.copytree(self.environment_dir, self.root / "work", dirs_exist_ok=True)
        for name in (
            "tmp",
            "tmp/harbor-agent-runtime",
            "logs/agent",
            "logs/verifier",
            "logs/artifacts",
        ):
            self.path(name).mkdir(parents=True, exist_ok=True)
        if self.capabilities.mounted:
            for mount in self._mounts:
                target = self.path(mount["target"])
                if target.exists():
                    target.rmdir()
                source = Path(mount["source"])
                source.mkdir(parents=True, exist_ok=True)
                target.symlink_to(source, target_is_directory=True)

    async def stop(self, delete):
        self.calls.append("stop")
        if self.fail_stop:
            raise RuntimeError("injected provider cleanup failure")
        self.stopped = True

    async def upload_file(self, source_path, target_path):
        self.calls.append("upload_file")
        target = self.path(target_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source_path, target)

    async def upload_dir(self, source_dir, target_dir):
        self.calls.append("upload_dir")
        shutil.copytree(source_dir, self.path(target_dir), dirs_exist_ok=True)

    async def download_file(self, source_path, target_path):
        self.calls.append("download_file")
        Path(target_path).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(self.path(source_path), target_path)

    async def download_dir(self, source_dir, target_dir):
        self.calls.append("download_dir")
        shutil.copytree(self.path(source_dir), target_dir, dirs_exist_ok=True)

    async def exec(self, command, cwd=None, env=None, timeout_sec=None, user=None):
        self.calls.append("exec")
        process = await asyncio.create_subprocess_exec(
            "bash",
            "-c",
            self.translate(command),
            cwd=str(self.path(cwd) if cwd else self.root / "work"),
            env={
                "PATH": f"{self.root / 'bin'}:{os.environ['PATH']}",
                "HOME": str(self.root),
                **(env or {}),
            },
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            start_new_session=True,
        )
        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout_sec)
        except BaseException:
            if process.returncode is None:
                os.killpg(process.pid, signal.SIGKILL)
            await process.communicate()
            raise
        return ExecResult(
            stdout=stdout.decode(),
            stderr=stderr.decode(),
            return_code=process.returncode,
        )


async def _install_fixture_cli(self, environment):
    """Install the generated wheel without depending on distro ``ensurepip``.

    The test still uploads and executes the wheel through the real
    ``OpenHarnessAgent.run`` path.  A tiny launcher is enough here because the
    fixture wheel has no third-party dependencies; exercising Debian's package
    manager would make this contract test depend on the host image.
    """
    self.preflight(self.options.model_dump())
    self._configure_runtime_paths(environment)
    wheel = Path(self.options.wheel_path).expanduser().resolve()
    remote = f"/tmp/{wheel.name}"
    local_remote = environment.path(remote)
    await environment.upload_file(wheel, remote)
    with tempfile.TemporaryDirectory(prefix="fixture-cli-") as directory:
        launcher = Path(directory) / "open-harness"
        launcher.write_text(
            "#!/usr/bin/env python3\n"
            "import sys\n"
            f"sys.path.insert(0, {str(local_remote)!r})\n"
            "sys.argv[0] = 'open-harness'\n"
            "from fixture_cli import main\n"
            "main()\n"
        )
        launcher.chmod(0o755)
        await environment.upload_file(launcher, self._remote_cli)
    await environment.exec(f"chmod 755 {self._remote_cli}")
    self.logs_dir.mkdir(parents=True, exist_ok=True)
    (self.logs_dir / "artifact.json").write_text(
        json.dumps(
            {
                "wheel_sha256": hashlib.sha256(wheel.read_bytes()).hexdigest(),
                "cli_contract": self.options.cli_contract,
                "profile": self.options.profile,
            },
            indent=2,
        )
        + "\n"
    )


class MountedFixtureEnvironment(FixtureTransport, MountedEnvironment):
    """Extend Harbor's existing mounted test facility with real fixture I/O."""


class CustomFixtureEnvironment(FixtureTransport, BaseEnvironment):
    @staticmethod
    def type():
        return "fixture"

    @property
    def capabilities(self):
        return EnvironmentCapabilities()

    def _validate_definition(self):
        pass


@pytest.fixture
def native_inputs(tmp_path):
    wheel = tmp_path / "open_harness_fixture-1.0-py3-none-any.whl"
    dist = "open_harness_fixture-1.0.dist-info"
    cli = """import json, os, pathlib, sys, time
def main():
    if "--version" in sys.argv:
        print("1.0")
        return
    args = sys.argv
    prompt = pathlib.Path(args[args.index("--prompt-file") + 1]).read_bytes()
    pathlib.Path("received-instruction.txt").write_bytes(prompt)
    if os.environ.get("FIXTURE_HANG"):
        pathlib.Path("entered").touch()
        time.sleep(60)
    code = int(os.environ.get("FIXTURE_EXIT", "0"))
    if not code:
        pathlib.Path("output.bin").write_bytes(pathlib.Path("nested/input.bin").read_bytes())
    print(json.dumps({"type":"message_end","message":{"role":"assistant","content":[{"type":"text","text":"done"}],"usage":{"input":1,"output":1}}}))
    print("fixture stderr", file=sys.stderr)
    raise SystemExit(code)
"""
    members = {
        "fixture_cli.py": cli,
        f"{dist}/METADATA": "Metadata-Version: 2.1\nName: open-harness-fixture\nVersion: 1.0\nRequires-Python: >=3.11\n",
        f"{dist}/WHEEL": "Wheel-Version: 1.0\nGenerator: fixture\nRoot-Is-Purelib: true\nTag: py3-none-any\n",
        f"{dist}/entry_points.txt": "[console_scripts]\nopen-harness = fixture_cli:main\n",
    }
    members[f"{dist}/RECORD"] = "".join(
        f"{name},,\n" for name in [*members, f"{dist}/RECORD"]
    )
    with zipfile.ZipFile(wheel, "w") as archive:
        for name, content in members.items():
            archive.writestr(name, content)
    task = tmp_path / "task"
    (task / "environment/nested").mkdir(parents=True)
    (task / "tests").mkdir()
    (task / "task.toml").write_text(
        "[agent]\ntimeout_sec = 10\n[verifier]\ntimeout_sec = 5\n[environment]\n"
    )
    (task / "instruction.md").write_text(
        "Copy nested/input.bin to output.bin.\nKeep literal '$HOME'.\n"
    )
    (task / "environment/Dockerfile").write_text(
        "FROM python:3.12\nWORKDIR /work\nCOPY . /work\n"
    )
    (task / "environment/nested/input.bin").write_bytes(bytes(range(256)) * 16384)
    (task / "tests/test.sh").write_text(
        "#!/bin/bash\nif cmp nested/input.bin output.bin; then echo 1; else echo 0; fi > ../logs/verifier/reward.txt\n"
    )
    FixtureTransport.instances.clear()
    return task, wheel


def native_config(tmp_path, inputs, provider="CustomFixtureEnvironment", **agent_env):
    task, wheel = inputs
    return JobConfig(
        job_name="native",
        jobs_dir=tmp_path / "jobs",
        quiet=True,
        tasks=[TaskConfig(path=task)],
        agents=[
            AgentConfig(
                name="open-harness",
                model_name="deepseek/fixture",
                kwargs={
                    "wheel_path": str(wheel),
                    "wheel_sha256": hashlib.sha256(wheel.read_bytes()).hexdigest(),
                },
                env={
                    "DEEPSEEK_API_KEY": "fixture-only",
                    "PIP_NO_INDEX": "1",
                    **agent_env,
                },
            )
        ],
        environment=EnvironmentConfig(
            import_path=f"tests.unit.rsi.test_native_job:{provider}"
        ),
    )


@pytest.mark.parametrize(
    "provider", ["MountedFixtureEnvironment", "CustomFixtureEnvironment"]
)
@pytest.mark.parametrize("exit_code", [0, 7])
async def test_native_job_with_real_cli_and_verifier(
    tmp_path, native_inputs, provider, exit_code, monkeypatch
):
    from harbor.agents.installed.open_harness import OpenHarnessAgent

    monkeypatch.setattr(OpenHarnessAgent, "install", _install_fixture_cli)
    task, _ = native_inputs
    before = Packager.compute_content_hash(task)[0]
    job = await Job.create(
        native_config(tmp_path, native_inputs, provider, FIXTURE_EXIT=str(exit_code))
    )
    result = await job.run()
    trial = result.trial_results[0]
    assert trial.verifier_result.rewards == {"reward": float(exit_code == 0)}
    assert (trial.exception_info is None) == (exit_code == 0)
    if exit_code:
        assert trial.exception_info.exception_type == "NonZeroAgentExitCodeError"
    directory = job.job_dir / trial.trial_name
    marker = json.loads((directory / "agent/open-harness.complete.json").read_text())
    assert marker["exit_code"] == exit_code
    assert (
        directory / "agent/open-harness.stderr.log"
    ).read_text() == "fixture stderr\n"
    assert before == Packager.compute_content_hash(task)[0]
    assert trial.task_checksum
    assert trial.config.task.path == task
    assert not (job.job_dir.parent / ".rsi").exists()
    assert (directory / "fixture-root/work/received-instruction.txt").read_bytes() == (
        task / "instruction.md"
    ).read_bytes()
    assert (
        TrialResult.model_validate_json((directory / "result.json").read_text())
        == trial
    )


async def test_recovery_failure_is_confined_to_one_trial(tmp_path, monkeypatch):
    from unittest.mock import AsyncMock
    from harbor.models.trial.config import TrialConfig, VerifierConfig
    from harbor.trial.trial import Trial
    from tests.unit.test_trial_cleanup import _create_task_dir

    task = _create_task_dir(tmp_path)
    trials = [
        await Trial.create(
            TrialConfig(
                task=TaskConfig(path=task),
                trial_name=name,
                trials_dir=tmp_path / "trials",
                agent=AgentConfig(
                    import_path="tests.unit.test_trial_cleanup:QuickAgent"
                ),
                environment=EnvironmentConfig(
                    import_path="tests.unit.test_trial_cleanup:MountedEnvironment"
                ),
                verifier=VerifierConfig(disable=True),
            )
        )
        for name in ("broken", "healthy")
    ]
    trials[0].agent_environment.start = AsyncMock(
        side_effect=RuntimeError("start failed")
    )
    trials[0]._recover_outputs = AsyncMock(side_effect=RuntimeError("recovery failed"))
    async with asyncio.TaskGroup() as group:
        futures = [group.create_task(trial.run()) for trial in trials]
    assert futures[0].result().exception_info.exception_message == "start failed"
    assert futures[1].result().exception_info is None
    assert trials[0].agent_environment.stop_call_count == 1
    assert trials[0].paths.result_path.exists()


async def test_provider_cleanup_failure_is_persisted_on_own_trial(tmp_path):
    from unittest.mock import AsyncMock
    from harbor.trial.trial import Trial
    from tests.unit.test_trial_cleanup import _create_task_dir

    task = _create_task_dir(tmp_path)
    trial = await Trial.create(
        TrialConfig(
            task=TaskConfig(path=task),
            trial_name="cleanup-failure",
            trials_dir=tmp_path / "trials",
            agent=AgentConfig(import_path="tests.unit.test_trial_cleanup:QuickAgent"),
            environment=EnvironmentConfig(
                import_path="tests.unit.test_trial_cleanup:MountedEnvironment"
            ),
            verifier=VerifierConfig(disable=True),
        )
    )
    trial.agent_environment.stop = AsyncMock(side_effect=RuntimeError("stop failed"))

    result = await trial.run()

    assert result.exception_info is not None
    assert result.exception_info.exception_message == "stop failed"
    assert result.failure_phase == "cleanup"
    assert [error.phase for error in result.infrastructure_errors] == ["cleanup"]
    assert (
        TrialResult.model_validate_json(trial.paths.result_path.read_text())
        .infrastructure_errors[0]
        .phase
        == "cleanup"
    )
