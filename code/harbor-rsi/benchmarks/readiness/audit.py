"""Offline full-task audit and native Job configuration export (never runs jobs)."""

import argparse
import asyncio
import ast
import csv
import json
import re
import shlex
from pathlib import Path
from typing import Any

import yaml
from dirhash import dirhash

from harbor.environments.definition import (
    environment_content_hash,
    require_agent_environment_definition,
)
from harbor.models.job.config import DatasetConfig, JobConfig
from harbor.models.task.task import Task
from harbor.models.task.config import VerifierEnvironmentMode
from harbor.publisher.packager import Packager
from harbor.tasks.client import TaskClient

COUNTS = {
    "alfworld": 134,
    "clawgym": 200,
    "tb21": 89,
    "jobbench-main": 65,
    "jobbench-easy": 63,
}
PROVIDERS = {
    "alfworld": "harbor.environments.e2b_resumable:ResumableE2BEnvironment",
    "clawgym": "harbor.environments.e2b_resumable:ResumableE2BEnvironment",
    "tb21": "harbor_remote_docker:RemoteDockerEnvironment",
    "jobbench-main": "harbor_remote_docker:RemoteDockerEnvironment",
    "jobbench-easy": "harbor_remote_docker:RemoteDockerEnvironment",
}


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n")


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        raise ValueError(f"Refusing empty inventory: {path}")
    fields = list(dict.fromkeys(k for row in rows for k in row))
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def dockerfile_images(text: str) -> list[tuple[str, str]]:
    """Resolve ARG-backed FROM and distinguish internal stages from registries."""
    args: dict[str, str] = {}
    stages: set[str] = set()
    images = []
    text = text.replace("\\\n", " ")
    for line in text.splitlines():
        parts = shlex.split(line, comments=True)
        if not parts:
            continue
        if parts[0].upper() == "ARG" and len(parts) > 1 and "=" in parts[1]:
            key, value = parts[1].split("=", 1)
            args[key] = value
        if parts[0].upper() != "FROM":
            continue
        tokens = [x for x in parts[1:] if not x.startswith("--")]
        if not tokens:
            raise ValueError("FROM without image")
        image = re.sub(
            r"\$(?:\{(\w+)\}|(\w+))", lambda m: args.get(m[1] or m[2], m[0]), tokens[0]
        )
        kind = (
            "internal_stage"
            if image in stages or image == "scratch"
            else "unresolved"
            if "$" in image
            else "from"
        )
        images.append((image, kind))
        if len(tokens) >= 3 and tokens[1].upper() == "AS":
            stages.add(tokens[2])
    return images


def task_images(task: Task) -> list[dict[str, Any]]:
    images: list[dict[str, Any]] = []
    for role, directory, config in [
        ("agent", task.paths.environment_dir, task.config.environment),
        ("verifier", task.paths.tests_dir, task.config.verifier.environment),
    ]:
        if config and config.docker_image:
            images.append(
                {
                    "role": role,
                    "image": config.docker_image,
                    "kind": "prebuilt",
                    "file": "task.toml",
                }
            )
        for p in sorted(directory.rglob("*")):
            if not p.is_file():
                continue
            if p.name.startswith("Dockerfile") or p.suffix == ".dockerfile":
                for image, kind in dockerfile_images(p.read_text()):
                    images.append(
                        {
                            "role": role,
                            "image": image,
                            "kind": kind,
                            "file": str(p.relative_to(task.paths.task_dir)),
                        }
                    )
            if p.name in {
                "docker-compose.yaml",
                "docker-compose.yml",
                "compose.yaml",
                "compose.yml",
            }:
                compose = yaml.safe_load(p.read_text()) or {}
                for service, definition in compose.get("services", {}).items():
                    if definition.get("image"):
                        image = definition["image"]
                        images.append(
                            {
                                "role": role,
                                "image": image,
                                "kind": "compose_unresolved"
                                if "$" in image
                                else "compose",
                                "file": str(p.relative_to(task.paths.task_dir)),
                                "service": service,
                            }
                        )
    return images


