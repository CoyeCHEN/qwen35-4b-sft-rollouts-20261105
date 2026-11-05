"""Represent ten fixed Workspace cases as native Harbor Tasks and Jobs.

The native Workspace runner still constructs prompts, prepares role workspaces,
collects outputs and judges rubrics. This command generates files only.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import runpy
import shutil
import sys
from pathlib import Path
from typing import Any

import toml
import yaml

bridge = runpy.run_path(str(Path(__file__).with_name("native_trial_bridge.py")))
agent_visible_metadata = bridge["agent_visible_metadata"]
load_module = bridge["load_module"]


TASK_IDS = ["3", "7", "13", "15", "23", "33", "35", "37", "38", "44"]
NATIVE_ROOT = "/logs/workspace-native"
RUN_NAME = "OpenHarness--DeepSeek-Flash--phase3"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def generate(
    native_eval: Path, dataset: Path, seed_ready: Path, frozen: Path, output: Path
) -> dict[str, Any]:
    seed = json.loads(seed_ready.read_text())
    if (
        seed.get("status") != "verified"
        or seed.get("native_seed_provenance", {}).get("role_count") != 5
    ):
        raise ValueError(
            "Verified official role baselines are required before generation"
        )
    if (
        seed.get("task_asset_sha256")
        != "f47d396a4a75ea8125a3683807198d23183cb70a38bb1ca0137675ff972d4847"
    ):
        raise ValueError("Fixed Lite input dataset identity mismatch")
    image = seed["image_id"]
    if not image.startswith("sha256:") or len(image) != 71:
        raise ValueError("A complete immutable seed image ID is required")
    original = json.loads(frozen.read_text())["benchmarks"]["workspacebench_lite"][
        "tasks"
    ]
    if [str(task["task_id"]) for task in original] != TASK_IDS:
        raise ValueError("The frozen Workspace case selection changed")
    native_src = native_eval / "src"
    sys.path.insert(0, str(native_src))
    runner = load_module("workspace_native_prompt", native_src / "agent_runner.py")
    download = load_module(
        "workspace_native_download", native_eval / "scripts/download_hf_assets.py"
    )
    builder = load_module(
        "workspace_native_builder", native_eval / "scripts/build_run_config.py"
    )
    parser = load_module(
        "workspace_native_openharness", native_src / "agents/openharness.py"
    )
    model_config = parser._build_config(
        model="deepseek-flash",
        base_url="https://api.deepseek.com",
        supports_images=True,
        context_window=200000,
        max_tokens=65536,
        thinking="high",
    )
    output.mkdir(parents=True, exist_ok=False)
    generated = []
    for original_task in original:
        task_id = str(original_task["task_id"])
        source = Path(original_task["path"])
        for record in original_task["files"]:
            if sha256(source / record["path"]) != record["sha256"]:
                raise ValueError(
                    f"Frozen task bytes changed: {task_id}/{record['path']}"
                )
        metadata = json.loads((source / "metadata.json").read_text())
        download._normalize_task_meta(metadata, task_id=task_id, expected_language="en")
        official_meta = json.loads((dataset / task_id / "metadata.json").read_text())
        if metadata != official_meta:
            raise ValueError(
                f"Fixed Task metadata differs from the complete native dataset: {task_id}"
            )
        task = output / f"workspacebench-lite-{task_id}"
        view = task / "environment/taskview"
        tests = task / "tests"
        view.mkdir(parents=True)
        tests.mkdir()
        for entry in metadata.get("data_manifest", []):
            relative = Path(entry["stored_relpath"])
            if relative.is_absolute() or ".." in relative.parts:
                raise ValueError("Native task input path escaped its directory")
            old = source / relative
            official = dataset / task_id / relative
            if not official.is_file() or sha256(official) != sha256(old):
                raise ValueError(f"Frozen task input changed: {task_id}/{relative}")
            destination = view / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(official, destination)
        public = agent_visible_metadata(metadata)
        (view / "metadata.json").write_text(
            json.dumps(public, ensure_ascii=False, indent=2) + "\n"
        )
        work_dir = f"{NATIVE_ROOT}/{RUN_NAME}/{task_id}/workdir"
        prompt = runner._wrap_prompt(
            prompt=str(metadata["task"]),
            work_dir=work_dir,
            prompt_head="",
            prompt_tail="",
            task_target_output_dir="model_output",
            language="en",
        )
        (task / "instruction.md").write_text(prompt)
        (view / "instruction.md").write_text(prompt)
        role = metadata["file_system"]
        config = {
            "native_src": "/opt/workspace-native/src",
            "openharness_parser": "/opt/workspace-native/src/agents/openharness.py",
            "metadata_path": "/taskview/metadata.json",
            "instruction_path": "/taskview/instruction.md",
            "agent_logs": "/logs/agent",
            "agent_logs_link": "/tmp/harbor-workspace-agent-logs",
            "standard_work_dir": f"/opt/workspace-native/standard/{builder.ROLE_DIRS[role]}",
            "output_dir": NATIVE_ROOT,
            "agent_name": "OpenHarness",
            "model_name": "DeepSeek-Flash",
            "run_name": "phase3",
            "timeout_sec": 2400,
            "task_resources": {
                "cpus": 2,
                "memory_mb": 8192,
                "pids": 512,
                "storage_mb": 20480,
            },
        }
        (view / "run.yaml").write_text(yaml.safe_dump(config, allow_unicode=True))
        command = (
            "mkdir -p /tmp/home /tmp/cache; "
            f"python3 /opt/harbor-workspace/task_container_entry.py --run-config /taskview/run.yaml --task-id {task_id} "
            f">{NATIVE_ROOT}/native-entry.log 2>&1; code=$?; "
            f'printf \'{{"exit_code":%s}}\\n\' "$code" >{NATIVE_ROOT}/native-entry-exit.json; '
            # A native timeout/storage failure ends the container and every
            # Harbor CLI process inside it. A normal exit keeps it for Judge.
            'if [ "$code" -ne 0 ]; then '
            "mkdir -p /logs/artifacts/native-guard; "
            f"cp {NATIVE_ROOT}/native-entry-exit.json /logs/artifacts/native-guard/; "
            f"cp {NATIVE_ROOT}/{RUN_NAME}/{task_id}/raw/container-isolation.json /logs/artifacts/native-guard/ 2>/dev/null || true; "
            f"cp {NATIVE_ROOT}/native-entry.log /logs/artifacts/native-guard/ 2>/dev/null || true; "
            'exit "$code"; fi; exec sleep infinity'
        )
        ready = f"{NATIVE_ROOT}/{RUN_NAME}/{task_id}/raw/harbor-ready.json"
        compose = {
            "services": {
                "main": {
                    "image": image,
                    "working_dir": "/tmp",
                    "init": True,
                    "read_only": True,
                    "entrypoint": ["bash", "-lc", command.replace("$", "$$")],
                    "command": [],
                    "cpus": 2,
                    "mem_limit": "8192m",
                    "pids_limit": 512,
                    "security_opt": ["no-new-privileges:true"],
                    "cap_drop": ["ALL"],
                    "environment": {
                        "HOME": "/tmp/home",
                        "XDG_CACHE_HOME": "/tmp/cache",
                        "PIP_CACHE_DIR": "/tmp/pip-cache",
                        "UV_CACHE_DIR": "/tmp/uv-cache",
                        "npm_config_cache": "/tmp/npm-cache",
                        "PYTHONDONTWRITEBYTECODE": "1",
                        "WORKSPACE_BENCH_TASK_STORAGE_QUOTA_MODE": "case-directory-watchdog",
                    },
                    "volumes": [
                        "./taskview:/taskview:ro",
                        f"native-results:{NATIVE_ROOT}",
                        "verifier-logs:/logs/verifier",
                        "artifacts:/logs/artifacts",
                    ],
                    "tmpfs": ["/tmp:rw,size=20480m,mode=1777"],
                    "healthcheck": {
                        "test": ["CMD-SHELL", f"test -f {ready}"],
                        "interval": "2s",
                        "timeout": "5s",
                        "retries": 720,
                    },
                }
            },
            "volumes": {"native-results": {}, "verifier-logs": {}, "artifacts": {}},
        }
        (task / "environment/docker-compose.yaml").write_text(
            yaml.safe_dump(compose, sort_keys=False)
        )
        task_config = {
            "schema_version": "1.1",
            "task": {"name": f"workspacebench-lite/{task_id}"},
            "metadata": {
                "benchmark": "WorkspaceBench Lite",
                "original_task_id": task_id,
                "original_content_sha256": original_task["content_sha256"],
                "judge_comparability": "diagnostic",
            },
            "artifacts": [
                {"source": NATIVE_ROOT, "exclude": ["*/workdir", "*/workdir/*"]}
            ],
            "agent": {"timeout_sec": 2400},
            "verifier": {"timeout_sec": 3900},
            "environment": {
                "docker_image": image,
                "build_timeout_sec": 1800,
                "cpus": 2,
                "memory_mb": 8192,
                "storage_mb": 20480,
                "workdir": work_dir,
            },
        }
        (task / "task.toml").write_text(toml.dumps(task_config))
        full = dict(metadata)
        full["__metadata_path"] = "/taskview/metadata.json"
        (tests / "metadata.json").write_text(
            json.dumps(full, ensure_ascii=False, indent=2) + "\n"
        )
        (tests / "test.sh").write_text(
            "#!/bin/bash\nset -euo pipefail\npython3 - <<'PY'\n"
            "import sys\nfrom pathlib import Path\nsys.path.insert(0, '/opt/harbor-workspace')\n"
            "from native_trial_bridge import verify_single_case\n"
            "verify_single_case(Path('/taskview/run.yaml'), Path('/tests/metadata.json'), Path('/logs/verifier/reward.txt'))\nPY\n"
        )
        generated.append(
            {
                "task_id": task_id,
                "path": str(task.resolve()),
                "original_content_sha256": original_task["content_sha256"],
                "prompt_sha256": sha256(task / "instruction.md"),
                "files": [
                    {"path": path.relative_to(task).as_posix(), "sha256": sha256(path)}
                    for path in sorted(task.rglob("*"))
                    if path.is_file()
                ],
            }
        )
    result = {
        "generated_tasks": generated,
        "seed_image_id": image,
        "model_config": model_config,
        "agent_profile": "legacy-eval-v1",
        "model_calls": 0,
    }
    (output / "generated-manifest.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    )
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    for name in ["native-eval", "dataset", "seed-ready", "frozen", "output"]:
        parser.add_argument(f"--{name}", type=Path, required=True)
    args = parser.parse_args()
    result = generate(
        args.native_eval, args.dataset, args.seed_ready, args.frozen, args.output
    )
    print(
        json.dumps(
            {
                "generated_tasks": len(result["generated_tasks"]),
                "seed_image_id": result["seed_image_id"],
                "model_calls": 0,
            }
        )
    )


if __name__ == "__main__":
    main()
