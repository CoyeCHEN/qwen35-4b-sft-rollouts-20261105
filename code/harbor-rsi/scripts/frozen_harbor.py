"""Attest the installed controller before entering Harbor's native CLI.

The attestation and ``harbor run`` execute in the same Python process. This is
an opt-in release entry point; it does not alter Harbor's Job or Trial logic.
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import csv
import fcntl
import hashlib
import importlib
import importlib.metadata
import json
import os
import sys
import time
import urllib.parse
import zipfile
from pathlib import Path
from typing import Any


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def dependency_inventory() -> list[tuple[str, str]]:
    return sorted(
        (dist.metadata["Name"].lower(), dist.version)
        for dist in importlib.metadata.distributions()
    )


def _check(actual: object, expected: object, name: str, errors: list[str]) -> None:
    if actual != expected:
        errors.append(f"{name}: actual={actual!r}, expected={expected!r}")


def _distribution(
    name: str, expected: dict[str, Any], errors: list[str]
) -> dict[str, Any]:
    """Verify wheel, direct URL, RECORD and the files actually imported."""
    dist = importlib.metadata.distribution(name)
    record_paths = [
        Path(str(dist.locate_file(item))).resolve()
        for item in (dist.files or [])
        if str(item).endswith(".dist-info/RECORD")
    ]
    if len(record_paths) != 1:
        raise ValueError(f"{name} has {len(record_paths)} distribution RECORD files")
    record = record_paths[0]
    dist_root = record.parent
    wheel = Path(expected["wheel_path"]).resolve()
    _check(dist.version, expected["version"], f"{name}.version", errors)
    _check(sha256(wheel), expected["wheel_sha256"], f"{name}.wheel_sha256", errors)
    direct_url = json.loads(dist.read_text("direct_url.json") or "{}")
    installed_from = urllib.parse.unquote(
        urllib.parse.urlparse(direct_url.get("url", "")).path
    )
    _check(Path(installed_from).resolve(), wheel, f"{name}.direct_url", errors)
    _check(
        bool(direct_url.get("dir_info", {}).get("editable")),
        False,
        f"{name}.editable",
        errors,
    )

    site_root = dist_root.parent
    if not record.is_file():
        errors.append(f"{name}.RECORD missing: {record}")
        return {"version": dist.version, "dist_info": str(dist_root)}
    checked = 0
    with record.open(newline="") as stream:
        for row in csv.reader(stream):
            if len(row) < 3 or not row[1]:
                continue
            path = (site_root / row[0]).resolve()
            if (
                not path.is_relative_to(Path(sys.prefix).resolve())
                or not path.is_file()
            ):
                errors.append(f"{name}.RECORD file missing/escaped: {path}")
                continue
            algorithm, encoded = row[1].split("=", 1)
            if algorithm != "sha256":
                errors.append(f"{name}.RECORD unsupported digest: {algorithm}")
                continue
            actual = (
                base64.urlsafe_b64encode(bytes.fromhex(sha256(path)))
                .rstrip(b"=")
                .decode()
            )
            _check(actual, encoded, f"{name}.RECORD {row[0]}", errors)
            _check(
                path.stat().st_size, int(row[2]), f"{name}.RECORD size {row[0]}", errors
            )
            checked += 1
    if not checked:
        errors.append(f"{name}.RECORD has no hashed files")

    modules = {}
    with zipfile.ZipFile(wheel) as archive:
        for module_name, expected_hash in expected["modules"].items():
            module = importlib.import_module(module_name)
            if module.__file__ is None:
                errors.append(f"{module_name} has no import file")
                continue
            module_path = Path(module.__file__).resolve()
            if not module_path.is_relative_to(site_root):
                errors.append(
                    f"{module_name} imported outside {site_root}: {module_path}"
                )
                continue
            relative = module_path.relative_to(site_root).as_posix()
            actual_hash = sha256(module_path)
            _check(
                actual_hash, expected_hash, f"{module_name}.installed_sha256", errors
            )
            try:
                wheel_hash = hashlib.sha256(archive.read(relative)).hexdigest()
                _check(actual_hash, wheel_hash, f"{module_name}.wheel_member", errors)
            except KeyError:
                errors.append(f"{module_name} missing from wheel: {relative}")
            modules[module_name] = {"path": str(module_path), "sha256": actual_hash}
    return {
        "version": dist.version,
        "dist_info": str(dist_root),
        "direct_url": direct_url.get("url"),
        "wheel_path": str(wheel),
        "wheel_sha256": sha256(wheel),
        "record_checked_files": checked,
        "modules": modules,
    }


def attest(
    manifest: dict[str, Any], config_path: Path
) -> tuple[dict[str, Any], list[str]]:
    errors: list[str] = []
    python = Path(sys.executable).absolute()
    _check(str(python), str(Path(manifest["python"]).absolute()), "python", errors)
    _check(str(Path(sys.prefix).absolute()), manifest["venv_path"], "venv_path", errors)
    _check(os.environ.get("PYTHONPATH"), None, "PYTHONPATH", errors)
    _check(sys.flags.no_user_site, 1, "python -s/no_user_site", errors)
    inventory = dependency_inventory()
    _check(
        inventory,
        [tuple(item) for item in manifest["dependency_inventory"]],
        "dependency_inventory",
        errors,
    )
    packages = {}
    for name, expected in manifest["packages"].items():
        try:
            packages[name] = _distribution(name, expected, errors)
        except Exception as exc:
            errors.append(f"{name} attestation failed: {type(exc).__name__}: {exc}")

    repo = Path(manifest["repo_path"]).resolve()
    git_head = repo / ".git"
    # The release manifest records the commit. Git itself may be a worktree
    # pointer, so use git rather than parsing .git/HEAD.
    import subprocess

    result = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=False,
    )
    _check(result.returncode, 0, "git rev-parse exit", errors)
    _check(result.stdout.strip(), manifest["git_commit"], "git_commit", errors)
    if not git_head.exists():
        errors.append(f"Git checkout missing: {repo}")

    wheel = Path(manifest["open_harness"]["wheel_path"]).resolve()
    _check(
        sha256(wheel),
        manifest["open_harness"]["wheel_sha256"],
        "open_harness.wheel_sha256",
        errors,
    )
    with zipfile.ZipFile(wheel) as archive:
        entries = [
            n for n in archive.namelist() if n.endswith(".dist-info/entry_points.txt")
        ]
        if len(entries) != 1:
            errors.append(f"OpenHarness wheel entry_points count: {len(entries)}")
        else:
            entry_text = archive.read(entries[0]).decode()
            if manifest["open_harness"]["cli_entry"] not in entry_text:
                errors.append("OpenHarness wheel CLI entry contract mismatch")

    source_manifest = manifest["source_task_manifest"]
    _check(
        sha256(Path(source_manifest["path"])),
        source_manifest["sha256"],
        "source_task_manifest.sha256",
        errors,
    )

    configs = manifest["configs"]
    config_key = str(config_path.resolve())
    if config_key not in configs:
        errors.append(f"Unfrozen config: {config_key}")
        config_info = {}
    else:
        config_info = configs[config_key]
        _check(sha256(config_path), config_info["sha256"], "config.sha256", errors)
    config = json.loads(config_path.read_text())
    from harbor.job import Job
    from harbor.models.job.config import JobConfig

    try:
        resolved = asyncio.run(
            Job._resolve_task_configs(JobConfig.model_validate(config))
        )
        paths = [Path(t.path).resolve() for t in resolved if t.path is not None]
        if len(paths) != len(resolved):
            errors.append("Unfrozen remote task in config; local pinned Tasks required")
    except Exception as exc:
        errors.append(f"Native dataset resolution failed: {type(exc).__name__}: {exc}")
        paths = []
    task_by_path = {str(Path(x["path"]).resolve()): x for x in manifest["tasks"]}
    ids = [task_by_path.get(str(p), {}).get("task_id", f"UNFROZEN:{p}") for p in paths]
    _check(ids, config_info.get("task_ids"), "config.task_ids", errors)
    concurrency = config_info.get("n_concurrent_trials", 1)
    _check(
        config.get("n_concurrent_trials"),
        concurrency,
        "config.n_concurrent_trials",
        errors,
    )
    if not 1 <= concurrency <= manifest.get("max_concurrent_trials", 1):
        errors.append("Frozen concurrency exceeds release cap")
    _check(
        config.get("retry", {}).get("max_retries", 0), 0, "config.max_retries", errors
    )
    task_index = {x["task_id"]: x for x in manifest["tasks"]}
    for task_id, path in zip(ids, paths, strict=True):
        task = task_index.get(task_id)
        if task is None:
            errors.append(f"Unfrozen task: {task_id}")
            continue
        _check(str(path), str(Path(task["path"]).resolve()), f"{task_id}.path", errors)
        for item in task["files"]:
            file_path = path / item["path"]
            if not file_path.is_file():
                errors.append(f"{task_id} file missing: {file_path}")
            else:
                _check(
                    sha256(file_path),
                    item["sha256"],
                    f"{task_id}/{item['path']}",
                    errors,
                )
    if ids:
        _check(len(ids), len(set(ids)), "unique_task_ids", errors)
    evidence = {
        "schema_version": "frozen-harbor-attestation-v1",
        "attested_at_unix": time.time(),
        "pid": os.getpid(),
        "python": str(python),
        "git_commit": result.stdout.strip(),
        "packages": packages,
        "dependency_inventory": inventory,
        "open_harness_wheel_sha256": sha256(wheel),
        "config_path": config_key,
        "config_sha256": sha256(config_path),
        "task_ids": ids,
        "benchmark_revision": config_info.get("benchmark_revision"),
        "judge_identity": config_info.get("judge_identity"),
        "model_identity": config_info.get("model_identity"),
        "environment_identity": config_info.get("environment_identity"),
        "passed": not errors,
        "errors": errors,
    }
    return evidence, errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--attestation", type=Path, required=True)
    parser.add_argument("--check-only", action="store_true")
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text())
    lock_path = Path(manifest["controller_lock"])
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("w") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print(
                f"Another frozen Harbor controller holds {lock_path}", file=sys.stderr
            )
            return 2
        evidence, errors = attest(manifest, args.config)
        args.attestation.parent.mkdir(parents=True, exist_ok=True)
        args.attestation.write_text(json.dumps(evidence, indent=2) + "\n")
        if errors:
            print(
                "Frozen runtime mismatch; no Harbor Job dispatched:\n"
                + "\n".join(errors),
                file=sys.stderr,
            )
            return 2
        if args.check_only:
            print(f"Runtime attested: {args.attestation}")
            return 0
        # This is the same process whose imported modules were just hashed.
        # Typer enters the ordinary Harbor CLI and native Job/Trial path.
        from harbor.cli.main import app

        app(args=["run", "--config", str(args.config.resolve()), "--yes"])
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
