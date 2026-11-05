"""Assemble a verified Workspace seed image context; no case scheduling."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import runpy
import shutil
import subprocess
from pathlib import Path
from typing import Any

bridge = runpy.run_path(str(Path(__file__).with_name("native_trial_bridge.py")))
agent_visible_metadata = bridge["agent_visible_metadata"]


EXPECTED_TASK_ASSETS = (
    "f47d396a4a75ea8125a3683807198d23183cb70a38bb1ca0137675ff972d4847"
)


def hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(8 * 1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def prepare(
    native_eval: Path, dataset: Path, archive: Path, context: Path
) -> dict[str, Any]:
    marker = json.loads(
        (native_eval.parent / ".harbor-rsi-workspacebench.json").read_text()
    )
    if marker.get("source_commit") != "3fbd0f1a136720fece86786545983e26642c3db2":
        raise ValueError("Native Workspace source identity mismatch")
    tasks = sorted(dataset.glob("*/metadata.json"))
    if len(tasks) != 100:
        raise ValueError(
            "Native baseline requires the complete fixed Lite input dataset"
        )
    files = sorted(path for path in dataset.rglob("*") if path.is_file())
    if any(path.is_symlink() for path in dataset.rglob("*")):
        raise ValueError("Unexpected symlink in fixed dataset assets")
    records = [
        (path.relative_to(dataset).as_posix(), hash_file(path)) for path in files
    ]
    digest = hashlib.sha256(
        json.dumps(records, separators=(",", ":")).encode()
    ).hexdigest()
    if digest != EXPECTED_TASK_ASSETS:
        raise ValueError(f"Frozen complete Lite asset digest mismatch: {digest}")
    if archive.stat().st_size != 18721947868 or hash_file(archive) != (
        "1899e03bfea2c3d4c63686405ede303914e004e735ae193af7c4bdb7898546ac"
    ):
        raise ValueError("Official workspace archive identity mismatch")
    context.mkdir(parents=True, exist_ok=False)
    # A hard link avoids another multi-gigabyte copy; Docker reads this input.
    os.link(archive, context / "filesys_en.zip")
    shutil.copytree(dataset, context / "tasks_lite")
    for metadata in (context / "tasks_lite").glob("*/metadata.json"):
        metadata.write_text(
            json.dumps(
                agent_visible_metadata(json.loads(metadata.read_text())),
                ensure_ascii=False,
                indent=2,
            )
            + "\n"
        )
    shutil.copytree(
        native_eval / "src",
        context / "native-src",
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )
    tools = context / "tools"
    tools.mkdir()
    for name in ["download_hf_assets.py", "build_run_config.py"]:
        shutil.copy2(native_eval / "scripts" / name, tools / name)
    here = Path(__file__).resolve().parent
    for name in ["seed_workspace.py", "native_trial_bridge.py"]:
        shutil.copy2(here / name, context / name)
    shutil.copy2(
        native_eval / "src/task_container_entry.py", context / "task_container_entry.py"
    )
    (context / "agent_runner.py").write_text(
        "from native_trial_bridge import main\n\nif __name__ == '__main__':\n    main()\n"
    )
    (context / "Dockerfile").write_text(
        "FROM harbor-rsi-phase3-workspace-runtime:3fbd0f1a1367\n"
        "COPY native-src/ /opt/workspace-native/src/\n"
        "COPY tools/ /opt/harbor-workspace/tools/\n"
        "COPY seed_workspace.py native_trial_bridge.py task_container_entry.py agent_runner.py /opt/harbor-workspace/\n"
        "RUN mkdir -p /opt/workspace-assets /logs/verifier /logs/artifacts /logs/workspace-native "
        "&& ln -s /tmp/harbor-workspace-agent-logs /logs/agent\n"
        "RUN --mount=type=bind,source=filesys_en.zip,target=/opt/workspace-assets/filesys_en.zip,ro "
        "--mount=type=bind,source=tasks_lite,target=/opt/workspace-task-inputs,ro "
        "python3 /opt/harbor-workspace/seed_workspace.py\n"
        "WORKDIR /tmp\n"
    )
    source = {
        "owner": "harbor-rsi-phase3",
        "native_source_commit": "3fbd0f1a136720fece86786545983e26642c3db2",
        "task_asset_sha256": digest,
        "task_asset_files": len(records),
        "archive_sha256": hash_file(archive),
        "input_task_count": 100,
        "formal_case_count": 10,
        "baseline_builder": "native filesys_utils.make_filesys",
        "agent_visible_full_metadata": False,
        "model_calls": 0,
        "bridge_sha256": hash_file(here / "native_trial_bridge.py"),
        "native_guard_sha256": hash_file(native_eval / "src/task_container_entry.py"),
        "native_source_manifest": [
            {
                "path": path.relative_to(native_eval).as_posix(),
                "sha256": hash_file(path),
            }
            for path in sorted(native_eval.rglob("*.py"))
            if "__pycache__" not in path.parts
        ],
    }
    (context / "source.json").write_text(json.dumps(source, indent=2) + "\n")
    return source


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--native-eval", type=Path, required=True)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--context", type=Path, required=True)
    parser.add_argument("--build", action="store_true")
    args = parser.parse_args()
    runtime = "harbor-rsi-phase3-workspace-runtime:3fbd0f1a1367"
    if args.build:
        identity = subprocess.check_output(
            ["docker", "image", "inspect", runtime, "--format", "{{.Id}}"], text=True
        ).strip()
        if (
            identity
            != "sha256:f583e85ae342403d8a059e8658f2a69e37288a7855afbb2d7c6a5edf97f01787"
        ):
            raise RuntimeError("Official runtime image identity changed")
    source = prepare(args.native_eval, args.dataset, args.archive, args.context)
    if args.build:
        tag = "harbor-rsi-phase3-workspace-seed:e245d63"
        subprocess.run(
            ["docker", "build", "--pull=false", "-t", tag, str(args.context)],
            check=True,
        )
        identity = subprocess.check_output(
            ["docker", "image", "inspect", tag, "--format", "{{.Id}}"], text=True
        ).strip()
        payload = subprocess.check_output(
            [
                "docker",
                "run",
                "--rm",
                "--label",
                "harbor-rsi-owner=phase3",
                "--cpus=1",
                "--memory=1g",
                "--entrypoint",
                "cat",
                identity,
                "/opt/workspace-native/seed-provenance.json",
            ]
        )
        native = json.loads(payload)
        if (
            native["role_count"] != 5
            or native["archive_sha256"] != source["archive_sha256"]
        ):
            raise RuntimeError("Native baseline build provenance mismatch")
        (args.context / "seed-ready.json").write_text(
            json.dumps(
                {
                    **source,
                    "image_id": identity,
                    "status": "verified",
                    "native_seed_provenance": native,
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n"
        )
    print(json.dumps(source, indent=2))


if __name__ == "__main__":
    main()
