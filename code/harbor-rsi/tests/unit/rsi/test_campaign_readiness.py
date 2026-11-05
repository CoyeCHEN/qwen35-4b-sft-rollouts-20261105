"""Campaign gates must fail before dispatch and must not interpret rewards."""

import json
import os
import subprocess
import shutil
import sys
import time
from contextlib import asynccontextmanager, nullcontext
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

from harbor.extensions.rsi import readiness as gate
from harbor.models.task.config import NetworkMode
from harbor.models.trial.config import AgentConfig, TrialConfig


@pytest.fixture
def task(tmp_path):
    root = tmp_path / "task"
    (root / "environment").mkdir(parents=True)
    (root / "tests").mkdir()
    (root / "task.toml").write_text(
        '[task]\nname="fixture/plain"\n[environment]\ncpus=1\nmemory_mb=128\n'
    )
    (root / "instruction.md").write_text("Write an answer.\n")
    (root / "environment/Dockerfile").write_text("FROM fixture:immutable\n")
    (root / "tests/test.sh").write_text(
        "#!/bin/sh\necho 0 > /logs/verifier/reward.txt\n"
    )
    return root


@pytest.fixture
def contract():
    return {
        "basis": "Reviewed fixture initial environment; installing the answer remains agent work.",
        "coverage": {
            key: {
                "reason": "No additional dependency in this reviewed fixture.",
                "not_required": True,
            }
            for key in gate.CATEGORIES
        },
        "checks": [],
    }


@pytest.fixture
def raw(task):
    return TrialConfig(
        task={"path": task}, agent={"name": "nop"}, environment={"type": "docker"}
    ).model_dump(mode="json")


@pytest.fixture
def fake_dispatch_identity(monkeypatch):
    # These native Job fakes must not query the host's Linux /proc identity.
    monkeypatch.setattr(
        gate,
        "process_identity",
        lambda pid: {
            "hostname": "fixture-host",
            "pid": pid,
            "boot_id": "fixture-boot",
            "start_ticks": "fixture-start",
        },
    )


def test_contract_must_review_all_dimensions(contract):
    gate.Contract.model_validate(contract)
    del contract["coverage"]["verifier"]
    with pytest.raises(ValidationError, match="Review"):
        gate.Contract.model_validate(contract)


def test_contract_rejects_undefined_or_wrong_category_checks(contract):
    contract["coverage"]["runtime"] = {
        "reason": "Promised Python runtime must import.",
        "checks": ["imports"],
    }
    with pytest.raises(ValidationError, match="Coverage"):
        gate.Contract.model_validate(contract)


def test_profile_replaces_environment_not_merges_top_level(task):
    trial = TrialConfig(
        task={"path": task},
        environment={"type": "docker", "env": {"TOP": "not-effective"}},
        agent={"name": "nop", "env": {"BASE": "retained"}},
    )
    gate.apply_profiles(
        [trial],
        {
            "fixture/plain": {
                "environment": {"type": "docker", "env": {"ACTUAL": "yes"}},
                "verifier": {"env": {"VERIFIER": "yes"}},
                "agent_env": {"HTTP_PROXY": "http://proxy:8080"},
            }
        },
    )
    assert trial.environment.env == {"ACTUAL": "yes"}
    assert trial.agent.env == {"BASE": "retained", "HTTP_PROXY": "http://proxy:8080"}
    assert trial.verifier.env == {"VERIFIER": "yes"}


def test_profile_coverage_is_exact(task):
    with pytest.raises(ValueError, match="exactly"):
        gate.apply_profiles([TrialConfig(task={"path": task})], {"wrong/task": {}})


async def test_profile_deadlines_reach_native_trial_without_changing_task_limits(
    task, tmp_path
):
    from harbor.models.task.task import Task
    from harbor.trial.trial import Trial

    task_file = task / "task.toml"
    task_file.write_text(
        task_file.read_text()
        + "[agent]\ntimeout_sec=12000\n[verifier]\ntimeout_sec=900\n"
    )
    short_task = tmp_path / "short-task"
    shutil.copytree(task, short_task)
    short_file = short_task / "task.toml"
    short_file.write_text(
        short_file.read_text()
        .replace("fixture/plain", "fixture/short")
        .replace("timeout_sec=12000", "timeout_sec=900")
    )
    roots = (task, short_task)
    before = {
        p: p.read_bytes() for root in roots for p in root.rglob("*") if p.is_file()
    }
    template = AgentConfig(name="nop", override_timeout_sec=10800)
    configs = [
        TrialConfig(
            task={"path": root},
            agent=template,
            trial_name=f"profile-{i}",
            trials_dir=tmp_path / "trials",
            environment={
                "import_path": "tests.unit.test_trial_cleanup:MountedEnvironment"
            },
        )
        for i, root in enumerate(roots)
    ]
    profile = {
        "environment": configs[0].environment.model_dump(mode="json"),
        "verifier": {},
        "agent_env": {},
        "agent_timeout_sec": 12000,
    }
    gate.apply_profiles(
        configs,
        {
            Task(task).name: profile,
            Task(short_task).name: {
                k: v for k, v in profile.items() if k != "agent_timeout_sec"
            },
        },
    )
    longer, default = [await Trial.create(cfg) for cfg in configs]
    try:
        assert longer._agent_timeout_sec == 12000
        assert default._agent_timeout_sec == 10800
        assert longer._verifier_timeout_sec == default._verifier_timeout_sec == 900
        assert (
            configs[1].agent.override_timeout_sec
            == template.override_timeout_sec
            == 10800
        )
        assert before == {
            p: p.read_bytes() for root in roots for p in root.rglob("*") if p.is_file()
        }
    finally:
        longer._close_logger_handler()
        default._close_logger_handler()


