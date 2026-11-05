from __future__ import annotations

import ast
import hashlib
import json
import shutil
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Iterable


UPSTREAM_REVISION = "c8cbd1d0df033af24fc14064d40d6964ca8f611f"
DEFAULT_DATASET_PATH = (
    Path.home() / ".cache/harbor-rsi/sources/clawgym/benchmark_data.jsonl"
)
DATASET_SHA256 = "b2fede029e73a769ad294089a735108be4396294590ec00c9527ac60b1da0f72"
REWARD_PATHS = {"reward/test.py", "test.py", "grader.py", "reward/grader.py"}
OFFICIAL_CODE_WEIGHT = 0.7
OFFICIAL_RUBRIC_WEIGHT = 0.3
VERIFIER_PACKAGES = {"yaml": "PyYAML==6.0.3"}


def verifier_requirements(source: str) -> list[str]:
    """Declare checker libraries in the verifier image, never the agent image."""
    imported: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    return sorted(
        VERIFIER_PACKAGES[name] for name in imported & VERIFIER_PACKAGES.keys()
    )


@dataclass(frozen=True)
class ClawGymRecord:
    ordinal: int
    raw: dict[str, Any]

    @property
    def prompt(self) -> str:
        value = self.raw.get("prompt")
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"record {self.ordinal} has no non-empty prompt")
        return value

    @property
    def input_files(self) -> list[dict[str, Any]]:
        files = self.raw.get("input_files") or []
        if not isinstance(files, list):
            raise ValueError(f"record {self.ordinal} input_files must be a list")
        return files

    @property
    def rules(self) -> list[dict[str, Any]]:
        rules = self.raw.get("rules") or []
        if not isinstance(rules, list):
            raise ValueError(f"record {self.ordinal} rules must be a list")
        return rules

    @property
    def has_code_score(self) -> bool:
        return bool(str(self.raw.get("hook_code") or "").strip())

    @property
    def has_rubric_score(self) -> bool:
        return bool(self.rules)

    @property
    def content_hash(self) -> str:
        payload = json.dumps(self.raw, ensure_ascii=False, sort_keys=True).encode()
        return hashlib.sha256(payload).hexdigest()

    @property
    def task_id(self) -> str:
        return f"task-{self.ordinal:06d}-{self.content_hash[:10]}"


def _safe_relative_path(value: str, *, allow_reward: bool = False) -> str:
    normalized = value.replace("\\", "/")
    path = PurePosixPath(normalized)
    if path.is_absolute() or ".." in path.parts or not normalized.strip():
        raise ValueError(f"unsafe ClawGym input path: {value!r}")
    clean = path.as_posix()
    if clean in REWARD_PATHS and not allow_reward:
        raise ValueError("reward checker must remain verifier-only")
    return clean


def read_records(dataset_path: Path) -> list[ClawGymRecord]:
    records: list[ClawGymRecord] = []
    with Path(dataset_path).open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            try:
                raw = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"line {line_number}: invalid JSON: {exc}") from exc
            if not isinstance(raw, dict):
                raise ValueError(f"line {line_number}: expected JSON object")
            record = ClawGymRecord(len(records) + 1, raw)
            record.prompt
            for item in record.input_files:
                if not isinstance(item, dict):
                    raise ValueError(
                        f"record {record.ordinal}: input file is not an object"
                    )
                _safe_relative_path(
                    str(item.get("file_path") or ""),
                    allow_reward=True,
                )
            records.append(record)
    if not records:
        raise ValueError(f"no records found in {dataset_path}")
    return records