def dependencies(task: Task, benchmark: str) -> list[dict[str, Any]]:
    rows = []
    for p in sorted(task.paths.task_dir.rglob("*")):
        if (
            not p.is_file()
            or p.suffix not in {".sh", ".py", ".toml", ".yaml", ".yml"}
            and not p.name.startswith("Dockerfile")
            and not p.name.endswith("requirements.txt")
        ):
            continue
        try:
            text = p.read_text()
        except UnicodeError:
            continue
        filename = str(p.relative_to(task.paths.task_dir))
        if p.name.endswith("requirements.txt"):
            rows.extend(
                {
                    "benchmark": benchmark,
                    "task_id": task.name,
                    "file": filename,
                    "kind": "declared_python_requirement",
                    "dependency": line.strip(),
                    "status": "static_only",
                }
                for line in text.splitlines()
                if line.strip() and not line.startswith("#")
            )
        if p.suffix == ".py":
            try:
                nodes = ast.walk(ast.parse(text))
                imports = sorted(
                    {
                        name
                        for node in nodes
                        for name in (
                            [alias.name.split(".")[0] for alias in node.names]
                            if isinstance(node, ast.Import)
                            else [node.module.split(".")[0]]
                            if isinstance(node, ast.ImportFrom) and node.module
                            else []
                        )
                    }
                )
            except SyntaxError as exc:
                imports = [f"syntax_error:{exc.lineno}"]
            rows.extend(
                {
                    "benchmark": benchmark,
                    "task_id": task.name,
                    "file": filename,
                    "kind": "python_import",
                    "dependency": name,
                    "status": "static_only",
                }
                for name in imports
            )
        for number, line in enumerate(text.splitlines(), 1):
            if re.search(
                r"(pip[0-9]? |uvx? |apt-get |wget |curl |npm |cargo |cmake |make |https?://|privileged:|/dev/kvm|network_mode:|gpus:|docker.sock)",
                line,
            ):
                rows.append(
                    {
                        "benchmark": benchmark,
                        "task_id": task.name,
                        "file": filename,
                        "line": number,
                        "kind": "runtime_or_build_requirement",
                        "dependency": line.strip(),
                        "status": "not_executed",
                    }
                )
    return rows


def job_config(benchmark: str, path: Path) -> dict[str, Any]:
    provider: dict[str, Any] = {"import_path": PROVIDERS[benchmark], "delete": True}
    if "RemoteDocker" in provider["import_path"]:
        provider["kwargs"] = {
            "endpoint": "ssh://aibox-149",
            "staging_root": "/home/chenkeyi/.cache/harbor-rsi/full-readiness",
            "project_namespace": "fullreadiness",
        }
    verifier = {}
    if benchmark.startswith("jobbench"):
        verifier = {
            "env": {
                "JOBBENCH_EVALUATED_MODEL": "nop-readiness",
                "JUDGE_MODEL": "not-authorized",
                "JUDGE_API_KEY": "",
                "JUDGE_API_BASE": "http://127.0.0.1:9",
            }
        }
    if benchmark == "clawgym":
        verifier = {
            "env": {
                "CLAWGYM_JUDGE_API_KEY": "",
                "CLAWGYM_JUDGE_BASE_URL": "",
                "CLAWGYM_JUDGE_MODEL": "not-authorized",
            }
        }
    return {
        "job_name": f"full-readiness-{benchmark}",
        "jobs_dir": "jobs/full-readiness",
        "n_attempts": 1,
        "n_concurrent_trials": 1,
        "retry": {"max_retries": 0},
        "environment": provider,
        "agents": [{"name": "nop"}],
        "verifier": verifier,
        "datasets": [{"path": str(path)}],
    }