@pytest.mark.parametrize(
    "timeout", [None, True, 0, -1, "12000", float("nan"), float("inf")]
)
def test_profile_deadline_must_be_explicit_and_valid(task, timeout):
    trial = TrialConfig(task={"path": task}, agent={"name": "nop"})
    with pytest.raises(ValueError, match="finite and positive"):
        gate.apply_profiles(
            [trial],
            {
                "fixture/plain": {
                    "environment": {},
                    "verifier": {},
                    "agent_env": {},
                    "agent_timeout_sec": timeout,
                }
            },
        )


def test_unknown_profile_fields_cannot_silently_drop_a_deadline(task):
    trial = TrialConfig(task={"path": task}, agent={"name": "nop"})
    with pytest.raises(ValueError, match="Unsupported task profile fields"):
        gate.apply_profiles(
            [trial],
            {
                "fixture/plain": {
                    "environment": {},
                    "verifier": {},
                    "agent_env": {},
                    "agent_timeout_typo": 12000,
                }
            },
        )


def test_compose_interpolation_freezes_unbraced_variables_but_not_escaped_dollars():
    assert gate.compose_variables(
        "$PROXY ${NO_PROXY:-localhost} $$LITERAL $${ESCAPED} $$$EXPANDED"
    ) == {"PROXY", "NO_PROXY", "EXPANDED"}


def test_execution_dump_preserves_public_git_keys_but_credentials_require_references(
    task,
):
    trial = TrialConfig(
        task={"path": task},
        agent={"name": "nop"},
        verifier={
            "env": {
                "GIT_CONFIG_KEY_0": "http.version",
                "GIT_CONFIG_VALUE_0": "HTTP/1.1",
            }
        },
    )
    gate.check_env_references([trial])
    replay = TrialConfig.model_validate(gate.execution_dump(trial))
    assert replay.verifier.env == trial.verifier.env
    trial.agent.env = {"DEEPSEEK_API_KEY": "not-a-real-test-credential"}
    with pytest.raises(ValueError, match="inherited"):
        gate.check_env_references([trial])
    trial.agent.env = {"DEEPSEEK_API_KEY": "${DEEPSEEK_API_KEY}"}
    gate.check_env_references([trial])


def test_overlay_task_wheel_cache_and_compose_variables_are_frozen(
    raw, contract, tmp_path, monkeypatch
):
    monkeypatch.setattr(gate, "code_identity", lambda: {"code": "fixed"})
    overlay = tmp_path / "overlay.yaml"
    overlay.write_text(
        'services:\n  main:\n    environment:\n      HTTP_PROXY: "${TEST_READINESS_PROXY}"\n'
    )
    wheel, cache = tmp_path / "fixture.whl", tmp_path / "cache-manifest.json"
    wheel.write_bytes(b"wheel")
    cache.write_text('{"revision":"one"}')
    raw["environment"]["extra_docker_compose"] = [str(overlay)]
    raw["agent"]["kwargs"] = {"wheel_path": str(wheel)}
    contract["inputs"] = [str(cache)]
    contracts = {"fixture/plain": contract}
    before = gate.identity([raw], contracts)
    monkeypatch.setenv("TEST_READINESS_PROXY", "http://changed:8080")
    assert gate.identity([raw], contracts) != before
    before = gate.identity([raw], contracts)
    for path in [overlay, wheel, cache]:
        original = path.read_bytes()
        path.write_bytes(original + b" ")
        assert gate.identity([raw], contracts) != before
        path.write_bytes(original)
    (
        gate.TrialConfig.model_validate(raw).task.get_local_path() / "instruction.md"
    ).write_text("changed task")
    assert gate.identity([raw], contracts) != before


