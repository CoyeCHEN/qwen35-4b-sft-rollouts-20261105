"""JobBench (upstream source) → Harbor task directories.

Produces, per upstream task::

    <out>/<split>/<profession>__<taskN>/
    ├── instruction.md            # the JobBench F.1 prompt, paths substituted
    ├── task.toml                 # Harbor manifest
    ├── environment/              # NO Dockerfile when --base-image is used
    │   ├── task_folder/          # the agent-visible fixture, verbatim
    │   └── output/.keep
    ├── solution/solve.sh         # non-zero placeholder (no oracle exists)
    └── tests/
        ├── test.sh
        ├── jobbench_verify.py
        ├── judge.py              # vendored, unmodified, SHA-checked
        └── RUBRICS.json

Design notes worth keeping in mind if you change this file:

* ``files_required_to_search/`` is **dropped**, not copied. Upstream treats it
  as grader-side material: the agent is expected to find equivalent sources on
  the web. Copying it in would hand over the answer key. Its *existence* is
  still meaningful — it marks the task as needing network access.
* ``task_card.md`` is dropped for the same reason; it spells out expected
  findings.
* ``environment/Dockerfile`` is only emitted in baked-image mode. In
  runtime-upload mode it must be absent, or Harbor skips uploading
  ``environment/`` entirely and the fixture never reaches the sandbox.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path.cwd()
TEMPLATE_DIR = Path(__file__).resolve().parent / "task-template"
VENDOR_DIR = (
    Path(os.environ.get("BENCHMARK_CACHE_ROOT", Path.home() / ".cache/harbor-rsi"))
    / "vendor/jobbench"
)

# Pinned upstream judge. Changing this invalidates comparability with any
# previously published numbers, so it is recorded in every task.toml.
EVALUATOR_REPOSITORY = "https://github.com/Job-Bench/job-bench-eval"
EVALUATOR_COMMIT = "bbeae9de5d2f0f6f162f053e03b37069b5f404c8"
EVALUATOR_SHA256 = "4e86a2e7f3e0790986332a3c72d96916211127396cb92f6501fce258d0a6856a"

DEFAULT_WORKDIR = "/workspace"

# Base for self-contained (baked) task images. The OpenHarness adapter and
# JobBench verifier are both Python applications. E2B builds this server-side.
BASE_IMAGE_FOR_BAKED = "python:3.12-slim-bookworm"

# split -> (candidate source dirs under <source-root>, expected task count)
SPLITS: dict[str, tuple[tuple[str, ...], int]] = {
    "main": (("dataset/main", "dataset"), 65),
    "easy": (("dataset/easy", "dataset_easy"), 63),
}


@dataclass(frozen=True)
class SourceTask:
    split: str
    profession: str
    task_name: str  # "task1"
    root: Path  # <source>/<profession>/<task1>

    @property
    def harbor_name(self) -> str:
        """Directory/tag-safe task id. Upstream uses lowercase professions and
        ``taskN`` already, so an ``__`` join is enough — but sanitize anyway so a
        future profession with a dash or space does not produce a broken image
        tag."""
        raw = f"{self.profession}__{self.task_name}"
        return "".join(c if (c.isalnum() or c == "_") else "_" for c in raw).lower()


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def resolve_split_root(source_root: Path, split: str) -> Path:
    dirs, _ = SPLITS[split]
    for candidate in dirs:
        if (source_root / candidate).is_dir():
            return source_root / candidate
    raise FileNotFoundError(f"none of {dirs} exist under {source_root} for split {split!r}")


def discover_tasks(source_root: Path, split: str) -> list[SourceTask]:
    root = resolve_split_root(source_root, split)
    tasks = [
        SourceTask(split, profession.name, task.name, task)
        for profession in sorted(root.iterdir())
        if profession.is_dir()
        for task in sorted(profession.iterdir())
        if task.is_dir() and (task / "task_folder" / "TASK_INSTRUCTIONS.txt").is_file()
    ]
    _, expected = SPLITS[split]
    if len(tasks) != expected:
        raise ValueError(
            f"split {split!r}: found {len(tasks)} tasks under {root}, expected {expected}. "
            "Refusing to generate a partial dataset."
        )
    return tasks


def load_judge() -> str:
    """Return the vendored judge source, verifying it is the pinned revision."""
    judge = VENDOR_DIR / "judge.py"
    if not judge.is_file():
        raise FileNotFoundError(
            f"{judge} missing. Re-fetch it:\n"
            f"  curl -fsSL -o {judge} "
            f"{EVALUATOR_REPOSITORY.replace('.git', '')}/raw/{EVALUATOR_COMMIT}/eval/judge.py"
        )
    actual = sha256_file(judge)
    if actual != EVALUATOR_SHA256:
        raise ValueError(
            f"vendor/judge.py SHA mismatch:\n  expected {EVALUATOR_SHA256}\n  actual   {actual}\n"
            "The judge defines the scores; a silent change makes results "
            "incomparable with previous runs."
        )
    return judge.read_text(encoding="utf-8")


def render_instruction(template: str, workdir: str) -> str:
    """Substitute the F.1 placeholder with the concrete runtime path.

    The template is the JobBench F.1 prompt verbatim (see the official
    ``run_benchmark_claude_code_cli.sh``); only the path placeholders differ.
    """
    if "{workdir}" not in template:
        raise ValueError("instruction template has no {workdir} placeholder")
    return template.replace("{workdir}", workdir)


def render_task_toml(
    *,
    task: SourceTask,
    keywords: list[str],
    network_required: bool,
    instruction_sha256: str,
    judge_sha256: str,
    base_image: str | None,
    workdir: str,
    baked_image: bool,
) -> str:
    template = (TEMPLATE_DIR / "task.toml").read_text(encoding="utf-8")

    # Runtime-upload mode needs network at the *environment* level, so the agent
    # can reach its model endpoint and (for 57/65 main tasks) search the web.
    network_mode = "public"

    # The whole line is a placeholder so baked mode can omit `docker_image`
    # entirely rather than leaving a dangling comment (not valid TOML).
    image_line = (
        f"docker_image = {json.dumps(base_image)}"
        if base_image
        else "# docker_image omitted: this task builds environment/Dockerfile"
    )

    replacements = {
        "__TASK_NAME__": json.dumps(f"jobbench/{task.split}__{task.harbor_name}"),
        "__KEYWORDS__": json.dumps(["jobbench", task.split, task.profession]),
        "__SPLIT__": json.dumps(task.split),
        "__PROFESSION__": json.dumps(task.profession),
        "__SOURCE_TASK__": json.dumps(f"{task.profession}/{task.task_name}"),
        "__NETWORK_REQUIRED__": "true" if network_required else "false",
        "__INSTRUCTION_SHA256__": json.dumps(instruction_sha256),
        "__JUDGE_SHA256__": json.dumps(judge_sha256),
        "__EVALUATOR_COMMIT__": EVALUATOR_COMMIT,
        "__DOCKER_IMAGE_LINE__": image_line,
        "__WORKDIR__": workdir,
        "__NETWORK_MODE__": json.dumps(network_mode),
    }

    out = template
    for key, value in replacements.items():
        out = out.replace(key, str(value))
    return out


def render_dockerfile(workdir: str) -> str:
    """Build a *self-contained* task image: base recipe + fixture, one Dockerfile.

    Used by ``--baked-image``. The base recipe is taken from
    ``images/Dockerfile.jobbench`` up to its ``BASE_RECIPE_END`` marker, minus the
    ``FROM`` line (which is re-emitted from ``BASE_IMAGE``) and minus the trailing
    ENTRYPOINT/CMD (E2B's own supervisor supplies the runtime command).

    This exists so there is exactly one place to edit when the dependency set
    changes. Duplicating the recipe here would let the two drift, and a drifted
    dependency list is invisible until scores come out wrong.

    Why self-contained rather than "base image + upload": E2B has no bind mounts
    and Harbor uploads ``environment/`` only when there is no Dockerfile. Baking
    the fixture in is the mode that works without owning a container registry.
    """
    recipe_path = Path(__file__).resolve().parent / "images" / "Dockerfile.jobbench"
    if not recipe_path.is_file():
        raise FileNotFoundError(f"base recipe not found: {recipe_path}")

    body = recipe_path.read_text(encoding="utf-8")
    marker = "# BASE_RECIPE_END"
    if marker not in body:
        raise ValueError(
            f"{recipe_path} is missing its '{marker}' marker; the self-contained "
            "build cannot tell where the runnable recipe ends"
        )
    body = body.split(marker, 1)[0]

    # Drop the base image's own FROM (we emit ours) and any trailing comments.
    lines = [ln for ln in body.splitlines() if not ln.startswith("FROM ")]
    while lines and (lines[-1].startswith("#") or not lines[-1].strip()):
        lines.pop()

    return (
        "# Generated by jobbench_e2b.adapter --baked-image mode.\n"
        "# Self-contained: the JobBench runtime recipe plus this task's fixture.\n"
        "# E2B builds this server-side, so no container registry is needed.\n"
        f"FROM {BASE_IMAGE_FOR_BAKED}\n\n" + "\n".join(lines) + f"\n\nWORKDIR {workdir}\n"
        f"COPY task_folder/ {workdir}/task_folder/\n"
        f"RUN mkdir -p {workdir}/output\n"
    )


def convert_one(
    task: SourceTask,
    out_root: Path,
    *,
    judge_source: str,
    judge_sha256: str,
    instruction_template: str,
    base_image: str | None,
    workdir: str,
    overwrite: bool,
) -> dict:
    target = out_root / task.harbor_name
    if target.exists():
        if not overwrite:
            raise FileExistsError(f"{target} exists; pass --overwrite")
        shutil.rmtree(target)

    env_dir = target / "environment"
    tests_dir = target / "tests"
    env_dir.mkdir(parents=True)
    tests_dir.mkdir(parents=True)

    src_task_folder = task.root / "task_folder"

    # --- fixture: task_folder verbatim, nothing else ------------------------
    shutil.copytree(src_task_folder, env_dir / "task_folder")
    output_dir = env_dir / "output"
    output_dir.mkdir()
    (output_dir / ".keep").write_text("", encoding="utf-8")

    # --- environment/Dockerfile: only in baked mode -------------------------
    if base_image is None:
        (env_dir / "Dockerfile").write_text(render_dockerfile(workdir), encoding="utf-8")

    # --- instruction.md -----------------------------------------------------
    instruction = render_instruction(instruction_template, workdir)
    (target / "instruction.md").write_text(instruction, encoding="utf-8")

    # --- tests/ -------------------------------------------------------------
    (tests_dir / "RUBRICS.json").write_text(
        (task.root / "RUBRICS.json").read_text(encoding="utf-8"), encoding="utf-8"
    )
    (tests_dir / "judge.py").write_text(judge_source, encoding="utf-8")
    for name in ("jobbench_verify.py", "test.sh"):
        shutil.copy2(TEMPLATE_DIR / "tests" / name, tests_dir / name)
    # test.sh carries the concrete workdir.
    test_sh = tests_dir / "test.sh"
    test_sh.write_text(
        test_sh.read_text(encoding="utf-8").replace("__WORKDIR__", workdir),
        encoding="utf-8",
    )
    test_sh.chmod(0o755)

    # --- solution/ ----------------------------------------------------------
    (target / "solution").mkdir()
    shutil.copy2(TEMPLATE_DIR / "solution" / "solve.sh", target / "solution" / "solve.sh")
    (target / "solution" / "solve.sh").chmod(0o755)

    # --- task.toml ----------------------------------------------------------
    network_required = (task.root / "files_required_to_search").is_dir()
    task_toml = render_task_toml(
        task=task,
        keywords=[],
        network_required=network_required,
        instruction_sha256=sha256_text(instruction),
        judge_sha256=judge_sha256,
        base_image=base_image,
        workdir=workdir,
        baked_image=base_image is None,
    )
    (target / "task.toml").write_text(task_toml, encoding="utf-8")

    return {
        "harbor_name": task.harbor_name,
        "split": task.split,
        "profession": task.profession,
        "source_task": f"{task.profession}/{task.task_name}",
        "network_required": network_required,
        "instruction_sha256": sha256_text(instruction),
        "task_toml_sha256": sha256_text(task_toml),
        "judge_sha256": judge_sha256,
        "fixture_files": sorted(
            p.relative_to(env_dir).as_posix()
            for p in (env_dir / "task_folder").rglob("*")
            if p.is_file()
        ),
    }


def run(
    *,
    source_root: Path,
    output_root: Path,
    splits: list[str],
    base_image: str | None,
    workdir: str,
    overwrite: bool,
    limit: int | None = None,
    task_ids: list[str] | None = None,
) -> dict:
    judge_source = load_judge()
    judge_sha256 = sha256_file(VENDOR_DIR / "judge.py")
    instruction_template = (TEMPLATE_DIR / "instruction.md").read_text(encoding="utf-8")

    manifest: dict = {
        "schema": "jobbench-e2b.dataset.v1",
        "source_root": str(source_root),
        "workdir": workdir,
        "base_image": base_image,
        "evaluator_commit": EVALUATOR_COMMIT,
        "evaluator_sha256": EVALUATOR_SHA256,
        "splits": {},
    }

    for split in splits:
        tasks = discover_tasks(source_root, split)
        if task_ids:
            wanted = {t.replace("/", "__") if "/" in t else t for t in task_ids}
            tasks = [t for t in tasks if t.harbor_name in wanted or t.task_name in wanted]
        if limit is not None:
            tasks = tasks[:limit]

        out_root = output_root / split
        out_root.mkdir(parents=True, exist_ok=True)

        records = []
        for task in tasks:
            records.append(
                convert_one(
                    task,
                    out_root,
                    judge_source=judge_source,
                    judge_sha256=judge_sha256,
                    instruction_template=instruction_template,
                    base_image=base_image,
                    workdir=workdir,
                    overwrite=overwrite,
                )
            )
            print(f"  [{split}] {task.harbor_name}")

        manifest["splits"][split] = {"count": len(records), "tasks": records}
        (out_root / "manifest.json").write_text(
            json.dumps(manifest["splits"][split], indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

    return manifest
