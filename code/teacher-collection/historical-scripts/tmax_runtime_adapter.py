"""Validate and call TMax's pinned native Apptainer-to-Harbor converter.

Original release files remain immutable. Private fixtures or reference material
in the agent image are explicit preparation failures, never silently copied to
the teacher or rewritten to make a task pass.
"""

from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
import re
from pathlib import Path
from types import ModuleType
from typing import Any

CONVERTER_COMMIT = "6d3d606c0f9de6ceec9481f9ccc793936818fef0"
CONVERTER_SHA256 = "20a50e89949c2822e5729b3461581b4e47d79bfd3d39dd3cf005613c7dab66bb"
CONVERTER_URL = (
    "https://github.com/hamishivi/tmax/blob/"
    + CONVERTER_COMMIT
    + "/rl_data/scripts/analyze/convert_to_harbor.py"
)
PRIVATE_MARKERS = re.compile(
    r"(?:oracle|ground[\s_-]?truth|hidden[_-]?truth|answer[_-]?key|expected[_-]?output)"
    r"|\.(?:label|algo|answer)\.txt"
    r"|\btruth\.(?:csv|txt|json|npy)\b"
    r"|\.?\bexpected[_-][A-Za-z0-9_.-]+\.(?:txt|csv|json|npy)\b"
    r"|/\.expected[_-][A-Za-z0-9_.-]+"
    r"|/(?:expected|golden)/"
    r"|\bgolden(?:_[A-Za-z0-9_-]+)?\.(?:csv|txt|json|npy)\b"
    r"|/\.(?:secret|private)[_-](?:true|expected)[_-][A-Za-z0-9_.-]+"
    r"|Expected token:",
    re.IGNORECASE,
)


class TaskPreparationError(ValueError):
    """A source task cannot yet be delivered under the trusted-data boundary."""


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def runtime_environment_files(source: Path) -> dict[str, str]:
    """Original shell sections copied into the external image build context."""
    definition = (source / "container.def").read_text()
    files = {}
    for section, destination in (
        ("environment", "/usr/local/lib/tmax-original-environment.sh"),
        ("startscript", "/usr/local/lib/tmax-original-startscript.sh"),
    ):
        match = re.search(
            rf"^%{section}\b[^\n]*\n(.*?)(?=^%\w+|\Z)",
            definition,
            re.MULTILINE | re.DOTALL,
        )
        if match and match.group(1).strip():
            body = match.group(1).rstrip() + "\n"
            if section == "environment":
                # Harbor executes noninteractive bash -c; child tools inherit
                # the initialized values rather than running setup twice.
                body = (
                    'if [ "${TMAX_ORIGINAL_ENV_LOADED-}" != 1 ]; then\n'
                    "export TMAX_ORIGINAL_ENV_LOADED=1\n" + body + "fi\n"
                )
            else:
                interactive = bool(
                    re.search(r">>?\s*['\"]?/etc/bash\.bashrc\b", definition)
                )
                body += (
                    "exec bash -ic 'exec sleep infinity'"
                    if interactive
                    else "exec sleep infinity"
                ) + "\n"
            files[destination] = body
    return files


def runtime_compose_override(source: Path) -> dict[str, Any]:
    """Run original startup from files, preserving exports and process matching."""
    definition = (source / "container.def").read_text()
    files = runtime_environment_files(source)
    interactive = bool(re.search(r">>?\s*['\"]?/etc/bash\.bashrc\b", definition))
    if "/usr/local/lib/tmax-original-startscript.sh" in files:
        command = [
            "bash",
            "-lc",
            "exec bash /usr/local/lib/tmax-original-startscript.sh",
        ]
    elif files:
        command = [
            "bash",
            "-lc",
            "exec bash -ic 'exec sleep infinity'"
            if interactive
            else "exec sleep infinity",
        ]
    else:
        command = ["bash", "-ic" if interactive else "-lc", "exec sleep infinity"]
    # Upstream env.py uses --pwd /home/user and exports HOME=/home/user.
    main: dict[str, Any] = {
        "command": command,
        "working_dir": "/home/user",
        "environment": {"HOME": "/home/user"},
    }
    if files:
        # Native Harbor compose up --wait observes finite original startup.
        main["healthcheck"] = {
            "test": [
                "CMD",
                "bash",
                "-c",
                'read -r task_process < /proc/1/comm; test "$$task_process" = sleep',
            ],
            "interval": "1s",
            "timeout": "2s",
            "retries": 120,
        }
    return {"services": {"main": main}}