def test_external_compose_env_file_drift_invalidates_readiness(
    raw, contract, tmp_path, monkeypatch
):
    monkeypatch.setattr(gate, "code_identity", lambda: {"code": "fixed"})
    env_file = tmp_path / "runtime.env"
    env_file.write_text("PUBLIC_OPTION=one\n")
    overlay = tmp_path / "overlay.yaml"
    overlay.write_text(
        "services:\n  main:\n    build: !reset null\n    env_file: runtime.env\n"
    )
    raw["environment"]["extra_docker_compose"] = [str(overlay)]
    before = gate.identity([raw], {"fixture/plain": contract})
    env_file.write_text("PUBLIC_OPTION=two\n")
    assert gate.identity([raw], {"fixture/plain": contract}) != before
    overlay.write_text("include: other.yaml\n")
    with pytest.raises(ValueError, match="flattened"):
        gate.identity([raw], {"fixture/plain": contract})


@pytest.mark.parametrize("scope", ["env", "install_env"])
def test_inherited_credential_drift_is_hashed_without_persisting_value(
    raw, contract, monkeypatch, scope
):
    monkeypatch.setattr(gate, "code_identity", lambda: {"code": "fixed"})
    if scope == "env":
        raw["agent"]["env"] = {"DEEPSEEK_API_KEY": "${DEEPSEEK_API_KEY}"}
    else:
        raw["agent"]["kwargs"]["install_env"] = {
            "DEEPSEEK_API_KEY": "${DEEPSEEK_API_KEY}"
        }
    monkeypatch.setenv("DEEPSEEK_API_KEY", "fixture-secret-one")
    before = gate.identity([raw], {"fixture/plain": contract})
    assert "fixture-secret-one" not in json.dumps(before)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "fixture-secret-two")
    assert gate.identity([raw], {"fixture/plain": contract}) != before


def test_status_distinguishes_missing_check_from_failure():
    assert gate.status([]) == "UNVERIFIED"
    assert gate.status([{"status": "UNVERIFIED"}, {"status": "READY"}]) == "UNVERIFIED"
    assert gate.status([{"status": "UNVERIFIED"}, {"status": "BLOCKED"}]) == "BLOCKED"


async def test_exit_failure_and_timeout_never_become_rewards():
    check = gate.Check(
        id="import",
        category="runtime",
        command="python -c 'import promised'",
        timeout_sec=1,
    )
    env = SimpleNamespace(
        exec=AsyncMock(
            return_value=SimpleNamespace(
                return_code=1, stdout="", stderr="ModuleNotFoundError"
            )
        )
    )
    row = await gate.execute(env, check, {})
    assert row["status"] == "BLOCKED" and row["exit_code"] == 1
    assert "reward" not in row
    env.exec.side_effect = TimeoutError("bounded probe")
    row = await gate.execute(env, check, {})
    assert row["status"] == "BLOCKED" and row["error_type"] == "TimeoutError"


@pytest.fixture
def fake_trial(task, monkeypatch):
    @asynccontextmanager
    async def phase(*args, **kwargs):
        yield

    env = SimpleNamespace(
        start=AsyncMock(),
        stop=AsyncMock(),
        upload_dir=AsyncMock(),
        exec=AsyncMock(
            return_value=SimpleNamespace(return_code=0, stdout="ok", stderr="")
        ),
        scoped_exec_env=lambda _: nullcontext(),
    )
    plan = SimpleNamespace(
        agent_phase=SimpleNamespace(network_mode=NetworkMode.NO_NETWORK),
        verifier_phase=SimpleNamespace(network_mode=NetworkMode.NO_NETWORK),
        agent_env_baseline=None,
        verifier_env_baseline=None,
    )
    native_task = gate.Task(task)
    trial = SimpleNamespace(
        agent_environment=env,
        task=native_task,
        paths=SimpleNamespace(trial_dir=task.parent / "probe-output"),
        agent=SimpleNamespace(setup=AsyncMock(), extra_env={}),
        _network_plan=lambda: plan,
        _phase_network_policy=phase,
        _environment_build_timeout_sec=10,
        _agent_setup_timeout_sec=10,
        _close_logger_handler=lambda: None,
    )
    monkeypatch.setattr(gate.Trial, "create", AsyncMock(return_value=trial))
    monkeypatch.setattr(
        gate,
        "attestation",
        AsyncMock(
            return_value={
                "compose": {"name": "fixture-owned-project"},
                "services": {
                    "main": {"resources": {"NanoCpus": 10**9, "Memory": 128 * 1024**2}}
                },
            }
        ),
    )
    monkeypatch.setattr(gate, "docker", AsyncMock(return_value=""))
    monkeypatch.setattr(
        gate.Verifier,
        "_resolve_tests",
        lambda _: ([task / "tests"], task / "tests", task / "tests/test.sh"),
    )
    return trial


async def test_setup_precedes_phase_change_and_private_tests(
    raw, contract, fake_trial, tmp_path
):
    events = []

    async def setup(env):
        events.append("setup")
        env.upload_dir.assert_not_awaited()

    @asynccontextmanager
    async def phase(*args, **kwargs):
        events.append("phase")
        assert events[0] == "setup"
        yield

    fake_trial.agent.setup.side_effect = setup
    fake_trial._phase_network_policy = phase
    row = await gate.inspect_task(raw, contract, tmp_path / "validation", prepare=False)
    assert row["status"] == "READY", row
    fake_trial.agent.setup.assert_awaited_once()
    assert events == ["setup", "phase", "phase"]
    fake_trial.agent_environment.upload_dir.assert_awaited_once()


