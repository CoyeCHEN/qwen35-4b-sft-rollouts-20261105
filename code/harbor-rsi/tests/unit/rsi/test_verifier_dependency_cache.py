"""Offline preparation keeps official grading and agent inputs unchanged."""

import hashlib
import json
import os
import subprocess
import tarfile
from pathlib import Path

import pytest

from benchmarks.readiness.prepare_verifier_cache import (
    CACHE_PATH,
    INSTALLER_URL,
    curl_cache_shim,
    prepare,
    recipe,
    sha256,
    verify_cache,
)
from harbor.models.task.task import Task
from harbor.publisher.packager import Packager

SCRIPT = (
    f"#!/bin/bash\ncurl -LsSf {INSTALLER_URL} | sh\n"
    'source "$HOME/.local/bin/env"\n'
    "uvx \\\n -p 3.13 \\\n -w pytest==8.4.1 \\\n -w pytest-json-ctrf==0.3.5 \\\n pytest /tests/test_outputs.py\n"
    "if [ $? -eq 0 ]; then echo 1; else echo 0; fi\n"
)


def fixture(tmp_path: Path) -> tuple[Path, Path, str, str]:
    task = tmp_path / "official"
    (task / "tests").mkdir(parents=True)
    (task / "environment").mkdir()
    (task / "task.toml").write_text(
        'version = "1.0"\n[verifier]\ntimeout_sec = 12\n'
        '[agent]\ntimeout_sec = 15\n[environment]\ndocker_image = "official:pin"\n'
    )
    (task / "instruction.md").write_text("Write a program.\n")
    (task / "environment/Dockerfile").write_text("FROM official:pin\n")
    (task / "tests/test.sh").write_text(SCRIPT)
    (task / "tests/test_outputs.py").write_text("def test_official(): assert False\n")
    cache = tmp_path / "cache"
    (cache / "release").mkdir(parents=True)
    (cache / "install.sh").write_text("official installer fixture\n")
    (cache / "release/uv-x86_64-unknown-linux-gnu.tar.gz").write_bytes(b"fixture")
    manifest = {
        "schema_version": 1,
        "uv_version": "0.9.5",
        "python_requests": ["3.13"],
        "requirements": ["pytest==8.4.1", "pytest-json-ctrf==0.3.5"],
        "files": [
            {
                "path": p.relative_to(cache).as_posix(),
                "bytes": p.stat().st_size,
                "sha256": sha256(p),
            }
            for p in sorted(cache.rglob("*"))
            if p.is_file()
        ],
    }
    (cache / "manifest.json").write_text(json.dumps(manifest))
    return (
        task,
        cache,
        Packager.compute_content_hash(task)[0],
        sha256(cache / "manifest.json"),
    )


def test_preparation_never_rewrites_official_tests_or_agent_environment(
    tmp_path: Path,
) -> None:
    source, cache, task_hash, manifest_hash = fixture(tmp_path)
    destination = tmp_path / "prepared"
    receipt = prepare(source, destination, cache, task_hash, manifest_hash)
    for name in [
        "instruction.md",
        "environment/Dockerfile",
        "tests/test.sh",
        "tests/test_outputs.py",
    ]:
        assert (source / name).read_bytes() == (destination / name).read_bytes()
    assert Packager.compute_content_hash(source)[0] == task_hash
    assert receipt["prepared_task_hash"] != task_hash
    assert receipt["dynamic_readiness"] == "UNTESTED"
    prepared = Task(destination)
    original = Task(source)
    assert prepared.config.agent == original.config.agent
    assert prepared.config.environment == original.config.environment
    assert prepared.config.verifier.timeout_sec == original.config.verifier.timeout_sec
    assert "HOME" not in prepared.config.verifier.env
    assert not prepared.config.environment.env
    shim = destination / "tests/.harbor-verifier-cache/bin/curl"
    assert shim.read_bytes().startswith(b"#!/bin/sh\n")
    assert b"\r\n" not in shim.read_bytes()
    if os.name == "posix":
        assert shim.stat().st_mode & 0o111
    with pytest.raises(ValueError, match="already exists"):
        prepare(source, destination, cache, task_hash, manifest_hash)


@pytest.mark.parametrize("mutation", ["manifest", "asset", "unregistered", "symlink"])
def test_cache_integrity_fails_before_output_creation(
    tmp_path: Path, mutation: str
) -> None:
    source, cache, task_hash, manifest_hash = fixture(tmp_path)
    if mutation == "manifest":
        (cache / "manifest.json").write_text("{}")
    elif mutation == "asset":
        (cache / "install.sh").write_text("changed")
    elif mutation == "unregistered":
        (cache / "extra.py").write_text("not declared")
    else:
        (cache / "install.sh").unlink()
        (cache / "install.sh").symlink_to(source / "instruction.md")
    destination = tmp_path / "prepared"
    with pytest.raises(ValueError):
        prepare(source, destination, cache, task_hash, manifest_hash)
    assert not destination.exists()


