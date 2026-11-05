"""Prepare standard task copies with verified, verifier-only offline dependencies.

This does not run a Job, install anything in an agent image, or rewrite an
official test. Harbor uploads the additional tests assets after the agent phase.
The resulting task has a distinct hash and must be frozen before evaluation.
"""

import argparse
import gzip
import hashlib
import json
import re
import shlex
import shutil
import tarfile
import tempfile
import tomllib
from pathlib import Path, PurePosixPath
from typing import Any

from harbor.models.task.task import Task
from harbor.publisher.packager import Packager

CACHE_PATH = "/tests/.harbor-verifier-cache"
INSTALLER_URL = "https://astral.sh/uv/0.9.5/install.sh"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def _parse_recipe(script: str) -> tuple[str, list[str], list[str]]:
    """Accept explicit pinned uvx requirements; refuse dynamic shell expressions."""
    commands = re.findall(r"(?m)^uvx(?:[^\n]*\\\n)*[^\n]*", script)
    if len(commands) != 1:
        raise ValueError("Expected one explicit uvx command")
    tokens = shlex.split(commands[0].replace("\\\n", " "), comments=True)
    python = None
    requirements = []
    index_options = []
    index = 1
    while index < len(tokens) and tokens[index].startswith("-"):
        flag = tokens[index]
        if flag not in {
            "-p",
            "--python",
            "-w",
            "--with",
            "--index",
            "--index-strategy",
        } or index + 1 == len(tokens):
            raise ValueError(f"Unsupported uvx option: {flag}")
        value = tokens[index + 1]
        if flag in {"-p", "--python"}:
            python = value
        elif flag == "--index":
            if not re.fullmatch(
                r"https://[A-Za-z0-9][A-Za-z0-9.-]+(?::443)?(?:/[A-Za-z0-9._~/-]*)?",
                value,
            ):
                raise ValueError(
                    "Index must be a literal HTTPS URL without credentials"
                )
            index_options.extend([flag, value])
        elif flag == "--index-strategy":
            if value not in {"first-index", "unsafe-first-match", "unsafe-best-match"}:
                raise ValueError("Unsupported uv index strategy")
            index_options.extend([flag, value])
        else:
            if not re.fullmatch(r"[A-Za-z0-9_.-]+==[A-Za-z0-9_.+!-]+", value):
                raise ValueError(f"Requirement is not explicitly pinned: {value}")
            requirements.append(value)
        index += 2
    if (
        python not in {"3.11", "3.12", "3.13"}
        or not requirements
        or tokens[index : index + 1] != ["pytest"]
    ):
        raise ValueError("Unsupported Python request or tool command")
    if INSTALLER_URL not in script:
        raise ValueError("Official uv installer version does not match the cache")
    return python, requirements, index_options


def recipe(script: str) -> tuple[str, list[str]]:
    """Read pinned requirements while validating every supported resolver option."""
    python, requirements, _ = _parse_recipe(script)
    return python, requirements


def verify_cache(
    root: Path, expected_manifest_sha256: str, max_bytes: int
) -> dict[str, Any]:
    manifest_path = root / "manifest.json"
    if sha256(manifest_path) != expected_manifest_sha256:
        raise ValueError("Cache manifest SHA-256 mismatch")
    manifest = json.loads(manifest_path.read_text())
    if manifest.get("schema_version") != 1 or manifest.get("uv_version") != "0.9.5":
        raise ValueError("Unsupported dependency cache manifest")
    declared = set()
    total = 0
    for entry in manifest["files"]:
        name = PurePosixPath(entry["path"])
        if (
            name.is_absolute()
            or ".." in name.parts
            or not name.parts
            or str(name) != entry["path"]
            or str(name) in declared
            or name.parts[0] not in {"install.sh", "release", "python", "wheels", "bin"}
        ):
            raise ValueError(f"Unsafe or duplicate cache path: {name}")
        # Optional pinned OS tools are extracted by the same verified payload
        # bootstrap, after the Agent phase. They must never replace the curl
        # shim or the official uv/uvx executables.
        if name.parts[0] == "bin" and (
            len(name.parts) != 2
            or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", name.name)
            or name.name in {"curl", "uv", "uvx"}
        ):
            raise ValueError(f"Unsafe cached verifier executable: {name}")
        path = root / name
        if not path.resolve().is_relative_to(root.resolve()):
            raise ValueError(f"Cache link escapes root: {name}")
        if path.is_symlink() or not path.is_file():
            raise ValueError(f"Cache entries must be regular files: {name}")
        if name.parts[0] == "bin" and not path.stat().st_mode & 0o111:
            raise ValueError(f"Cached verifier command is not executable: {name}")
        total += path.stat().st_size
        if total > max_bytes:
            raise ValueError("Dependency cache exceeds the authorized byte bound")
        if path.stat().st_size != entry["bytes"] or sha256(path) != entry["sha256"]:
            raise ValueError(f"Cache content mismatch: {name}")
        declared.add(str(name))
    actual = {
        p.relative_to(root).as_posix()
        for p in root.rglob("*")
        if p.is_file() or p.is_symlink()
    } - {"manifest.json"}
    if actual != declared:
        raise ValueError("Cache contains missing or unregistered files")
    if not {"install.sh", "release/uv-x86_64-unknown-linux-gnu.tar.gz"} <= declared:
        raise ValueError("Official installer or release archive is missing")
    return manifest