async def test_no_network_probe_is_never_executed_and_cleanup_happens(
    raw, contract, fake_trial, tmp_path
):
    contract["checks"] = [
        {
            "id": "network",
            "category": "network",
            "command": "curl https://forbidden.example",
            "timeout_sec": 1,
            "network": True,
        }
    ]
    contract["coverage"]["network"] = {
        "reason": "Required endpoint declared, but task disallows it.",
        "checks": ["network"],
    }
    row = await gate.inspect_task(raw, contract, tmp_path / "validation", prepare=False)
    assert row["status"] == "BLOCKED"
    assert not any(
        "forbidden" in call.args[0]
        for call in fake_trial.agent_environment.exec.call_args_list
    )
    fake_trial.agent_environment.stop.assert_awaited_once_with(delete=False)
    assert row["agent_run_called"] is False


async def test_missing_contract_and_skipped_setup_cannot_be_ready(
    raw, fake_trial, tmp_path
):
    row = await gate.inspect_task(
        raw, None, tmp_path / "validation", prepare=False, skip_agent=True
    )
    assert row["status"] == "UNVERIFIED", row
    fake_trial.agent.setup.assert_not_awaited()


async def test_skipped_agent_check_is_unverified_not_a_fabricated_missing_cli_failure(
    raw, contract, fake_trial, tmp_path
):
    contract["checks"] = [
        {
            "id": "cli",
            "category": "agent",
            "command": "missing-installed-cli",
            "timeout_sec": 1,
        }
    ]
    contract["coverage"]["agent"] = {
        "reason": "CLI requires the skipped agent setup.",
        "checks": ["cli"],
    }
    row = await gate.inspect_task(
        raw, contract, tmp_path / "validation", prepare=False, skip_agent=True
    )
    assert row["status"] == "UNVERIFIED"
    assert not any(
        "missing-installed-cli" in call.args[0]
        for call in fake_trial.agent_environment.exec.call_args_list
    )


async def test_cleanup_failure_blocks_even_after_success(
    raw, contract, fake_trial, tmp_path
):
    fake_trial.agent_environment.stop.side_effect = RuntimeError(
        "owned resource cleanup failed"
    )
    row = await gate.inspect_task(raw, contract, tmp_path / "validation", prepare=False)
    assert row["status"] == "BLOCKED"


async def test_docker_swallowed_cleanup_error_cannot_be_ready(
    raw, contract, fake_trial, tmp_path, monkeypatch
):
    monkeypatch.setattr(
        gate, "docker", AsyncMock(return_value="owned-container-still-present")
    )
    row = await gate.inspect_task(raw, contract, tmp_path / "validation", prepare=False)
    assert row["status"] == "BLOCKED", row
    assert row["checks"][-1]["error"] == "Native Docker cleanup left owned containers"


async def test_known_zero_reward_is_irrelevant_to_environment_readiness(
    raw, contract, fake_trial, tmp_path
):
    row = await gate.inspect_task(raw, contract, tmp_path / "validation", prepare=False)
    assert row["status"] == "READY", row
    assert (
        next(c for c in row["checks"] if c["id"] == "verifier-script")["phase"]
        == "verifier"
    )
    assert "reward" not in row
    # The fixture's real verifier explicitly writes zero; it has not been run by validation.
    assert "echo 0" in (fake_trial.task.paths.tests_dir / "test.sh").read_text()


@pytest.fixture
async def storage_probe_command(raw, contract, fake_trial, tmp_path):
    fake_trial.task.config.environment.storage_mb = 1
    await gate.inspect_task(raw, contract, tmp_path / "validation", prepare=False)
    return next(
        call.args[0]
        for call in fake_trial.agent_environment.exec.call_args_list
        if "df -Pk" in call.args[0]
    )


def test_storage_probe_checks_df_failure_before_parsing(storage_probe_command):
    assert storage_probe_command.index("|| exit $?") < storage_probe_command.index(
        "| awk"
    )


@pytest.mark.skipif(sys.platform != "linux", reason="Executes Linux Bash and df")
def test_storage_probe_preserves_df_failure_before_output_parsing(
    storage_probe_command, tmp_path
):
    bin_dir = tmp_path / "fake-bin"
    bin_dir.mkdir()
    df = bin_dir / "df"
    df.write_text("#!/bin/sh\nexit 7\n")
    df.chmod(0o755)
    result = subprocess.run(
        ["bash", "-c", storage_probe_command],
        env={**os.environ, "PATH": str(bin_dir) + ":" + os.environ["PATH"]},
        capture_output=True,
        timeout=5,
    )
    assert result.returncode == 7


