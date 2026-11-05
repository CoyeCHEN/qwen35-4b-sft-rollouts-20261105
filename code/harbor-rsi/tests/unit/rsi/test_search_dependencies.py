from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from harbor.agents.installed.base import NonZeroAgentExitCodeError
from harbor.agents.installed.open_harness import OpenHarnessAgent


def agent(tmp_path):
    return OpenHarnessAgent(
        logs_dir=tmp_path / "logs",
        model_name="deepseek/deepseek-flash",
        wheel_path=str(tmp_path / "candidate.whl"),
    )


def result(code=0):
    return SimpleNamespace(return_code=code, stdout="", stderr="")


@pytest.mark.asyncio
async def test_existing_tools_still_receive_final_probe(tmp_path):
    subject = agent(tmp_path)
    subject.ensure_system_dependencies = AsyncMock()
    environment = SimpleNamespace(exec=AsyncMock(return_value=result()))
    await subject._ensure_search_dependencies(environment)
    subject.ensure_system_dependencies.assert_not_awaited()
    assert environment.exec.await_count == 2
    assert "command -v fdfind" in environment.exec.await_args_list[0].kwargs["command"]
    assert "--no-require-git" in environment.exec.await_args_list[-1].kwargs["command"]


@pytest.mark.asyncio
async def test_missing_tools_use_existing_apt_mapping(tmp_path):
    subject = agent(tmp_path)
    subject._get_system_package_manager = AsyncMock(return_value="apt-get")
    environment = SimpleNamespace(
        exec=AsyncMock(side_effect=[result(1), result(), result()])
    )
    await subject._ensure_search_dependencies(environment)
    install = environment.exec.await_args_list[1].kwargs["command"]
    assert "apt-get install -y ripgrep fd-find" in install
    assert environment.exec.await_args_list[1].kwargs["user"] == "root"


@pytest.mark.asyncio
async def test_no_manager_does_not_silently_leave_tools_missing(tmp_path):
    subject = agent(tmp_path)
    subject._get_system_package_manager = AsyncMock(return_value=None)
    environment = SimpleNamespace(exec=AsyncMock(return_value=result(1)))
    with pytest.raises(NonZeroAgentExitCodeError):
        await subject._ensure_search_dependencies(environment)


@pytest.mark.asyncio
async def test_failed_install_propagates(tmp_path):
    subject = agent(tmp_path)
    subject._get_system_package_manager = AsyncMock(return_value="apk")
    environment = SimpleNamespace(exec=AsyncMock(return_value=result(1)))
    with pytest.raises(NonZeroAgentExitCodeError):
        await subject._ensure_search_dependencies(environment)
    assert (
        "apk add --no-cache ripgrep fd"
        in environment.exec.await_args_list[-1].kwargs["command"]
    )


@pytest.mark.asyncio
async def test_installed_fd_with_unsupported_flags_fails_before_agent(tmp_path):
    subject = agent(tmp_path)
    environment = SimpleNamespace(exec=AsyncMock(side_effect=[result(), result(2)]))
    with pytest.raises(NonZeroAgentExitCodeError):
        await subject._ensure_search_dependencies(environment)


@pytest.mark.asyncio
async def test_host_prepared_fd_is_verified_uploaded_and_installed(tmp_path):
    import hashlib

    source = tmp_path / "fd"
    source.write_bytes(b"fixed-static-fd")
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    subject = OpenHarnessAgent(
        logs_dir=tmp_path / "logs",
        model_name="deepseek/deepseek-flash",
        wheel_path=str(tmp_path / "candidate.whl"),
        bootstrap_fd_path=str(source),
        bootstrap_fd_sha256=digest,
    )
    subject.ensure_system_dependencies = AsyncMock()
    environment = SimpleNamespace(
        exec=AsyncMock(return_value=result()), upload_file=AsyncMock()
    )
    await subject._ensure_search_dependencies(environment)
    subject.ensure_system_dependencies.assert_awaited_once_with(
        environment, ("ripgrep",)
    )
    environment.upload_file.assert_awaited_once()
    command = environment.exec.await_args_list[0].kwargs["command"]
    assert (
        digest in command
        and "sha256sum -c -" in command
        and "install -m 755" in command
    )


@pytest.mark.asyncio
async def test_changed_bootstrap_fd_is_rejected_before_upload(tmp_path):
    source = tmp_path / "fd"
    source.write_bytes(b"changed")
    subject = OpenHarnessAgent(
        logs_dir=tmp_path / "logs",
        model_name="deepseek/deepseek-flash",
        wheel_path=str(tmp_path / "candidate.whl"),
        bootstrap_fd_path=str(source),
        bootstrap_fd_sha256="0" * 64,
    )
    environment = SimpleNamespace(exec=AsyncMock(), upload_file=AsyncMock())
    with pytest.raises(ValueError, match="SHA256"):
        await subject._ensure_search_dependencies(environment)
    environment.exec.assert_not_awaited()
    environment.upload_file.assert_not_awaited()


@pytest.mark.parametrize(
    "options",
    [{"bootstrap_fd_path": "/missing/fd"}, {"bootstrap_fd_sha256": "0" * 64}],
)
def test_bootstrap_fd_requires_path_and_digest_together(tmp_path, options):
    with pytest.raises(ValueError, match="must be supplied together"):
        OpenHarnessAgent.preflight(
            {"wheel_path": str(tmp_path / "candidate.whl"), **options}
        )