def curl_cache_shim(
    installer_sha256: str, payload_sha256: str, release_sha256: str | None = None
) -> str:
    """Serve the verified installer/release locally; forward other curl calls."""
    digests = [installer_sha256, payload_sha256]
    if release_sha256 is not None:
        digests.append(release_sha256)
    if not all(re.fullmatch(r"[a-f0-9]{64}", digest) for digest in digests):
        raise ValueError("Invalid installer digest")
    local_release = ""
    if release_sha256 is not None:
        release_path = f"{CACHE_PATH}/release/uv-x86_64-unknown-linux-gnu.tar.gz"
        local_release = (
            f'if [ "$#" = 4 ] && [ "$1" = -sSfL ] && [ "$2" = {shlex.quote("file://" + release_path)} ] && [ "$3" = -o ]; then\n'
            f"  printf '%s  %s\\n' {release_sha256} {shlex.quote(release_path)} | sha256sum -c - >&2\n"
            f'  exec cp -- "{release_path}" "$4"\n'
            "fi\n"
        )
    return (
        "#!/bin/sh\nset -eu\n"
        f'if [ "$#" = 2 ] && [ "$1" = -LsSf ] && [ "$2" = {shlex.quote(INSTALLER_URL)} ]; then\n'
        f"  printf '%s  %s\\n' {installer_sha256} {CACHE_PATH}/install.sh | sha256sum -c - >&2\n"
        f"  printf '%s  %s\\n' {payload_sha256} {CACHE_PATH}/payload.tar.gz | sha256sum -c - >&2\n"
        f"  tar -xzf {CACHE_PATH}/payload.tar.gz -C {CACHE_PATH}\n"
        f"  exec cat {CACHE_PATH}/install.sh\n"
        "fi\n" + local_release + 'exec /usr/bin/curl "$@"\n'
    )


def payload_archive(cache: Path, target: Path) -> None:
    """Compress verified dependency bytes deterministically for native upload."""
    with (
        target.open("wb") as stream,
        gzip.GzipFile(filename="", fileobj=stream, mode="wb", mtime=0) as compressed,
        tarfile.open(fileobj=compressed, mode="w|") as archive,
    ):
        for path in sorted(cache.rglob("*")):
            name = path.relative_to(cache).as_posix()
            if not path.is_file() or name in {"manifest.json", "install.sh"}:
                continue
            info = archive.gettarinfo(str(path), arcname=name)
            info.mtime = 0
            info.uid = info.gid = 0
            info.uname = info.gname = ""
            info.pax_headers = {}
            with path.open("rb") as source:
                archive.addfile(info, source)