@pytest.mark.parametrize("bad", ["BLOCKED", "UNVERIFIED"])
def test_freeze_refuses_any_incomplete_task(raw, contract, tmp_path, monkeypatch, bad):
    prepared = {
        "trials": [raw],
        "contracts": {"fixture/plain": contract},
        "identity": {},
    }
    p = tmp_path / "prepared.json"
    gate.write_json(p, prepared)
    report = {
        "prepared_path": str(p),
        "prepared_sha256": gate.file_sha(p),
        "validated_at": time.time(),
        "tasks": [
            {
                "task": "fixture/plain",
                "trial_indices": [0],
                "status": bad,
                "checks": [{"status": bad}],
            }
        ],
    }
    v = tmp_path / "validation.json"
    gate.write_json(v, report)
    monkeypatch.setattr(gate, "check_identity", lambda _: None)
    with pytest.raises(ValueError, match="prohibited"):
        gate.freeze(v, tmp_path / "lock.json", 60)


async def test_expired_or_drifted_lock_never_constructs_a_job(
    raw, tmp_path, monkeypatch
):
    create = AsyncMock()
    monkeypatch.setattr(gate.Job, "create", create)
    lock = {
        "prepared": {"trials": [raw]},
        "validation": {
            "tasks": [
                {
                    "task": "fixture/plain",
                    "trial_indices": [0],
                    "status": "READY",
                    "checks": [{"status": "READY"}],
                }
            ]
        },
        "expires_at": time.time() - 1,
    }
    p = tmp_path / "lock.json"
    gate.write_json(p, lock)
    with pytest.raises(ValueError, match="expired"):
        await gate.run(p)
    create.assert_not_awaited()
    lock["expires_at"] = time.time() + 100
    gate.write_json(p, lock)
    monkeypatch.setattr(
        gate, "check_identity", lambda _: (_ for _ in ()).throw(ValueError("drift"))
    )
    with pytest.raises(ValueError, match="drift"):
        await gate.run(p)
    create.assert_not_awaited()


def test_scrub_credentials_proxy_userinfo_and_signed_url(monkeypatch):
    monkeypatch.setenv("READINESS_SECRET", "sensitive-test-value")
    value = gate.scrub(
        {
            "HTTPS_PROXY": "http://u:pw@proxy:80",
            "TOKEN": "hidden",
            "error": "sensitive-test-value https://example/a?Signature=secret",
        }
    )
    assert value["HTTPS_PROXY"] == "http://<redacted>@proxy:80"
    assert "hidden" not in json.dumps(
        value
    ) and "sensitive-test-value" not in json.dumps(value)
    assert "Signature=secret" not in json.dumps(value)


def test_formal_cli_forwards_to_the_single_gate_parser(monkeypatch):
    from typer.testing import CliRunner
    from harbor.cli.rsi import rsi_app

    calls = []
    monkeypatch.setattr(gate, "main", lambda argv: calls.append(argv))
    result = CliRunner().invoke(
        rsi_app, ["campaign", "run", "--lock", "/tmp/frozen.json"]
    )
    assert result.exit_code == 0
    assert calls == [["run", "--lock", "/tmp/frozen.json"]]


async def test_ready_freeze_runs_native_job_once_and_preserves_zero(
    raw, tmp_path, monkeypatch, fake_dispatch_identity
):
    from harbor.models.job.config import JobConfig

    config = JobConfig(
        job_name="zero",
        jobs_dir=tmp_path / "jobs",
        tasks=[{"path": raw["task"]["path"]}],
        agents=[{"name": "nop"}],
    )
    prepared = {
        "config": config.model_dump(mode="json"),
        "native_trials": [raw],
        "trials": [raw],
        "contracts": {},
        "identity": {"installed_artifacts": {"harbor": {"wheel_sha256": "a" * 64}}},
    }
    p = tmp_path / "prepared.json"
    gate.write_json(p, prepared)
    row = {
        "task": "fixture/plain",
        "trial_indices": [0],
        "status": "READY",
        "checks": [{"status": "READY"}],
        "attestation": {
            "daemon_id": "expected",
            "services": {"main": {"image_id": "sha256:fixed"}},
        },
    }
    report = {
        "prepared_path": str(p),
        "prepared_sha256": gate.file_sha(p),
        "validated_at": time.time(),
        "tasks": [row],
    }
    v, lock = tmp_path / "validation.json", tmp_path / "lock.json"
    gate.write_json(v, report)
    monkeypatch.setattr(gate, "check_identity", lambda _: None)
    gate.freeze(v, lock, 60)
    commands = AsyncMock(
        side_effect=["expected\n", "sha256:fixed\n", "expected\n", "sha256:fixed\n"]
    )
    monkeypatch.setattr(gate, "command", commands)
    job = SimpleNamespace(
        _remaining_trial_configs=[TrialConfig.model_validate(raw)],
        run=AsyncMock(return_value={"reward": 0}),
        add_hook=lambda *_: None,
    )
    create = AsyncMock(return_value=job)
    monkeypatch.setattr(gate.Job, "create", create)
    assert await gate.run(lock) == {"reward": 0}
    with pytest.raises(FileExistsError):
        await gate.run(lock)
    create.assert_awaited_once()
    assert commands.call_args_list[1].args[0][-1] == "sha256:fixed"