def test_source_identity_and_cache_size_are_bounded(tmp_path: Path) -> None:
    source, cache, task_hash, manifest_hash = fixture(tmp_path)
    with pytest.raises(ValueError, match="byte bound"):
        verify_cache(cache, manifest_hash, max_bytes=1)
    (source / "tests/test_outputs.py").write_text("different assertion")
    with pytest.raises(ValueError, match="source task hash"):
        prepare(source, tmp_path / "prepared", cache, task_hash, manifest_hash)


def test_prepared_content_is_deterministic_and_archive_contains_only_dependencies(
    tmp_path: Path,
) -> None:
    source, cache, task_hash, manifest_hash = fixture(tmp_path)
    first = prepare(source, tmp_path / "first", cache, task_hash, manifest_hash)
    os.utime(cache / "install.sh", (1, 1))
    second = prepare(source, tmp_path / "second", cache, task_hash, manifest_hash)
    assert first["prepared_task_hash"] == second["prepared_task_hash"]
    assert first["compressed_payload_sha256"] == second["compressed_payload_sha256"]
    with tarfile.open(
        tmp_path / "first/tests/.harbor-verifier-cache/payload.tar.gz"
    ) as archive:
        assert archive.getnames() == ["release/uv-x86_64-unknown-linux-gnu.tar.gz"]
    assert (
        Task(tmp_path / "first").config.verifier.env["UV_CACHE_DIR"].startswith("/tmp/")
    )


def test_cache_manifest_paths_cannot_escape_root(tmp_path: Path) -> None:
    _, cache, _, _ = fixture(tmp_path)
    path = cache / "manifest.json"
    manifest = json.loads(path.read_text())
    manifest["files"][0]["path"] = "../outside"
    path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="Unsafe"):
        verify_cache(cache, sha256(path), max_bytes=10000)


@pytest.mark.parametrize(
    "script",
    [
        SCRIPT.replace("pytest==8.4.1", "pytest"),
        SCRIPT.replace("pytest==8.4.1", "git+https://example.invalid/repo@$REF"),
        SCRIPT.replace("-p 3.13", "-p $VERSION"),
        SCRIPT.replace("-p 3.13", "--unknown 3.13"),
        SCRIPT.replace("uv/0.9.5", "uv/0.9.6"),
    ],
)
def test_dynamic_or_unsupported_dependency_recipes_are_refused(script: str) -> None:
    with pytest.raises(ValueError):
        recipe(script)


def test_explicit_index_preparation_preserves_official_network_selection(
    tmp_path: Path,
) -> None:
    source, cache, _, manifest_hash = fixture(tmp_path)
    options = "--index https://download.pytorch.org/whl/cpu --index-strategy unsafe-best-match"
    script = SCRIPT.replace("-p 3.13", options + " -p 3.13")
    (source / "tests/test.sh").write_text(script)
    assert recipe(script) == ("3.13", ["pytest==8.4.1", "pytest-json-ctrf==0.3.5"])
    task_hash = Packager.compute_content_hash(source)[0]
    with pytest.raises(ValueError, match="explicit index.*network"):
        prepare(source, tmp_path / "offline", cache, task_hash, manifest_hash)
    destination = tmp_path / "network-prepared"
    receipt = prepare(
        source,
        destination,
        cache,
        task_hash,
        manifest_hash,
        allow_network_packages=True,
    )
    assert (destination / "tests/test.sh").read_bytes() == (
        source / "tests/test.sh"
    ).read_bytes()
    assert Task(destination).config.verifier.env["UV_NO_INDEX"] == "false"
    assert receipt["index_options"] == options.split()
    assert receipt["agent_environment_changed"] is False


@pytest.mark.parametrize(
    "options",
    [
        "--index http://example.org/simple",
        "--index https://user:secret@example.org/simple",
        "--index https://example.org/$INDEX",
        "--index https://example.org/simple?token=secret",
        "--index-strategy invented-strategy",
    ],
)
def test_index_options_cannot_bypass_literal_recipe_validation(options: str) -> None:
    with pytest.raises(ValueError):
        recipe(SCRIPT.replace("-p 3.13", options + " -p 3.13"))


def test_missing_requirement_and_conflicting_environment_are_not_silently_overridden(
    tmp_path: Path,
) -> None:
    source, cache, _, manifest_hash = fixture(tmp_path)
    script = source / "tests/test.sh"
    script.write_text(SCRIPT.replace("pytest==8.4.1", "pytest==8.3.4"))
    with pytest.raises(ValueError, match="does not cover"):
        prepare(
            source,
            tmp_path / "prepared",
            cache,
            Packager.compute_content_hash(source)[0],
            manifest_hash,
        )
    receipt = prepare(
        source,
        tmp_path / "explicit-network",
        cache,
        Packager.compute_content_hash(source)[0],
        manifest_hash,
        allow_network_packages=True,
    )
    assert receipt["uncached_network_requirements"] == ["pytest==8.3.4"]
    assert receipt["dynamic_readiness"] == "UNTESTED"
    assert (
        Task(tmp_path / "explicit-network").config.verifier.env["UV_OFFLINE"] == "false"
    )
    script.write_text(SCRIPT)
    toml = source / "task.toml"
    toml.write_text(toml.read_text() + '\n[verifier.env]\nPATH = "/official/bin"\n')
    with pytest.raises(ValueError, match="conflicts"):
        prepare(
            source,
            tmp_path / "prepared",
            cache,
            Packager.compute_content_hash(source)[0],
            manifest_hash,
        )