def _write_content(path: Path, content: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(content, bytes):
        path.write_bytes(content)
    else:
        path.write_text(str(content), encoding="utf-8")


class ClawGymAdapter:
    """Generate standard Harbor tasks from ClawGym JSONL records."""

    def __init__(
        self,
        output_dir: Path,
        *,
        dataset_path: Path | None = None,
        template_dir: Path | None = None,
        agent_timeout_sec: float = 3000.0,
        verifier_timeout_sec: float = 900.0,
        overwrite: bool = False,
    ) -> None:
        self.output_dir = Path(output_dir)
        self.dataset_path = Path(dataset_path or DEFAULT_DATASET_PATH)
        self.template_dir = Path(
            template_dir or Path(__file__).parent / "task-template"
        )
        self.agent_timeout_sec = float(agent_timeout_sec)
        self.verifier_timeout_sec = float(verifier_timeout_sec)
        self.overwrite = overwrite

    def select_records(
        self,
        records: list[ClawGymRecord],
        *,
        limit: int | None = None,
        task_ids: Iterable[str] | None = None,
    ) -> list[ClawGymRecord]:
        selected = records
        wanted = set(task_ids or [])
        if wanted:
            selected = [
                r for r in records if r.task_id in wanted or str(r.ordinal) in wanted
            ]
            if len(selected) != len(wanted):
                found = {r.task_id for r in selected} | {
                    str(r.ordinal) for r in selected
                }
                raise ValueError(f"unknown ClawGym task IDs: {sorted(wanted - found)}")
        if limit is not None:
            if limit <= 0:
                raise ValueError("limit must be positive")
            selected = selected[:limit]
        if not selected:
            raise ValueError("selection matched no ClawGym records")
        return selected

    def generate_task(self, record: ClawGymRecord) -> Path:
        task_dir = self.output_dir / record.task_id
        if task_dir.exists():
            if not self.overwrite:
                raise FileExistsError(f"task already exists: {task_dir}")
            shutil.rmtree(task_dir)
        task_dir.mkdir(parents=True)

        environment_dir = task_dir / "environment"
        agent_workspace = environment_dir / "agent_workspace"
        tests_dir = task_dir / "tests"
        solution_dir = task_dir / "solution"
        for directory in (agent_workspace, tests_dir, solution_dir):
            directory.mkdir(parents=True)

        input_manifest: list[dict[str, Any]] = []
        reward_code: str | None = None
        for item in record.input_files:
            relative = _safe_relative_path(
                str(item.get("file_path") or ""),
                allow_reward=True,
            )
            content = item.get("content", "")
            if relative in REWARD_PATHS:
                reward_code = str(content)
                continue
            destination = agent_workspace / relative
            _write_content(destination, content)
            input_manifest.append(
                {
                    "file_path": relative,
                    "sha256": hashlib.sha256(destination.read_bytes()).hexdigest(),
                }
            )

        if record.has_code_score and reward_code is None:
            raise ValueError(
                f"record {record.ordinal} declares hook_code but has no reward file"
            )
        (tests_dir / "official_reward.py").write_text(
            reward_code or "", encoding="utf-8"
        )
        (tests_dir / "record.json").write_text(
            json.dumps(
                {
                    "ordinal": record.ordinal,
                    "content_hash": record.content_hash,
                    "prompt": record.prompt,
                    "hook_code": str(record.raw.get("hook_code") or ""),
                    "rules": record.rules,
                    "score_weights": {
                        "code": OFFICIAL_CODE_WEIGHT,
                        "rubric": OFFICIAL_RUBRIC_WEIGHT,
                    },
                    "missing_component_policy": "use_available_component",
                    "target_files": [
                        str(rule.get("file_path"))
                        for rule in record.rules
                        if rule.get("file_path")
                    ],
                    "input_manifest": input_manifest,
                },
                indent=2,
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )
        (task_dir / "instruction.md").write_text(
            record.prompt.rstrip() + "\n", encoding="utf-8"
        )
        (environment_dir / "Dockerfile").write_text(
            (self.template_dir / "environment" / "Dockerfile").read_text(),
            encoding="utf-8",
        )
        (tests_dir / "Dockerfile").write_text(
            (self.template_dir / "tests" / "Dockerfile").read_text(), encoding="utf-8"
        )
        requirements = verifier_requirements(reward_code or "")
        if requirements:
            (tests_dir / "verifier-requirements.txt").write_text(
                "\n".join(requirements) + "\n", encoding="utf-8"
            )
            dockerfile = tests_dir / "Dockerfile"
            dockerfile.write_text(
                dockerfile.read_text().replace(
                    "WORKDIR /workspace\n",
                    "WORKDIR /workspace\nCOPY verifier-requirements.txt /tests/verifier-requirements.txt\n"
                    "RUN python3 -m pip install --no-cache-dir -r /tests/verifier-requirements.txt\n",
                ),
                encoding="utf-8",
            )
        (tests_dir / "test.sh").write_text(
            (self.template_dir / "tests" / "test.sh").read_text(), encoding="utf-8"
        )
        (tests_dir / "evaluate.py").write_text(
            (self.template_dir / "tests" / "evaluate.py").read_text(), encoding="utf-8"
        )
        rubric_verifier = self.template_dir / "tests" / "rubric_verifier.py"
        if rubric_verifier.exists():
            (tests_dir / "rubric_verifier.py").write_text(
                rubric_verifier.read_text(), encoding="utf-8"
            )
        (tests_dir / "test.sh").chmod(0o755)
        (solution_dir / "solve.sh").write_text(
            "#!/bin/sh\n# Reference solution is benchmark-owned and intentionally omitted.\n",
            encoding="utf-8",
        )
        (solution_dir / "solve.sh").chmod(0o755)

        task_toml = (self.template_dir / "task.toml").read_text()
        replacements = {
            "{task_name}": f"clawgym/{record.task_id}",
            "{content_hash}": record.content_hash,
            "{agent_timeout}": str(self.agent_timeout_sec),
            "{verifier_timeout}": str(self.verifier_timeout_sec),
            "{score_mode}": (
                "hybrid"
                if record.has_rubric_score and record.has_code_score
                else "rubric"
                if record.has_rubric_score
                else "code"
            ),
            "{score_weight_code}": str(OFFICIAL_CODE_WEIGHT),
            "{score_weight_rubric}": str(OFFICIAL_RUBRIC_WEIGHT),
        }
        for needle, value in replacements.items():
            task_toml = task_toml.replace(needle, value)
        (task_dir / "task.toml").write_text(task_toml, encoding="utf-8")
        return task_dir

    def generate(
        self,
        *,
        limit: int | None = None,
        task_ids: Iterable[str] | None = None,
    ) -> list[Path]:
        records = self.select_records(
            read_records(self.dataset_path), limit=limit, task_ids=task_ids
        )
        self.output_dir.mkdir(parents=True, exist_ok=True)
        paths = [self.generate_task(record) for record in records]
        # Use Harbor's own packager algorithm so local references are identical
        # to those produced by `harbor add` and `harbor publish`.
        from harbor.models.dataset.manifest import (
            DatasetInfo,
            DatasetManifest,
            DatasetTaskRef,
        )
        from harbor.models.task.task import Task
        from harbor.publisher.packager import Packager

        refs: list[DatasetTaskRef] = []
        for path in paths:
            Task(path)
            digest, _ = Packager.compute_content_hash(path)
            refs.append(
                DatasetTaskRef(
                    name=Task(path, disable_verification=True).name,
                    digest=f"sha256:{digest}",
                )
            )
        manifest = {
            "benchmark": "ClawGym-Bench",
            "upstream_revision": UPSTREAM_REVISION,
            "dataset_sha256": hashlib.sha256(
                self.dataset_path.read_bytes()
            ).hexdigest(),
            "task_count": len(paths),
            "tasks": [ref.model_dump(mode="json") for ref in refs],
        }
        (self.output_dir / "source_manifest.json").write_text(
            json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
        )
        dataset = DatasetManifest(
            dataset=DatasetInfo(
                name="clawgym/clawgym-bench",
                version="c8cbd1d",
                description="ClawGym-Bench tasks generated from the pinned upstream revision.",
            ),
            tasks=refs,
        )
        (self.output_dir / "dataset.toml").write_text(
            dataset.to_toml(), encoding="utf-8"
        )
        return paths