async def test_changed_daemon_blocks_before_claim_or_native_job(
    raw, tmp_path, monkeypatch
):
    p = tmp_path / "lock.json"
    gate.write_json(
        p,
        {
            "prepared": {"trials": [raw]},
            "expires_at": time.time() + 60,
            "validation": {
                "tasks": [
                    {
                        "task": "fixture/plain",
                        "trial_indices": [0],
                        "status": "READY",
                        "checks": [{"status": "READY"}],
                        "attestation": {"daemon_id": "old"},
                    }
                ]
            },
        },
    )
    monkeypatch.setattr(gate, "check_identity", lambda _: None)
    monkeypatch.setattr(gate, "command", AsyncMock(return_value="new"))
    create = AsyncMock()
    monkeypatch.setattr(gate.Job, "create", create)
    with pytest.raises(ValueError, match="daemon"):
        await gate.run(p)
    create.assert_not_awaited()
    assert not p.with_suffix(".dispatch.json").exists()


@pytest.fixture
def checked_in_contracts():
    from pathlib import Path

    source = Path(__file__).parents[3] / "benchmarks/readiness/tb21-contracts.json"
    contracts = json.loads(source.read_text())
    assert len(contracts) == 4
    return [gate.Contract.model_validate(value) for value in contracts.values()]


def test_checked_in_contracts_have_valid_coverage(checked_in_contracts):
    assert len(checked_in_contracts) == 4


@pytest.mark.skipif(sys.platform != "linux", reason="Executes Linux Bash syntax checks")
def test_checked_in_contracts_have_valid_shell_syntax(checked_in_contracts):
    for contract in checked_in_contracts:
        for check in contract.checks:
            result = subprocess.run(
                ["bash", "-n", "-c", check.command], capture_output=True, timeout=5
            )
            assert result.returncode == 0, (check.id, result.stderr)


async def test_native_multi_model_three_attempt_plan_is_not_multiplied_twice(
    task, contract, tmp_path, monkeypatch, fake_dispatch_identity
):
    from harbor.models.job.config import JobConfig

    artifact_identity = {"installed_artifacts": {"harbor": {"wheel_sha256": "a" * 64}}}
    monkeypatch.setattr(gate, "identity", lambda *_: artifact_identity)
    attest = {
        "daemon_id": "fixture-daemon",
        "services": {"main": {"image_id": "sha256:fixed"}},
        "compose": {"services": {"main": {}}},
        "compose_effective_sha256": "fixed",
    }
    probes = []

    async def inspect(raw, contract_data, directory, *, prepare, skip_agent=False):
        probes.append((raw["agent"]["model_name"], prepare))
        return {
            "task": "fixture/plain",
            "status": "PREPARED" if prepare else "READY",
            "checks": [{"id": "actual-container", "status": "READY"}],
            "attestation": attest,
            "started_at": time.time(),
        }

    monkeypatch.setattr(gate, "inspect_task", inspect)
    config = JobConfig(
        job_name="two-models-three-attempts",
        jobs_dir=tmp_path / "native-jobs",
        n_attempts=3,
        n_concurrent_trials=2,
        agents=[
            {"name": "nop", "model_name": name} for name in ("fixture/a", "fixture/b")
        ],
        tasks=[{"path": task}],
    )
    config_path, contracts = tmp_path / "config.json", tmp_path / "contracts.json"
    gate.write_json(config_path, gate.execution_dump(config))
    gate.write_json(contracts, {"fixture/plain": contract})
    prepared_dir = tmp_path / "prepared"
    prepared = await gate.prepare(config_path, None, contracts, prepared_dir)
    assert prepared["n_tasks"] == 1
    assert prepared["n_trials"] == 6
    assert prepared["n_validation_groups"] == 2
    assert len(prepared["config"]["tasks"]) == 1
    assert [r["trial_indices"] for r in prepared["preparation"]] == [
        [0, 2, 4],
        [1, 3, 5],
    ]
    assert len({t["trial_name"] for t in prepared["trials"]}) == 6
    validation_dir = tmp_path / "validated"
    report = await gate.validate(prepared_dir / "prepared.json", validation_dir)
    assert len(probes) == 4  # Two models, prepare + setup, never six attempts.
    assert report["n_tasks"] == 1 and report["n_trials"] == 6
    assert report["contract_coverage"] == {"reviewed": 1, "total": 1}
    lock = tmp_path / "ready.lock.json"
    gate.freeze(validation_dir / "validation.json", lock, 60)
    monkeypatch.setattr(gate, "command", AsyncMock(return_value="fixture-daemon\n"))
    captured = []

    async def native_run(job):
        captured.extend(job._remaining_trial_configs)
        return {"native_count": len(captured)}

    monkeypatch.setattr(gate.Job, "run", native_run)
    assert await gate.run(lock) == {"native_count": 6}
    assert [t.trial_name for t in captured] == [
        t["trial_name"] for t in prepared["trials"]
    ]
    assert [t.agent.model_name for t in captured] == ["fixture/a", "fixture/b"] * 3
    with pytest.raises(FileExistsError):
        await gate.run(lock)


