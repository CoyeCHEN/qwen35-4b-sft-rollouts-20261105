"""Prepare immutable role baselines using WorkspaceBench's native helpers.

Executed during the seed image build, with verified assets mounted read-only.
There are no Agent or Judge calls.
"""

import hashlib
import importlib.util
import json
import shutil
import sys
from pathlib import Path


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Missing native helper: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(8 * 1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def main() -> None:
    archive = Path("/opt/workspace-assets/filesys_en.zip")
    if archive.stat().st_size != 18721947868 or sha256(archive) != (
        "1899e03bfea2c3d4c63686405ede303914e004e735ae193af7c4bdb7898546ac"
    ):
        raise RuntimeError("Official workspace archive identity mismatch")
    tools = Path("/opt/harbor-workspace/tools")
    download = load("workspace_download", tools / "download_hf_assets.py")
    config_builder = load("workspace_native_config", tools / "build_run_config.py")
    source = Path("/opt/workspace-native/src")
    sys.path.insert(0, str(source))
    filesys = load("workspace_native_filesys", source / "filesys_utils.py")
    raw = Path("/tmp/workspace-official-raw")
    raw.mkdir()
    download._extract_workspace_archive(archive, raw, force=False, language="en")
    records = {}
    baseline_root = Path("/opt/workspace-native/standard")
    baseline_root.mkdir(parents=True)
    for role, directory in config_builder.ROLE_DIRS.items():
        baseline = baseline_root / directory
        filesys.make_filesys(
            raw_work_dir=str(raw / f"{directory}_raw"),
            standard_work_dir=str(baseline),
            role=role,
            task_dir="/opt/workspace-task-inputs",
        )
        manifest = [
            {
                "path": path.relative_to(baseline).as_posix(),
                "sha256": sha256(path),
                "bytes": path.stat().st_size,
            }
            for path in sorted(baseline.rglob("*"))
            if path.is_file()
        ]
        manifest_path = baseline_root / f"{directory}.manifest.json"
        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, separators=(",", ":")) + "\n"
        )
        records[role] = {
            "directory": directory,
            "files": len(manifest),
            "bytes": sum(item["bytes"] for item in manifest),
            "manifest_sha256": sha256(manifest_path),
        }
    shutil.rmtree(raw)
    provenance = {
        "archive_revision": "e245d63bfa20cfdb708cd8e78145ffb087155857",
        "archive_sha256": sha256(archive),
        "baseline_builder": "native filesys_utils.make_filesys",
        "input_task_count": 100,
        "role_count": len(records),
        "roles": records,
        "model_calls": 0,
    }
    Path("/opt/workspace-native/seed-provenance.json").write_text(
        json.dumps(provenance, ensure_ascii=False, indent=2) + "\n"
    )


if __name__ == "__main__":
    main()