def test_curl_cache_is_exact_url_and_preserves_other_invocations() -> None:
    digest = hashlib.sha256(b"official").hexdigest()
    shim = curl_cache_shim(digest, digest)
    assert '"$#" = 2' in shim and '"$1" = -LsSf' in shim
    assert INSTALLER_URL in shim
    assert 'exec /usr/bin/curl "$@"' in shim
    assert "sha256sum -c" in shim
    with pytest.raises(ValueError, match="Invalid installer digest"):
        curl_cache_shim("untrusted; exit 0", digest)


@pytest.mark.skipif(os.name != "posix", reason="Generated POSIX verifier shim")
@pytest.mark.parametrize("tampered", [False, True])
def test_verified_local_release_does_not_require_system_curl(
    tmp_path: Path, tampered: bool
) -> None:
    source, cache, task_hash, manifest_hash = fixture(tmp_path)
    prepared = tmp_path / "prepared"
    prepare(source, prepared, cache, task_hash, manifest_hash)
    bundle = prepared / "tests/.harbor-verifier-cache"
    release = bundle / "release/uv-x86_64-unknown-linux-gnu.tar.gz"
    digest = sha256(cache / "release/uv-x86_64-unknown-linux-gnu.tar.gz")
    shim = tmp_path / "curl"
    program = (bundle / "bin/curl").read_text()
    program = program.replace(CACHE_PATH, str(bundle)).replace(
        "/usr/bin/curl", str(tmp_path / "absent-system-curl")
    )
    shim.write_text(program)
    bootstrap = subprocess.run(
        ["sh", str(shim), "-LsSf", INSTALLER_URL],
        capture_output=True,
        timeout=5,
    )
    assert bootstrap.returncode == 0, bootstrap.stderr.decode()
    if tampered:
        release.write_bytes(b"tampered release")
    output = tmp_path / "download archive"
    result = subprocess.run(
        ["sh", str(shim), "-sSfL", release.as_uri(), "-o", str(output)],
        capture_output=True,
        timeout=5,
    )
    if tampered:
        assert result.returncode != 0
        assert not output.exists()
    else:
        assert result.returncode == 0, result.stderr.decode()
        assert sha256(output) == digest


@pytest.mark.skipif(os.name != "posix", reason="Executes a POSIX verifier tool")
def test_declared_executable_is_only_available_after_verifier_bootstrap(
    tmp_path: Path,
) -> None:
    source, cache, task_hash, _ = fixture(tmp_path)
    command = cache / "bin/tool-command"
    command.parent.mkdir()
    command.write_text("#!/bin/sh\nprintf 'trusted verifier tool\\n'\n")
    command.chmod(0o755)
    manifest_path = cache / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["files"].append(
        {
            "path": "bin/tool-command",
            "bytes": command.stat().st_size,
            "sha256": sha256(command),
        }
    )
    manifest_path.write_text(json.dumps(manifest))
    destination = tmp_path / "prepared"
    receipt = prepare(source, destination, cache, task_hash, sha256(manifest_path))
    bundle = destination / "tests/.harbor-verifier-cache"
    executable = bundle / "bin/tool-command"
    assert not executable.exists()
    shim = bundle / "bin/curl"
    shim.write_text(shim.read_text().replace(CACHE_PATH, str(bundle)))
    response = subprocess.run(
        [str(shim), "-LsSf", INSTALLER_URL], capture_output=True, text=True, timeout=10
    )
    assert response.returncode == 0, response.stderr
    result = subprocess.run(
        [str(executable)], capture_output=True, text=True, timeout=10
    )
    assert result.returncode == 0
    assert result.stdout == "trusted verifier tool\n"
    assert receipt["agent_environment_changed"] is False
    assert (source / "tests/test.sh").read_bytes() == (
        destination / "tests/test.sh"
    ).read_bytes()


@pytest.mark.parametrize("name", ["curl", "uv", "uvx", "nested/tool"])
def test_cached_executables_cannot_replace_bootstrap_commands(
    tmp_path: Path, name: str
) -> None:
    _, cache, _, _ = fixture(tmp_path)
    command = cache / "bin" / name
    command.parent.mkdir(parents=True)
    command.write_text("#!/bin/sh\nexit 0\n")
    command.chmod(0o755)
    manifest_path = cache / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["files"].append(
        {
            "path": "bin/" + name,
            "bytes": command.stat().st_size,
            "sha256": sha256(command),
        }
    )
    manifest_path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="Unsafe"):
        verify_cache(cache, sha256(manifest_path), 1024 * 1024)