@pytest.mark.parametrize("indices", [[[0]], [[0], [0]], [[1], [0]]])
def test_freeze_requires_each_distinct_model_and_all_attempt_indices(raw, indices):
    other = json.loads(json.dumps(raw))
    other["agent"]["model_name"] = "fixture/second-model"
    prepared = {"trials": [raw, other]}
    report = {
        "tasks": [
            {
                "task": "fixture/plain",
                "trial_indices": group,
                "status": "READY",
                "checks": [{"status": "READY"}],
            }
            for group in indices
        ]
    }
    with pytest.raises(ValueError, match="exactly once"):
        gate.require_ready(prepared, report)


async def test_native_model_order_drift_cannot_dispatch(
    raw, tmp_path, monkeypatch, fake_dispatch_identity
):
    from harbor.models.job.config import JobConfig

    other = json.loads(json.dumps(raw))
    other["agent"]["model_name"] = "fixture/second-model"
    config = JobConfig(
        job_name="new",
        jobs_dir=tmp_path / "jobs",
        tasks=[{"path": raw["task"]["path"]}],
    )
    planned = [raw, other]
    lock = tmp_path / "lock.json"
    gate.write_json(
        lock,
        {
            "expires_at": time.time() + 60,
            "prepared": {
                "config": gate.execution_dump(config),
                "trials": planned,
                "native_trials": planned,
            },
            "validation": {
                "tasks": [
                    {
                        "task": "fixture/plain",
                        "trial_indices": [i],
                        "status": "READY",
                        "checks": [{"status": "READY"}],
                        "attestation": {
                            "daemon_id": "same",
                            "services": {"main": {"image_id": "sha256:fixed"}},
                        },
                    }
                    for i in range(2)
                ]
            },
        },
    )
    run = AsyncMock()
    monkeypatch.setattr(gate, "check_identity", lambda _: None)
    monkeypatch.setattr(gate, "command", AsyncMock(return_value="same\n"))
    monkeypatch.setattr(
        gate.Job,
        "create",
        AsyncMock(
            return_value=SimpleNamespace(
                _remaining_trial_configs=[
                    TrialConfig.model_validate(other),
                    TrialConfig.model_validate(raw),
                ],
                run=run,
            )
        ),
    )
    with pytest.raises(ValueError, match="configuration changed"):
        await gate.run(lock)
    run.assert_not_awaited()
    assert lock.with_suffix(
        ".dispatch.json"
    ).exists()  # Failure is evidence, not an implicit retry.


@pytest.mark.skipif(
    sys.platform != "linux", reason="Observes real Linux /proc dispatcher identity"
)
def test_status_observes_actual_dispatch_identity_without_starting_anything(
    raw, tmp_path, monkeypatch
):
    from harbor.models.job.config import JobConfig

    config = JobConfig(
        job_name="observed",
        jobs_dir=tmp_path / "jobs",
        tasks=[{"path": raw["task"]["path"]}],
    )
    lock = tmp_path / "lock.json"
    gate.write_json(
        lock, {"prepared": {"config": gate.execution_dump(config), "trials": [raw]}}
    )
    calls = []
    monkeypatch.setattr(
        gate,
        "summarize",
        lambda directory, trials: (
            calls.append((directory, trials)) or {"n_expected": 1, "n_scored": 0}
        ),
    )
    before = lock.read_bytes()
    assert gate.campaign_status(lock)["dispatch_process_state"] == "not_dispatched"
    claim = lock.with_suffix(".dispatch.json")
    gate.write_json(claim, {"process": gate.process_identity(os.getpid())})
    assert gate.campaign_status(lock)["dispatch_process_state"] == "running"
    identity = gate.process_identity(os.getpid())
    identity["start_ticks"] = "recycled-pid"
    gate.write_json(claim, {"process": identity})
    assert gate.campaign_status(lock)["dispatch_process_state"] == "not_running"
    assert lock.read_bytes() == before
    assert calls[0] == (config.jobs_dir / config.job_name, [raw])


def test_retired_rsi_launcher_is_not_a_second_dispatch_entry():
    from typer.testing import CliRunner
    from harbor.cli.rsi import rsi_app

    for command in ("run", "preflight", "summarize"):
        result = CliRunner().invoke(rsi_app, [command])
        assert result.exit_code == 2