async def audit(
    root: Path,
    output: Path,
    repository: Path,
    image_probes: dict[str, Any],
    e2b_probes: dict[str, Any],
) -> dict[str, Any]:
    output.mkdir(parents=True, exist_ok=True)
    prior = list(
        csv.DictReader(
            (repository / "artifacts/benchmark-reports/final-4x10/cases.csv").open()
        )
    )
    tasks, readiness, images, deps = [], [], [], []
    summary = {}
    for benchmark, expected in COUNTS.items():
        directory = root / (
            "jobbench/" + benchmark.removeprefix("jobbench-")
            if benchmark.startswith("jobbench-")
            else benchmark
        )
        dataset = DatasetConfig(path=directory)
        configs = await dataset.get_task_configs()
        if len(configs) != expected:
            raise ValueError(
                f"{benchmark}: native discovery {len(configs)} != {expected}"
            )
        native = await TaskClient().download_tasks([c.get_task_id() for c in configs])
        names = []
        for result in sorted(native.results, key=lambda r: str(r.path)):
            task = Task(result.path)
            require_agent_environment_definition(
                task.paths.environment_dir,
                docker_image=task.config.environment.docker_image,
            )
            if (
                task.config.verifier.environment_mode
                == VerifierEnvironmentMode.SEPARATE
            ):
                config = task.config.verifier.environment
                require_agent_environment_definition(
                    task.paths.tests_dir,
                    docker_image=config.docker_image if config else None,
                )
            names.append(task.name)
            digest, _ = Packager.compute_content_hash(result.path)
            native_checksum = dirhash(result.path, "sha256")
            metadata = task.config.metadata
            source_task = metadata.get("source_task", task.short_name)
            previous = next(
                (
                    p
                    for p in prior
                    if p["benchmark"] == benchmark.split("-")[0]
                    and p["task_id"] == source_task
                    and benchmark != "jobbench-easy"
                ),
                None,
            )
            mode = str(
                metadata.get(
                    "score_mode",
                    "official-tests"
                    if benchmark == "tb21"
                    else "official-success"
                    if benchmark == "alfworld"
                    else "judge",
                )
            )
            revision = metadata.get(
                "upstream_revision",
                "sha256:" + digest
                if benchmark == "tb21"
                else "d43a66575635da0d3f6cb9a20976dc1a60f3ffc9"
                if benchmark.startswith("jobbench")
                else "alfworld==0.4.2;json_2.1.1+tw-pddl_2.1.3;valid_unseen",
            )
            refs = task_images(task)
            pending = []
            for ref in refs:
                backend = (
                    "e2b" if benchmark in {"alfworld", "clawgym"} else "remote-docker"
                )
                probe = (
                    image_probes.get(ref["image"], {"status": "not_probed"})
                    if backend == "remote-docker"
                    else {"status": "e2b_registry_input_not_149"}
                )
                recipe_only = ref["kind"] == "from" and bool(
                    task.config.environment.docker_image
                )
                ref["selected_runtime_input"] = (
                    not recipe_only and ref["kind"] != "internal_stage"
                )
                images.append(
                    {
                        "benchmark": benchmark,
                        "task_id": task.name,
                        "provider": backend,
                        **ref,
                        **probe,
                    }
                )
                if (
                    ref["selected_runtime_input"]
                    and backend == "remote-docker"
                    and probe["status"] != "present"
                ):
                    pending.append(ref["image"])
            template = {}
            if benchmark in {"alfworld", "clawgym"}:
                for role, env_dir, config in [
                    ("agent", task.paths.environment_dir, task.config.environment),
                    (
                        "verifier",
                        task.paths.tests_dir,
                        task.config.verifier.environment,
                    ),
                ]:
                    if (
                        role == "verifier"
                        and task.config.verifier.environment_mode
                        != VerifierEnvironmentMode.SEPARATE
                    ):
                        continue
                    identity = environment_content_hash(
                        env_dir, docker_image=config.docker_image if config else None
                    )
                    alias = f"{task.short_name}__{identity[:12]}".replace(
                        "/", "__"
                    ).replace(".", "-")
                    template[role] = {
                        "alias": alias,
                        **e2b_probes.get(alias, {"status": "not_probed"}),
                    }
            is_cached = (
                not pending
                if not template
                else all(t["status"] == "present" for t in template.values())
            )
            row = {
                "benchmark": benchmark,
                "task_id": task.name,
                "source_task": source_task,
                "source_revision": revision,
                "task_hash": digest,
                "task_hash_algorithm": "Harbor Packager.compute_content_hash",
                "native_dirhash": native_checksum,
                "adapter_status": "FULLY_REGISTERED",
                "provider": PROVIDERS[benchmark],
                "verifier": mode,
                "image/asset_status": "template_cached_not_dynamic"
                if template and is_cached
                else "cached_inputs_build_unverified"
                if is_cached
                else "blocked_or_unverified",
                "readiness_status": "STATIC_READY",
                "prior_run": previous["result_path"] if previous else "none",
                "prior_task_hash": previous["task_hash"] if previous else "",
                "prior_same_content": bool(
                    previous and previous["task_hash"] == native_checksum
                ),
                "task_path": str(result.path),
            }
            tasks.append(row)
            readiness.append(
                {
                    **row,
                    "level1": "passed",
                    "level2": "unverified",
                    "level3": "not_run",
                    "level4": "historical_sample" if previous else "not_authorized",
                    "missing_images": json.dumps(sorted(set(pending))),
                    "e2b_templates": json.dumps(template),
                    "cpu": task.config.environment.cpus,
                    "ram_mb": task.config.environment.memory_mb,
                    "disk_mb": task.config.environment.storage_mb,
                    "gpu": task.config.environment.gpus,
                    "agent_timeout_sec": task.config.agent.timeout_sec,
                    "verifier_timeout_sec": task.config.verifier.timeout_sec,
                    "judge_complete": "requires_paid_authorization"
                    if mode in {"hybrid", "judge"}
                    else "not_run",
                    "environment_hash": environment_content_hash(
                        task.paths.environment_dir,
                        docker_image=task.config.environment.docker_image,
                    ),
                }
            )
            deps.extend(dependencies(task, benchmark))
        if len(names) != len(set(names)):
            raise ValueError(f"Duplicate task identities in {benchmark}")
        config = job_config(benchmark, directory)
        JobConfig.model_validate(config)
        write_json(output / "full-job-configs" / f"{benchmark}-nop.json", config)
        summary[benchmark] = {
            "official_count": expected,
            "generated": len(configs),
            "native_taskclient_parsed": len(native.results),
            "static_passed": len(names),
            "new_dynamic_passed": 0,
            "historical_real_samples": sum(
                bool(t["prior_run"] != "none")
                for t in tasks
                if t["benchmark"] == benchmark
            ),
            "full_evaluated": False,
        }
    write_csv(output / "full-task-manifest.csv", tasks)
    write_csv(output / "task-readiness.csv", readiness)
    write_csv(output / "image-inventory.csv", images)
    write_csv(output / "environment-dependencies.csv", deps)
    write_json(
        output / "preflight-results.json",
        {
            "status": "partial",
            "summary": summary,
            "scope": "TaskClient,Task,JobConfig parsing only; no Job launched by audit",
            "full_evaluated": False,
        },
    )
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--image-probes", type=Path)
    parser.add_argument("--e2b-probes", type=Path)
    args = parser.parse_args()
    images = json.loads(args.image_probes.read_text()) if args.image_probes else {}
    e2b = json.loads(args.e2b_probes.read_text()) if args.e2b_probes else {}
    summary = asyncio.run(
        audit(
            args.task_root.resolve(),
            args.output.resolve(),
            Path(__file__).resolve().parents[2],
            images,
            e2b,
        )
    )
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