def load_native_converter(path: Path) -> ModuleType:
    if digest(path) != CONVERTER_SHA256:
        raise TaskPreparationError("Pinned native converter SHA256 mismatch")
    spec = importlib.util.spec_from_file_location("tmax_native_conversion", path)
    if spec is None or spec.loader is None:
        raise TaskPreparationError("Native converter module cannot be loaded")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def inspect_source(source: Path, native: ModuleType) -> dict[str, Any]:
    """Reject unresolved fixture paths and known private material before build."""
    source = source.resolve()
    required = [
        "task.json",
        "container.def",
        "test_initial_state.py",
        "test_final_state.py",
    ]
    for relative in required:
        if not (source / relative).is_file():
            raise TaskPreparationError("Missing original source member: " + relative)
    metadata = json.loads((source / "task.json").read_text())
    if (
        metadata.get("name") != source.name
        or not metadata.get("description", "").strip()
    ):
        raise TaskPreparationError("Original task identity or instruction is invalid")
    # Verifier-owned answer paths are evidence even when the setup names the
    # file only "reference" or "expected" rather than "oracle". Publicly named
    # task inputs/outputs remain part of the original problem statement.
    private_paths = set()
    try:
        tree = ast.parse((source / "test_final_state.py").read_text())
    except SyntaxError as error:
        raise TaskPreparationError(
            f"Original final-state verifier has invalid syntax at line {error.lineno}"
        ) from error
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        value = node.value
        if not isinstance(value, ast.Constant) or not isinstance(value.value, str):
            continue
        if not value.value.startswith("/") or value.value in metadata["description"]:
            continue
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        names = [
            part.id
            for target in targets
            for part in ast.walk(target)
            if isinstance(part, ast.Name)
        ]
        if any(
            re.search(r"oracle|truth|reference|golden|expected", name, re.I)
            for name in names
        ):
            private_paths.add(value.value)
    if private_paths:
        raise TaskPreparationError(
            "VERIFIER_PRIVATE_PATH_REQUIRES_TRUSTED_SETUP: "
            + ", ".join(sorted(private_paths))
        )
    definition = (source / "container.def").read_text()
    if not re.search(r"^Bootstrap:\s*docker\s*$", definition, re.I | re.M):
        raise TaskPreparationError(
            "Source is not a supported original Apptainer Docker definition"
        )
    private_matches = sorted(set(PRIVATE_MARKERS.findall(definition)))
    if private_matches:
        raise TaskPreparationError(
            "PRIVATE_MATERIAL_IN_AGENT_BUILD_REQUIRES_TRUSTED_ADAPTER: "
            + ", ".join(private_matches)
        )
    fixtures = []
    for original, destination in native.parse_files_section(source / "container.def"):
        resolved = native._resolve_fixture_src(original, source)
        if resolved is None:
            raise TaskPreparationError("Unresolved original fixture: " + original)
        if resolved.is_symlink():
            raise TaskPreparationError(
                "Fixture symlinks require explicit source-boundary review"
            )
        resolved = resolved.resolve()
        if not resolved.is_relative_to(source):
            raise TaskPreparationError(
                "Fixture resolution escaped the original task directory"
            )
        target = Path(destination)
        if not target.is_absolute() or ".." in target.parts:
            raise TaskPreparationError(
                "Fixture destination is not a canonical absolute path"
            )
        if resolved.is_symlink() or any(p.is_symlink() for p in resolved.rglob("*")):
            raise TaskPreparationError(
                "Fixture symlinks require explicit source-boundary review"
            )
        fixtures.append(
            dict(source=str(resolved.relative_to(source)), destination=destination)
        )
    return dict(
        task_id=source.name,
        original_files={name: digest(source / name) for name in required},
        original_instruction_sha256=hashlib.sha256(
            metadata["description"].encode()
        ).hexdigest(),
        fixture_mapping=fixtures,
        base_image=metadata.get("base_image"),
        original_timeout_fields={
            key: value for key, value in metadata.items() if "timeout" in key.lower()
        },
    )


def convert_task(
    source: Path,
    destination: Path,
    *,
    native_converter: Path,
    intricate_base_definition: Path,
) -> dict[str, Any]:
    """Use the upstream converter unchanged and verify its actual outputs."""
    native = load_native_converter(native_converter)
    source = source.resolve()
    receipt = inspect_source(source, native)
    if receipt["original_timeout_fields"]:
        raise TaskPreparationError(
            "Published timeout fields are not handled by the pinned native converter"
        )
    target = destination / source.name
    if target.exists():
        raise FileExistsError("Existing converted task is preserved: " + str(target))
    base_post, base_env = native.load_intricate_base(intricate_base_definition)
    name = native.convert_task(
        source,
        destination,
        intricate_base_post=base_post,
        intricate_env=base_env,
        intricate_base_image_tag=None,
    )
    if name != source.name:
        raise TaskPreparationError(
            "Native converter did not produce the expected original identity"
        )
    if digest(target / "instruction.md") != receipt["original_instruction_sha256"]:
        raise TaskPreparationError("Native converter changed the official instruction")
    if (
        digest(target / "tests/test_final_state.py")
        != receipt["original_files"]["test_final_state.py"]
    ):
        raise TaskPreparationError(
            "Native converter changed the official final-state verifier"
        )
    if (target / "environment/task.json").exists() or (
        target / "environment/test_final_state.py"
    ).exists():
        raise TaskPreparationError(
            "Private task metadata or tests reached the agent build context"
        )
    receipt.update(
        status="NATIVE_CONVERSION_VERIFIED_ENVIRONMENT_NOT_YET_ACCEPTED",
        converter_commit=CONVERTER_COMMIT,
        converter_sha256=CONVERTER_SHA256,
        converter_url=CONVERTER_URL,
        intricate_base_definition_sha256=digest(intricate_base_definition),
        task_toml_sha256=digest(target / "task.toml"),
        environment_dockerfile_sha256=digest(target / "environment/Dockerfile"),
        source_unchanged=all(
            digest(source / name) == sha
            for name, sha in receipt["original_files"].items()
        ),
        reward_script="Unmodified native converter TEST_SH; final-state verifier copied byte for byte",
        source_timeouts="No published timeout field"
        if not receipt["original_timeout_fields"]
        else "PUBLISHED_FIELDS_REQUIRE_REVIEW",
    )
    if not receipt["source_unchanged"]:
        raise TaskPreparationError("Original source changed during conversion")
    return receipt