@pytest.mark.parametrize("field", ["config", "native_trials", "profiles"])
def test_dispatch_config_and_recovery_inputs_cannot_drift_outside_trial_hash(
    raw, monkeypatch, field
):
    monkeypatch.setattr(gate, "identity", lambda *_: {"content": "fixed"})
    prepared = {
        "config": {"n_concurrent_trials": 2},
        "native_trials": [raw],
        "profiles": {},
        "trials": [raw],
        "contracts": {},
    }
    prepared["identity"] = gate.prepared_identity(prepared)
    gate.check_identity(prepared)
    prepared[field] = {"changed": True}
    with pytest.raises(ValueError, match="inputs changed"):
        gate.check_identity(prepared)


async def test_revalidation_retries_failed_group_without_renewing_success(
    raw, contract, tmp_path, monkeypatch
):
    other = json.loads(json.dumps(raw))
    other["agent"]["model_name"] = "fixture/second"
    trials = [raw, other]
    rows = [
        {
            "task": "fixture/plain",
            "trial_indices": [i],
            "status": "PREPARED",
            "checks": [],
        }
        for i in range(2)
    ]
    prepared = {
        "trials": trials,
        "preparation": rows,
        "contracts": {"fixture/plain": contract},
        "identity": {"fixed": "identity"},
        "n_tasks": 1,
    }
    prepared_path = tmp_path / "prepared.json"
    gate.write_json(prepared_path, prepared)
    monkeypatch.setattr(gate, "check_identity", lambda _: None)
    old_time = time.time() - 100
    successful = {
        "task": "fixture/plain",
        "trial_indices": [0],
        "status": "READY",
        "checks": [{"status": "READY"}],
        "started_at": old_time,
    }
    previous = {
        "prepared_sha256": gate.file_sha(prepared_path),
        "identity": prepared["identity"],
        "tasks": [
            successful,
            {
                "task": "fixture/plain",
                "trial_indices": [1],
                "status": "BLOCKED",
                "checks": [{"status": "BLOCKED"}],
            },
        ],
    }
    previous_path = tmp_path / "previous.json"
    gate.write_json(previous_path, previous)
    original = previous_path.read_bytes()
    inspect = AsyncMock(
        return_value={
            "task": "fixture/plain",
            "status": "READY",
            "checks": [{"status": "READY"}],
            "started_at": time.time(),
        }
    )
    monkeypatch.setattr(gate, "inspect_task", inspect)
    report = await gate.validate(
        prepared_path, tmp_path / "new-validation", previous_path=previous_path
    )
    assert inspect.await_count == 1
    assert inspect.await_args.args[0]["agent"]["model_name"] == "fixture/second"
    assert report["validated_at"] == old_time
    assert report["tasks"][0]["reused_report_sha256"] == gate.file_sha(previous_path)
    assert previous_path.read_bytes() == original
    previous["identity"] = {"wrong": "deployment"}
    gate.write_json(previous_path, previous)
    with pytest.raises(ValueError, match="different native plan"):
        await gate.validate(
            prepared_path, tmp_path / "refused", previous_path=previous_path
        )


def test_native_event_observer_distinguishes_agent_phase_from_pending_pipelines(
    raw, tmp_path, monkeypatch
):
    from harbor.models.job.config import JobConfig

    other = TrialConfig.model_validate(raw).model_copy(
        update={"trial_name": "independent-second"}
    )
    planned = [raw, gate.execution_dump(other)]
    config = JobConfig(
        job_name="events",
        jobs_dir=tmp_path / "jobs",
        tasks=[{"path": raw["task"]["path"]}],
    )
    lock = tmp_path / "lock.json"
    gate.write_json(
        lock, {"prepared": {"config": gate.execution_dump(config), "trials": planned}}
    )
    monkeypatch.setattr(gate, "summarize", lambda *_: {"n_expected": 2})
    assert (
        gate.campaign_status(lock)["native_event_observation"]["agent_phase_active"]
        is None
    )
    events = [
        {"trial_name": raw["trial_name"], "event": "agent-start", "observed_at": 1},
        {
            "trial_name": other.trial_name,
            "event": "environment-start",
            "observed_at": 2,
        },
        {"trial_name": raw["trial_name"], "event": "cancel", "observed_at": 3},
    ]
    journal = lock.with_suffix(".events.jsonl")
    journal.write_text("".join(json.dumps(e) + "\n" for e in events))
    observation = gate.campaign_status(lock)["native_event_observation"]
    assert (
        observation["agent_phase_active"] == 1
    )  # Cancellation is not a cleanup acknowledgement.
    assert observation["model_generation_count_not_inferred"] is True
    events.append(
        {"trial_name": raw["trial_name"], "event": "agent-end", "observed_at": 4}
    )
    journal.write_text("".join(json.dumps(e) + "\n" for e in events))
    assert (
        gate.campaign_status(lock)["native_event_observation"]["agent_phase_active"]
        == 0
    )
    journal.write_text(journal.read_text() + '{"partial":')
    observation = gate.campaign_status(lock)["native_event_observation"]
    assert observation["agent_phase_active"] is None
    assert observation["error"] == "JSONDecodeError"