def prepare(
    source: Path,
    destination: Path,
    cache: Path,
    expected_task_hash: str,
    expected_manifest_sha256: str,
    max_bytes: int = 512 * 1024 * 1024,
    allow_network_packages: bool = False,
) -> dict[str, Any]:
    if destination.exists():
        raise ValueError("Destination already exists; refusing to overwrite evidence")
    task = Task(source)
    task.paths.validate_input_tree(source)
    actual_hash, _ = Packager.compute_content_hash(source)
    if actual_hash != expected_task_hash:
        raise ValueError("Official source task hash mismatch")
    python, requirements, index_options = _parse_recipe(
        (source / "tests/test.sh").read_text()
    )
    if index_options and not allow_network_packages:
        # A requirement-only cache manifest does not establish which index or
        # CPU/GPU wheel variant it came from. Keep the official resolver active.
        raise ValueError("An explicit index requires network package resolution")
    manifest = verify_cache(cache, expected_manifest_sha256, max_bytes)
    if python not in manifest["python_requests"] or (
        not allow_network_packages
        and not set(requirements) <= set(manifest["requirements"])
    ):
        raise ValueError("Cache does not cover the official verifier requirements")
    env = {
        "PATH": f"{CACHE_PATH}/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
        "UV_DOWNLOAD_URL": f"file://{CACHE_PATH}/release",
        "UV_PYTHON_INSTALL_DIR": f"{CACHE_PATH}/python",
        "UV_PYTHON_DOWNLOADS": "never",
        "UV_FIND_LINKS": f"{CACHE_PATH}/wheels",
        "UV_OFFLINE": "false" if allow_network_packages else "true",
        "UV_NO_INDEX": "false" if allow_network_packages else "true",
        "UV_CACHE_DIR": "/tmp/harbor-verifier-dependencies/cache",
    }
    if set(env) & task.config.verifier.env.keys():
        raise ValueError(
            "Existing verifier environment conflicts with dependency cache"
        )
    toml = (source / "task.toml").read_text()
    additions = "\n".join(f"{k} = {json.dumps(v)}" for k, v in env.items()) + "\n"
    if "[verifier.env]" in toml:
        toml = toml.replace("[verifier.env]", "[verifier.env]\n" + additions, 1)
    else:
        toml += "\n[verifier.env]\n" + additions
    parsed = tomllib.loads(toml)
    original = tomllib.loads((source / "task.toml").read_text())
    if "env" in original["verifier"]:
        parsed["verifier"]["env"] = original["verifier"]["env"]
    else:
        parsed["verifier"].pop("env")
    if parsed != original:
        raise ValueError("Preparation changed fields outside verifier.env")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=destination.parent) as temporary:
        prepared = Path(temporary) / "task"
        shutil.copytree(source, prepared, symlinks=True)
        bundle = prepared / "tests/.harbor-verifier-cache"
        (bundle / "bin").mkdir(parents=True)
        shutil.copy2(cache / "install.sh", bundle / "install.sh")
        shutil.copy2(cache / "manifest.json", bundle / "manifest.json")
        payload = bundle / "payload.tar.gz"
        payload_archive(cache, payload)
        shim = bundle / "bin/curl"
        shim.write_text(
            curl_cache_shim(
                sha256(cache / "install.sh"),
                sha256(payload),
                next(
                    entry["sha256"]
                    for entry in manifest["files"]
                    if entry["path"] == "release/uv-x86_64-unknown-linux-gnu.tar.gz"
                ),
            ),
            newline="\n",
        )
        shim.chmod(0o755)
        (prepared / "task.toml").write_text(toml, newline="\n")
        Task(prepared).paths.validate_input_tree(prepared / "tests")
        prepared.rename(destination)
    return {
        "source_task": str(source.resolve()),
        "source_task_hash": actual_hash,
        "prepared_task": str(destination.resolve()),
        "prepared_task_hash": Packager.compute_content_hash(destination)[0],
        "cache_manifest_sha256": expected_manifest_sha256,
        "compressed_payload_sha256": sha256(
            destination / "tests/.harbor-verifier-cache/payload.tar.gz"
        ),
        "compressed_payload_bytes": (
            destination / "tests/.harbor-verifier-cache/payload.tar.gz"
        )
        .stat()
        .st_size,
        "python_request": python,
        "requirements": requirements,
        "index_options": index_options,
        "uncached_network_requirements": sorted(
            set(requirements) - set(manifest["requirements"])
        ),
        "package_network_allowed": allow_network_packages,
        "official_test_script_sha256": sha256(source / "tests/test.sh"),
        "official_files_unchanged_except_verifier_env": True,
        "agent_environment_changed": False,
        "dynamic_readiness": "UNTESTED",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--destination", type=Path, required=True)
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--task-hash", required=True)
    parser.add_argument("--cache-manifest-sha256", required=True)
    parser.add_argument("--max-bytes", type=int, default=512 * 1024 * 1024)
    parser.add_argument("--allow-network-packages", action="store_true")
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()
    receipt = prepare(
        args.source,
        args.destination,
        args.cache,
        args.task_hash,
        args.cache_manifest_sha256,
        args.max_bytes,
        args.allow_network_packages,
    )
    args.receipt.write_text(json.dumps(receipt, indent=2) + "\n")


if __name__ == "__main__":
    main()
