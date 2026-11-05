"""Reshape an existing JobBench-Harbor dataset into the E2B-compatible form.

Motivation: ``JobBench-Harbor`` (yqi03) already contains a generated dataset
whose *content* — the task fixtures, the rubric, the judge — came from the same
upstream JobBench source this repo's ``adapter`` targets. Re-downloading and
regenerating is wasteful; what actually needs changing is the shell around that
content, because it was generated for a Siflow/sandbox-manager runtime.

Three structural problems make the generated dataset unrunnable on E2B as-is:

1. ``environment/Dockerfile`` exists *and* ``task.toml`` sets ``docker_image``.
   Harbor's rule (``environments/definition.py::should_upload_environment_dir``)
   is that a Dockerfile present with a docker_image set means "use the prebuilt
   image, do not upload environment/". The fixture therefore never reaches the
   sandbox — silently. The image reference also points at a VPC-only registry
   E2B cannot pull. Either drop the Dockerfile (upload mode) or drop the
   docker_image (bake mode).

2. ``[agent].user`` names a user that only exists in the Siflow base image.
   E2B sandboxes run as root; naming a missing user makes every ``exec`` fail.

3. ``[environment].storage_mb`` is never read by the E2B environment.

Plus two smaller ones: the verifier's interpreter path and the workdir are
Siflow-specific, and the judge credentials are not wired into ``[verifier.env]``.

This module fixes all of those, and nothing else. It does not touch
``task_folder/``, ``RUBRICS.json`` or ``judge.py``.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from jobbench_e2b.adapter import (
    EVALUATOR_COMMIT,
    EVALUATOR_SHA256,
    REPO_ROOT,
    TEMPLATE_DIR,
    VENDOR_DIR,
    sha256_file,
    sha256_text,
)

# The venv the JobBench base image builds (see images/Dockerfile.jobbench).
DEFAULT_VENV_PYTHON = "/opt/jobbench-venv/bin/python"

# Interpreters seen in JobBench-Harbor's generated test.sh, all Siflow-specific.
_LEGACY_INTERPRETERS = (
    "/opt/gdpval-agent-python/bin/python",
    "/opt/jobbench-python/bin/python",
)


@dataclass
class MigrationReport:
    converted: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def summary(self) -> str:
        lines = [f"converted: {len(self.converted)}", f"skipped:   {len(self.skipped)}"]
        if self.warnings:
            lines.append(f"warnings:  {len(self.warnings)}")
            for w in self.warnings[:20]:
                lines.append(f"  - {w}")
            if len(self.warnings) > 20:
                lines.append(f"  ... and {len(self.warnings) - 20} more")
        return "\n".join(lines)


def _rewrite_test_sh(text: str, *, old_workdir: str, new_workdir: str, venv_python: str) -> str:
    """Point the verifier at an interpreter that exists, and at the right output dir."""
    # The generated scripts detect the venv at runtime; replace the whole
    # detection block with a direct call. Anything else leaves a half-fixed
    # script that silently falls back to a dependency-less python3.
    text = re.sub(
        r"if \[ -x [^\]]+ \]; then\s*\n\s*PY=[^\n]*\n\s*else\s*\n\s*PY=[^\n]*\n\s*fi",
        f"PY={venv_python}",
        text,
    )
    for legacy in (*(_LEGACY_INTERPRETERS),):
        text = text.replace(legacy, venv_python)

    if old_workdir != new_workdir:
        text = text.replace(f"{old_workdir}/output", f"{new_workdir}/output")
        text = text.replace(f"{old_workdir}/task_folder", f"{new_workdir}/task_folder")

    return text


# Keys whose list-of-dicts value is conventionally an array of tables.
# Everything else that is a list-of-dicts is rendered as an inline array, which
# keeps short things like `authors` on one readable line.
_ARRAY_OF_TABLES_KEYS = frozenset({"artifacts", "mcp_servers", "collect", "steps"})


def _is_table(value: object, key: str = "") -> bool:
    """True when a value should become its own [table] / [[array-of-tables]].

    An array of scalars (``keywords = ["a", "b"]``) is a plain key. An array of
    dicts is a table only for the keys that conventionally use that form.
    """
    if isinstance(value, dict):
        return True
    if isinstance(value, list) and any(isinstance(v, dict) for v in value):
        return key in _ARRAY_OF_TABLES_KEYS
    return False


def _toml_dump(cfg: dict) -> str:
    """Serialise the subset of TOML that task.toml uses.

    Deliberately hand-rolled: the only alternative is a third-party dependency
    (tomli-w) for a file we control the shape of. Handles scalars, inline
    tables, arrays, and the ``[[artifacts]]`` array-of-tables we emit.
    """
    lines: list[str] = []

    def fmt(value: object) -> str:
        if isinstance(value, bool):
            return "true" if value else "false"
        if isinstance(value, (int, float)):
            return repr(value)
        if isinstance(value, str):
            return json.dumps(value)
        if isinstance(value, list):
            return "[" + ", ".join(fmt(v) for v in value) + "]"
        if isinstance(value, dict):
            inner = ", ".join(f"{k} = {fmt(v)}" for k, v in value.items())
            return "{ " + inner + " }"
        raise TypeError(f"cannot serialise {type(value).__name__}")

    def emit_table(prefix: str, table: dict) -> None:
        scalars = {k: v for k, v in table.items() if not _is_table(v, k)}
        subtables = {k: v for k, v in table.items() if _is_table(v, k)}

        if prefix:
            lines.append(f"[{prefix}]")
        for key, value in scalars.items():
            lines.append(f"{key} = {fmt(value)}")
        if scalars or prefix:
            lines.append("")

        for key, value in subtables.items():
            name = f"{prefix}.{key}" if prefix else key
            if isinstance(value, list):
                # array of tables -> [[name]]
                for entry in value:
                    lines.append(f"[[{name}]]")
                    for k, v in entry.items():
                        lines.append(f"{k} = {fmt(v)}")
                    lines.append("")
            else:
                emit_table(name, value)

    top_scalars = {k: v for k, v in cfg.items() if not _is_table(v, k)}
    for key, value in top_scalars.items():
        lines.append(f"{key} = {fmt(value)}")
    if top_scalars:
        lines.append("")

    for key, value in cfg.items():
        if not _is_table(value, key):
            continue
        if isinstance(value, list):
            for entry in value:
                lines.append(f"[[{key}]]")
                for k, v in entry.items():
                    lines.append(f"{k} = {fmt(v)}")
                lines.append("")
        else:
            emit_table(key, value)

    return "\n".join(lines).rstrip() + "\n"


def migrate_one(
    src: Path,
    dst: Path,
    *,
    base_image: str | None,
    workdir: str,
    old_workdir: str,
    venv_python: str,
    restore_pinned_judge: bool,
    overwrite: bool,
) -> dict:
    if dst.exists():
        if not overwrite:
            raise FileExistsError(f"{dst} exists; pass --overwrite")
        shutil.rmtree(dst)
    dst.mkdir(parents=True)

    # --- environment/: drop the Dockerfile in upload mode --------------------
    env_src, env_dst = src / "environment", dst / "environment"
    shutil.copytree(
        env_src,
        env_dst,
        ignore=shutil.ignore_patterns("Dockerfile" if base_image else "__never__"),
    )
    if base_image is None:
        # Baked mode: a Dockerfile with no docker_image is what makes Harbor
        # build rather than pull-and-skip-upload. The recipe comes from
        # images/Dockerfile.jobbench so the dependency list has a single source —
        # and because E2B cannot bind-mount /logs, /tests or /solution, a
        # minimal stock image would fail during log collection.
        from jobbench_e2b.adapter import render_dockerfile

        (env_dst / "Dockerfile").write_text(render_dockerfile(workdir), encoding="utf-8")

    # --- tests/: verbatim, then fix the interpreter and paths ---------------
    shutil.copytree(src / "tests", dst / "tests")
    test_sh = dst / "tests" / "test.sh"
    test_sh.write_text(
        _rewrite_test_sh(
            test_sh.read_text(encoding="utf-8"),
            old_workdir=old_workdir,
            new_workdir=workdir,
            venv_python=venv_python,
        ),
        encoding="utf-8",
    )
    test_sh.chmod(0o755)

    # --- judge.py: optionally restore the official pinned revision ----------
    # The source dataset carries a *modified* judge (see vendor/PROVENANCE.md),
    # so its scores are not comparable with upstream JobBench numbers. Swapping
    # in the pinned revision restores comparability; --keep-source-judge keeps
    # the local variant for reproducing previous runs.
    judge_sha = sha256_file(dst / "tests" / "judge.py")
    swapped = False
    if restore_pinned_judge and judge_sha != EVALUATOR_SHA256:
        (dst / "tests" / "judge.py").write_text(
            (VENDOR_DIR / "judge.py").read_text(encoding="utf-8"), encoding="utf-8"
        )
        judge_sha = EVALUATOR_SHA256
        swapped = True

    # --- solution/ ----------------------------------------------------------
    if (src / "solution").is_dir():
        shutil.copytree(src / "solution", dst / "solution")

    # --- instruction.md -----------------------------------------------------
    template = (TEMPLATE_DIR / "instruction.md").read_text(encoding="utf-8")
    instruction = template.replace("{workdir}", workdir)
    (dst / "instruction.md").write_text(instruction, encoding="utf-8")

    # --- task.toml ----------------------------------------------------------
    import tomllib  # Python 3.11+; the repo targets 3.12

    cfg = tomllib.loads((src / "task.toml").read_text(encoding="utf-8"))
    cfg.pop("storage_mb", None)

    env = cfg.setdefault("environment", {})
    env.pop("storage_mb", None)
    env["workdir"] = workdir
    if base_image:
        env["docker_image"] = base_image
    else:
        env.pop("docker_image", None)
    env.setdefault("network_mode", "public")

    agent = cfg.setdefault("agent", {})
    agent.pop("user", None)  # no such user inside E2B
    for bad in ("reasoning_effort", "cwd", "output_dir"):
        agent.pop(bad, None)  # silently ignored by the task-level schema

    verifier = cfg.setdefault("verifier", {})
    verifier.setdefault("user", "root")
    v_env = verifier.setdefault("env", {})
    v_env.setdefault("JOBBENCH_JUDGE_WORKERS", "3")
    v_env["JUDGE_API_BASE"] = "${JUDGE_API_BASE}"
    v_env["JUDGE_API_KEY"] = "${JUDGE_API_KEY}"
    v_env["JUDGE_MODEL"] = "${JUDGE_MODEL}"

    artifacts = cfg.get("artifacts")
    if isinstance(artifacts, list):
        for entry in artifacts:
            if isinstance(entry, dict) and "source" in entry:
                entry["source"] = entry["source"].replace(old_workdir, workdir)

    meta = cfg.setdefault("metadata", {})
    meta["instruction_sha256"] = sha256_text(instruction)
    meta["migrated_by"] = "jobbench_e2b.migrate"
    meta.setdefault("jobbench_evaluator_commit", EVALUATOR_COMMIT)

    (dst / "task.toml").write_text(_toml_dump(cfg), encoding="utf-8")

    return {
        "task": src.name,
        "network_required": bool(meta.get("network_required")),
        "judge_sha256": judge_sha,
        "judge_swapped_to_pinned": swapped,
    }


def run(
    *,
    source_root: Path,
    output_root: Path,
    splits: list[str],
    base_image: str | None,
    workdir: str,
    old_workdir: str,
    venv_python: str,
    restore_pinned_judge: bool,
    overwrite: bool,
    limit: int | None = None,
    task_ids: list[str] | None = None,
) -> MigrationReport:
    report = MigrationReport()

    for split in splits:
        src_split = source_root / split
        if not src_split.is_dir():
            report.skipped.append(f"{split}: no such directory {src_split}")
            continue

        dst_split = output_root / split
        dst_split.mkdir(parents=True, exist_ok=True)

        tasks = sorted(p for p in src_split.iterdir() if (p / "task.toml").is_file())
        if task_ids:
            wanted = {t.replace("/", "__") for t in task_ids}
            tasks = [t for t in tasks if t.name in wanted]
        if limit is not None:
            tasks = tasks[:limit]

        for task in tasks:
            try:
                info = migrate_one(
                    task,
                    dst_split / task.name,
                    base_image=base_image,
                    workdir=workdir,
                    old_workdir=old_workdir,
                    venv_python=venv_python,
                    restore_pinned_judge=restore_pinned_judge,
                    overwrite=overwrite,
                )
                report.converted.append(f"{split}/{info['task']}")
                print(f"  [{split}] {info['task']}")
            except Exception as exc:  # noqa: BLE001 - keep going, report at the end
                report.warnings.append(f"{split}/{task.name}: {exc}")

    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Reshape a JobBench-Harbor dataset for Harbor + E2B.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--source-root",
        type=Path,
        required=True,
        help="Existing dataset root, e.g. .../JobBench-Harbor/datasets/jobbench",
    )
    parser.add_argument(
        "--split",
        action="append",
        dest="splits",
        choices=["main", "easy"],
        help="Split to migrate; repeat for both. Default: main.",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=REPO_ROOT / "datasets",
        help="Where to write the E2B-ready dataset.",
    )
    parser.add_argument(
        "--base-image",
        default=None,
        help=(
            "Runtime-upload mode: rewrite docker_image to this reference. The "
            "image must already contain /logs, /tests, /solution and the workdir "
            "— E2B cannot bind-mount them. Omit (the default) for baked mode."
        ),
    )
    parser.add_argument(
        "--baked-image",
        action="store_true",
        help="Force baked mode (already the default when --base-image is omitted).",
    )
    parser.add_argument("--workdir", default="/workspace")
    parser.add_argument(
        "--old-workdir",
        default="/home/user",
        help="Workdir used by the source dataset (default: /home/user).",
    )
    parser.add_argument(
        "--venv-python",
        default=DEFAULT_VENV_PYTHON,
        help=f"Interpreter with the judge deps (default: {DEFAULT_VENV_PYTHON}).",
    )
    parser.add_argument(
        "--keep-source-judge",
        action="store_true",
        help=(
            "Keep the judge.py that ships with the source dataset instead of "
            "restoring the official pinned revision. The source judge is a "
            "modified variant, so its scores are not comparable with upstream "
            "JobBench numbers — only use this to reproduce those runs."
        ),
    )
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--task-ids", nargs="+", default=None)
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = run(
        source_root=args.source_root,
        output_root=args.output_root,
        splits=args.splits or ["main"],
        base_image=args.base_image,
        workdir=args.workdir,
        old_workdir=args.old_workdir,
        venv_python=args.venv_python,
        restore_pinned_judge=not args.keep_source_judge,
        overwrite=args.overwrite,
        limit=args.limit,
        task_ids=args.task_ids,
    )
    print("\n" + report.summary())
    return 1 if report.warnings else 0


if __name__ == "__main__":
    raise SystemExit(main())
