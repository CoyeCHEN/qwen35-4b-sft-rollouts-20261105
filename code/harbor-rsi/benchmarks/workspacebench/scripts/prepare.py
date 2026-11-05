"""Create a reproducible WorkspaceBench runtime without copying large assets."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = json.loads((ROOT / "manifest.json").read_text(encoding="utf-8"))
MARKER = ".harbor-rsi-workspacebench.json"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(8 * 1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def _tree_digest(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        digest.update(path.relative_to(root).as_posix().encode())
        digest.update(b"\0")
        digest.update(_sha256(path).encode())
        digest.update(b"\n")
    return digest.hexdigest()


def _run(*args: str, cwd: Path | None = None) -> None:
    subprocess.run(args, cwd=cwd, check=True)


def _new_worktree(source: Path, output: Path) -> None:
    if output.exists():
        raise ValueError(
            f"staging directory already exists without a valid marker: {output}"
        )
    output.parent.mkdir(parents=True, exist_ok=True)
    _run(
        "git",
        "-C",
        str(source),
        "worktree",
        "add",
        "--detach",
        str(output),
        str(MANIFEST["source_commit"]),
    )


def _ensure_mountpoints(output: Path) -> None:
    """Create ignored targets required by read-only task-container bind mounts."""
    eval_root = output / "evaluation"
    for name in ("tasks", "tasks_lite"):
        (eval_root / name).mkdir(parents=True, exist_ok=True)


def prepare(source: Path, output: Path, wheel: Path) -> dict[str, Any]:
    source = source.resolve()
    output = output.resolve()
    wheel = wheel.resolve()
    if not wheel.is_file() or wheel.suffix != ".whl":
        raise ValueError(f"OpenHarness wheel not found or not a .whl: {wheel}")

    patch_sha = _sha256(ROOT / "patches" / "workspacebench-openharness.patch")
    overlay_sha = _tree_digest(ROOT / "overlay")
    marker_path = output / MARKER
    created = False
    if output.exists():
        if not marker_path.is_file():
            raise ValueError(f"refusing to reuse unmarked staging directory: {output}")
        marker = json.loads(marker_path.read_text(encoding="utf-8"))
        if marker.get("source_commit") != MANIFEST["source_commit"]:
            raise ValueError(f"staging source commit mismatch: {output}")
        if (
            marker.get("patch_sha256") != patch_sha
            or marker.get("overlay_sha256") != overlay_sha
        ):
            raise ValueError(
                "staging adapter differs from this checkout; choose a fresh "
                "WORKSPACEBENCH_RUNTIME_ROOT"
            )
    else:
        _new_worktree(source, output)
        patch = ROOT / "patches" / "workspacebench-openharness.patch"
        _run("git", "apply", "--check", str(patch), cwd=output)
        _run("git", "apply", str(patch), cwd=output)
        overlay = ROOT / "overlay"
        for path in sorted(item for item in overlay.rglob("*") if item.is_file()):
            destination = output / path.relative_to(overlay)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, destination)
        created = True

    _ensure_mountpoints(output)
    artifact_dir = output / "evaluation" / ".generated" / "artifacts"
    artifact_dir.mkdir(parents=True, exist_ok=True)
    installed_wheel = artifact_dir / wheel.name
    shutil.copy2(wheel, installed_wheel)

    marker = {
        "schema_version": 1,
        "source_repository": MANIFEST["source_repository"],
        "source_commit": MANIFEST["source_commit"],
        "task_asset_revision": MANIFEST["task_asset_revision"],
        "patch_sha256": patch_sha,
        "overlay_sha256": overlay_sha,
        "wheel_sha256": _sha256(installed_wheel),
        "asset_source": str(source / "evaluation"),
    }
    marker_path.write_text(
        json.dumps(marker, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return {
        **marker,
        "created": created,
        "runtime_root": str(output),
        "wheel_path": str(installed_wheel),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--wheel", type=Path, required=True)
    args = parser.parse_args()
    print(
        json.dumps(
            prepare(args.source, args.output, args.wheel),
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
